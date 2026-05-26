import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from marstek_ble_mqtt.capture import ProtocolWriteJsonlCapture
from marstek_ble_mqtt.protocol import ReadCommand, build_command_frame, parse_read_command
from marstek_ble_mqtt.requests import BleRequestClient


@dataclass(frozen=True)
class FakeCharacteristic:
    uuid: str


class FakeBleakClient:
    def __init__(self, response_payload: bytes) -> None:
        self.response_payload = response_payload
        self.notify_callbacks: list[Any] = []
        self.writes: list[tuple[FakeCharacteristic, bytes, bool]] = []
        self.stopped: list[FakeCharacteristic] = []

    async def start_notify(self, characteristic: FakeCharacteristic, callback: Any) -> None:
        self.notify_callbacks.append(callback)

    async def stop_notify(self, characteristic: FakeCharacteristic) -> None:
        self.stopped.append(characteristic)

    async def write_gatt_char(
        self,
        characteristic: FakeCharacteristic,
        payload: bytes,
        *,
        response: bool,
    ) -> None:
        self.writes.append((characteristic, payload, response))
        self.notify_callbacks[0](None, bytearray(self.response_payload))


def test_ble_request_client_writes_command_and_returns_matching_notification() -> None:
    async def run() -> None:
        write_characteristic = FakeCharacteristic("0000ff01-0000-1000-8000-00805f9b34fb")
        notify_characteristic = FakeCharacteristic("0000ff02-0000-1000-8000-00805f9b34fb")
        command = parse_read_command("bms-data")
        response_payload = build_command_frame(command.code)
        fake_client = FakeBleakClient(response_payload)
        client = BleRequestClient(
            client=fake_client,
            write_characteristic=write_characteristic,
            notify_characteristics=(notify_characteristic,),
            response_timeout=1.0,
        )

        await client.start()
        payload = await client.read(command)
        await client.stop()

        assert payload == response_payload
        assert fake_client.writes == [(write_characteristic, build_command_frame(0x14), False)]
        assert fake_client.stopped == [notify_characteristic]

    asyncio.run(run())


def test_ble_request_client_rejects_non_allowlisted_read_command() -> None:
    async def run() -> None:
        write_characteristic = FakeCharacteristic("0000ff01-0000-1000-8000-00805f9b34fb")
        notify_characteristic = FakeCharacteristic("0000ff02-0000-1000-8000-00805f9b34fb")
        fake_client = FakeBleakClient(build_command_frame(0x25))
        client = BleRequestClient(
            client=fake_client,
            write_characteristic=write_characteristic,
            notify_characteristics=(notify_characteristic,),
            response_timeout=1.0,
        )

        await client.start()
        with pytest.raises(ValueError, match="not in the safe read allowlist"):
            await client.read(ReadCommand(0x25, "unsafe", "Unsafe write-shaped command"))

        assert fake_client.writes == []

    asyncio.run(run())


def test_ble_request_client_captures_protocol_writes() -> None:
    async def run() -> None:
        records = []
        write_characteristic = FakeCharacteristic("0000ff01-0000-1000-8000-00805f9b34fb")
        notify_characteristic = FakeCharacteristic("0000ff02-0000-1000-8000-00805f9b34fb")
        command = parse_read_command("bms-data")
        response_payload = build_command_frame(command.code)
        fake_client = FakeBleakClient(response_payload)
        client = BleRequestClient(
            client=fake_client,
            write_characteristic=write_characteristic,
            notify_characteristics=(notify_characteristic,),
            response_timeout=1.0,
            write_capture_sink=records.append,
            clock=lambda: datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        )

        await client.start()
        await client.read(command)

        assert records[0].timestamp == datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
        assert records[0].purpose == "Live battery/PV/grid/cell telemetry"
        assert records[0].characteristic_uuid == "0000ff01-0000-1000-8000-00805f9b34fb"
        assert records[0].payload_hex == "7305231441"

    asyncio.run(run())


def test_protocol_write_jsonl_capture_writes_expected_record(tmp_path) -> None:
    path = tmp_path / "writes.jsonl"
    capture = ProtocolWriteJsonlCapture(path)
    records = []

    async def run() -> None:
        write_characteristic = FakeCharacteristic("0000ff01-0000-1000-8000-00805f9b34fb")
        notify_characteristic = FakeCharacteristic("0000ff02-0000-1000-8000-00805f9b34fb")
        command = parse_read_command("bms-data")
        fake_client = FakeBleakClient(build_command_frame(command.code))
        client = BleRequestClient(
            client=fake_client,
            write_characteristic=write_characteristic,
            notify_characteristics=(notify_characteristic,),
            response_timeout=1.0,
            write_capture_sink=lambda record: (records.append(record), capture(record)),
            clock=lambda: datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        )

        await client.start()
        await client.read(command)

    asyncio.run(run())

    assert path.read_text(encoding="utf-8") == (
        '{"characteristic_uuid":"0000ff01-0000-1000-8000-00805f9b34fb",'
        '"payload_hex":"7305231441","purpose":"Live battery/PV/grid/cell telemetry",'
        '"timestamp":"2026-05-24T12:00:00+00:00"}\n'
    )


def test_no_capture_file_is_written_without_capture_sink(tmp_path) -> None:
    path = tmp_path / "disabled.jsonl"

    async def run() -> None:
        write_characteristic = FakeCharacteristic("0000ff01-0000-1000-8000-00805f9b34fb")
        notify_characteristic = FakeCharacteristic("0000ff02-0000-1000-8000-00805f9b34fb")
        command = parse_read_command("bms-data")
        fake_client = FakeBleakClient(build_command_frame(command.code))
        client = BleRequestClient(
            client=fake_client,
            write_characteristic=write_characteristic,
            notify_characteristics=(notify_characteristic,),
            response_timeout=1.0,
        )

        await client.start()
        await client.read(command)

    asyncio.run(run())

    assert not path.exists()
