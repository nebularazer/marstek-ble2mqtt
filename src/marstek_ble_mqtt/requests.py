"""Constrained BLE request/response commands."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from marstek_ble_mqtt.capture import ProtocolWriteCaptureRecord
from marstek_ble_mqtt.notifications import NotificationFrame, make_notification_frame
from marstek_ble_mqtt.protocol import (
    ReadCommand,
    build_command_frame,
    ensure_safe_read_command,
    is_response_for_command,
)

DEFAULT_WRITE_CHARACTERISTIC = "0000ff01-0000-1000-8000-00805f9b34fb"
DEFAULT_NOTIFY_CHARACTERISTIC = "0000ff02-0000-1000-8000-00805f9b34fb"
LOGGER = logging.getLogger(__name__)


class BleRequestClient:
    """A persistent BLE request/response client for read-style telemetry commands."""

    def __init__(
        self,
        *,
        client: Any,
        write_characteristic: Any,
        notify_characteristics: tuple[Any, ...],
        response_timeout: float,
        frame_sink: Callable[[NotificationFrame], None] | None = None,
        write_capture_sink: Callable[[ProtocolWriteCaptureRecord], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._write_characteristic = write_characteristic
        self._notify_characteristics = notify_characteristics
        self._response_timeout = response_timeout
        self._frame_sink = frame_sink
        self._write_capture_sink = write_capture_sink
        self._clock = clock or (lambda: datetime.now(UTC))
        self._response_event = asyncio.Event()
        self._response_command: int | None = None
        self._response_payload: bytes | None = None
        self._frame_count = 0

    @property
    def subscribed_characteristics(self) -> tuple[str, ...]:
        return tuple(characteristic.uuid for characteristic in self._notify_characteristics)

    @property
    def write_characteristic_uuid(self) -> str:
        return self._write_characteristic.uuid

    async def start(self) -> None:
        for characteristic in self._notify_characteristics:
            await self._client.start_notify(
                characteristic,
                _build_request_notification_callback(
                    characteristic_uuid=characteristic.uuid,
                    frame_sink=self._on_frame,
                ),
            )

    async def stop(self) -> None:
        for characteristic in self._notify_characteristics:
            await self._client.stop_notify(characteristic)

    async def read(self, command: ReadCommand) -> bytes:
        command = ensure_safe_read_command(command)
        self._response_command = command.code
        self._response_payload = None
        self._frame_count = 0
        self._response_event.clear()

        outbound_frame = build_command_frame(command.code)
        LOGGER.debug(
            "BLE read request command=%s code=0x%02x characteristic=%s payload=%s",
            command.name,
            command.code,
            self._write_characteristic.uuid,
            outbound_frame.hex(),
        )
        if self._write_capture_sink is not None:
            self._write_capture_sink(
                ProtocolWriteCaptureRecord(
                    timestamp=self._clock(),
                    purpose=command.purpose,
                    characteristic_uuid=self._write_characteristic.uuid,
                    payload_hex=outbound_frame.hex(),
                )
            )
        await self._client.write_gatt_char(
            self._write_characteristic,
            outbound_frame,
            response=False,
        )
        await asyncio.wait_for(self._response_event.wait(), timeout=self._response_timeout)

        if self._response_payload is None:
            raise TimeoutError(f"No response payload for command 0x{command.code:02x}")
        return self._response_payload

    def _on_frame(self, frame: NotificationFrame, payload: bytes) -> None:
        self._frame_count += 1
        if self._frame_sink is not None:
            self._frame_sink(frame)
        if self._response_command is not None and is_response_for_command(
            payload,
            self._response_command,
        ):
            self._response_payload = payload
            self._response_event.set()


@asynccontextmanager
async def open_ble_request_client(
    *,
    address: str,
    response_timeout: float = 5.0,
    connect_timeout: float = 30.0,
    write_characteristic_uuid: str = DEFAULT_WRITE_CHARACTERISTIC,
    notify_characteristic_uuids: tuple[str, ...] = (DEFAULT_NOTIFY_CHARACTERISTIC,),
    frame_sink: Callable[[NotificationFrame], None] | None = None,
    write_capture_sink: Callable[[ProtocolWriteCaptureRecord], None] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> AsyncIterator[BleRequestClient]:
    """Keep one BLE connection open for repeated read-style requests."""

    try:
        from bleak import BleakClient
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "Bleak is required for BLE requests. Install dependencies with: uv sync --dev"
        ) from exc

    async with BleakClient(address, timeout=connect_timeout) as client:
        write_characteristic = _resolve_write_characteristic(
            services=client.services,
            write_characteristic_uuid=write_characteristic_uuid,
        )
        notify_characteristics = _resolve_notify_characteristics(
            services=client.services,
            notify_characteristic_uuids=notify_characteristic_uuids,
        )
        connected = BleRequestClient(
            client=client,
            write_characteristic=write_characteristic,
            notify_characteristics=tuple(notify_characteristics),
            response_timeout=response_timeout,
            frame_sink=frame_sink,
            write_capture_sink=write_capture_sink,
            clock=clock,
        )
        await connected.start()
        try:
            yield connected
        finally:
            await connected.stop()


def _build_request_notification_callback(
    *,
    characteristic_uuid: str,
    frame_sink: Callable[[NotificationFrame, bytes], None],
) -> Callable[[Any, bytearray], None]:
    def callback(_: Any, payload: bytearray) -> None:
        payload_bytes = bytes(payload)
        frame = make_notification_frame(
            characteristic_uuid=characteristic_uuid,
            payload=payload_bytes,
        )
        frame_sink(frame, payload_bytes)

    return callback


def _find_characteristic(*, services: Any, uuid: str) -> Any | None:
    expected = uuid.lower()
    for service in services:
        for characteristic in service.characteristics:
            if characteristic.uuid.lower() == expected:
                return characteristic
    return None


def _resolve_write_characteristic(*, services: Any, write_characteristic_uuid: str) -> Any:
    write_characteristic = _find_characteristic(
        services=services,
        uuid=write_characteristic_uuid,
    )
    if write_characteristic is None:
        raise RuntimeError(f"Write characteristic not found: {write_characteristic_uuid}")
    if "write-without-response" not in set(write_characteristic.properties):
        raise RuntimeError(
            f"Characteristic {write_characteristic_uuid} does not advertise write-without-response"
        )
    return write_characteristic


def _resolve_notify_characteristics(
    *,
    services: Any,
    notify_characteristic_uuids: tuple[str, ...],
) -> list[Any]:
    requested_notify = {uuid.lower() for uuid in notify_characteristic_uuids}
    notify_characteristics = _find_notifiable_characteristics(
        services=services,
        requested_uuids=requested_notify,
    )
    if not notify_characteristics:
        raise RuntimeError("No matching notify/indicate characteristics found.")
    return notify_characteristics


def _find_notifiable_characteristics(
    *,
    services: Any,
    requested_uuids: set[str],
) -> list[Any]:
    characteristics = []
    for service in services:
        for characteristic in service.characteristics:
            properties = set(characteristic.properties)
            if not properties.intersection({"notify", "indicate"}):
                continue
            if requested_uuids and characteristic.uuid.lower() not in requested_uuids:
                continue
            characteristics.append(characteristic)
    return characteristics
