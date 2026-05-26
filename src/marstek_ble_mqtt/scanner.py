"""Read-only BLE advertisement scanner."""

from __future__ import annotations

import re
from dataclasses import dataclass

MARSTEK_MARKERS = (
    "MST",
    "MARSTEK",
    "HAME",
    "HMM",
    "HMJ",
    "JUPITER",
    "VENUS",
)


@dataclass(frozen=True)
class BleScanResult:
    """BLE advertisement data captured without connecting to the device."""

    address: str
    name: str | None
    manufacturer_data: dict[int, str]
    service_uuids: tuple[str, ...]
    is_likely_marstek: bool
    matched_markers: tuple[str, ...]


async def scan_ble_devices(timeout: float = 5.0) -> list[BleScanResult]:
    """Scan BLE advertisements without connecting to any device."""

    try:
        from bleak import BleakScanner
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "Bleak is required for BLE scanning. Install dependencies with: uv sync --dev"
        ) from exc

    discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
    results = []
    for device, advertisement in discovered.values():
        name = advertisement.local_name or device.name
        manufacturer_data = {
            company_id: bytes(payload).hex()
            for company_id, payload in advertisement.manufacturer_data.items()
        }
        service_uuids = tuple(advertisement.service_uuids or ())
        matched_markers = find_marstek_markers(name=name, manufacturer_data=manufacturer_data)

        results.append(
            BleScanResult(
                address=device.address,
                name=name,
                manufacturer_data=manufacturer_data,
                service_uuids=service_uuids,
                is_likely_marstek=bool(matched_markers),
                matched_markers=matched_markers,
            )
        )

    return sorted(results, key=_sort_key)


def find_marstek_markers(
    *,
    name: str | None,
    manufacturer_data: dict[int, str],
) -> tuple[str, ...]:
    """Return known Marstek/Hame markers found in advertised name or manufacturer bytes."""

    haystacks = []
    if name:
        haystacks.append(name.upper())

    for payload_hex in manufacturer_data.values():
        payload = bytes.fromhex(payload_hex)
        haystacks.append(_ascii_preview(payload).upper())
        haystacks.append(payload_hex.upper())

    matched = {
        marker for marker in MARSTEK_MARKERS if any(marker in haystack for haystack in haystacks)
    }
    return tuple(marker for marker in MARSTEK_MARKERS if marker in matched)


def format_scan_results(results: list[BleScanResult]) -> str:
    """Format scan results for terminal output."""

    if not results:
        return "No BLE advertisements found."

    blocks = []
    for result in results:
        heading = "[LIKELY MARSTEK/HAME] " if result.is_likely_marstek else ""
        heading += f"{result.address}  {result.name or '<unknown>'}"
        lines = [
            heading,
            f"  Manufacturer data: {_format_manufacturer_data(result.manufacturer_data)}",
            f"  Service UUIDs: {_format_sequence(result.service_uuids)}",
        ]
        if result.matched_markers:
            lines.append(f"  Matched markers: {', '.join(result.matched_markers)}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _ascii_preview(payload: bytes) -> str:
    return re.sub(r"[^ -~]", ".", payload.decode("latin1", errors="replace"))


def _format_manufacturer_data(manufacturer_data: dict[int, str]) -> str:
    if not manufacturer_data:
        return "<none>"

    return ", ".join(
        f"0x{company_id:04x}={payload_hex}"
        for company_id, payload_hex in sorted(manufacturer_data.items())
    )


def _format_sequence(values: tuple[str, ...]) -> str:
    if not values:
        return "<none>"
    return ", ".join(values)


def _sort_key(result: BleScanResult) -> tuple[int, int, str]:
    likely_rank = 0 if result.is_likely_marstek else 1
    marker_rank = -len(result.matched_markers)
    return likely_rank, marker_rank, result.address
