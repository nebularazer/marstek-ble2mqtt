"""Read-only BLE service and characteristic dumping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CharacteristicDump:
    """GATT characteristic metadata and optional read value."""

    uuid: str
    handle: int | None
    properties: tuple[str, ...]
    value_hex: str | None = None
    read_error: str | None = None


@dataclass(frozen=True)
class ServiceDump:
    """GATT service metadata and child characteristics."""

    uuid: str
    handle: int | None
    characteristics: tuple[CharacteristicDump, ...]


async def dump_ble_services(
    *,
    address: str,
    connect_timeout: float = 30.0,
    read_values: bool = True,
) -> list[ServiceDump]:
    """Connect to a BLE device and dump GATT services without performing writes."""

    try:
        from bleak import BleakClient
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "Bleak is required for BLE service dumps. Install dependencies with: uv sync --dev"
        ) from exc

    async with BleakClient(address, timeout=connect_timeout) as client:
        return await _dump_services_from_client(client=client, read_values=read_values)


async def _dump_services_from_client(*, client: Any, read_values: bool) -> list[ServiceDump]:
    services = client.services
    dumps = []
    for service in services:
        characteristics = []
        for characteristic in service.characteristics:
            properties = tuple(characteristic.properties)
            value_hex = None
            read_error = None

            if read_values and "read" in properties:
                try:
                    value = await client.read_gatt_char(characteristic)
                    value_hex = bytes(value).hex()
                except Exception as exc:  # noqa: BLE001 - preserve read failures in output.
                    read_error = f"{type(exc).__name__}: {exc}"

            characteristics.append(
                CharacteristicDump(
                    uuid=characteristic.uuid,
                    handle=_optional_attr(characteristic, "handle"),
                    properties=properties,
                    value_hex=value_hex,
                    read_error=read_error,
                )
            )

        dumps.append(
            ServiceDump(
                uuid=service.uuid,
                handle=_optional_attr(service, "handle"),
                characteristics=tuple(characteristics),
            )
        )

    return dumps


def format_service_dump(services: list[ServiceDump]) -> str:
    """Format a read-only service dump for terminal output."""

    if not services:
        return "No GATT services found."

    blocks = []
    for service in services:
        lines = [f"service {service.uuid}  handle={_format_optional(service.handle)}"]
        if not service.characteristics:
            lines.append("  <no characteristics>")
            blocks.append("\n".join(lines))
            continue

        for characteristic in service.characteristics:
            handle = _format_optional(characteristic.handle)
            lines.extend(
                [
                    f"  char {characteristic.uuid}  handle={handle}",
                    f"    properties: {_format_properties(characteristic.properties)}",
                ]
            )
            if "read" in characteristic.properties:
                lines.append(f"    value: {_format_value(characteristic)}")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _format_properties(properties: tuple[str, ...]) -> str:
    if not properties:
        return "<none>"
    return ", ".join(properties)


def _format_value(characteristic: CharacteristicDump) -> str:
    if characteristic.value_hex is not None:
        return characteristic.value_hex or "<empty>"
    if characteristic.read_error is not None:
        return f"<read failed: {characteristic.read_error}>"
    return "<not read>"


def _format_optional(value: object | None) -> str:
    if value is None:
        return "<unknown>"
    return str(value)


def _optional_attr(obj: Any, name: str) -> int | None:
    value = getattr(obj, name, None)
    return value if isinstance(value, int) else None
