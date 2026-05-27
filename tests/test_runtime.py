import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

from marstek_ble_mqtt.config import AppConfig, BleConfig
from marstek_ble_mqtt.models import BatteryData, Telemetry
from marstek_ble_mqtt.mqtt import MqttConfig
from marstek_ble_mqtt.profiles import DeviceProfile
from marstek_ble_mqtt.protocol import parse_read_command
from marstek_ble_mqtt.runtime import RunOptions, RuntimeAdapters, run_bridge


class StopRun(BaseException):
    pass


class FakeClient:
    write_characteristic_uuid = "write"
    subscribed_characteristics = ("notify",)

    def __init__(self, *, fail_sample: bool = False) -> None:
        self.fail_sample = fail_sample

    async def read(self, _command) -> bytes:
        if self.fail_sample:
            raise TimeoutError("timed out")
        return b"ok"


def _profile() -> DeviceProfile:
    return DeviceProfile(
        slug="jupiter-hmm",
        display_name="test",
        maturity="test",
        read_command=parse_read_command("bms-data"),
        decoder=lambda _payload: Telemetry(battery=BatteryData(soc_percent=83.0)),
    )


def _config(**ble_kwargs) -> AppConfig:
    return AppConfig(
        ble=BleConfig(address="AA:BB:CC:DD:EE:FF", **ble_kwargs),
        mqtt=MqttConfig(publish_groups=("battery",)),
    )


def test_stdout_mode_prints_samples_and_skips_mqtt() -> None:
    printed_samples = []
    sample_count = 0

    @asynccontextmanager
    async def fake_open_ble_request_client(**_kwargs):
        yield FakeClient()

    async def fake_sleep(_delay: float) -> None:
        nonlocal sample_count
        sample_count += 1
        raise StopRun

    adapters = RuntimeAdapters(
        load_config=lambda _path: _config(),
        get_profile=lambda _slug: _profile(),
        open_ble_request_client=fake_open_ble_request_client,
        print_sample=lambda sample, **_kwargs: printed_samples.append(sample),
        publish_mqtt=lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected mqtt")),
        log_event=lambda *_args, **_kwargs: None,
        clock=lambda: datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        sleep=fake_sleep,
    )

    with suppress(StopRun):
        asyncio.run(run_bridge(RunOptions(config_path=Path("config.toml"), stdout=True), adapters))

    assert printed_samples == [
        {
            "ts": "2026-05-24T12:00:00+00:00",
            "battery_soc_percent": 83.0,
        }
    ]
    assert sample_count == 1


def test_mqtt_mode_publishes_and_skips_stdout() -> None:
    published = []

    @asynccontextmanager
    async def fake_open_ble_request_client(**_kwargs):
        yield FakeClient()

    async def fake_sleep(_delay: float) -> None:
        raise StopRun

    adapters = RuntimeAdapters(
        load_config=lambda _path: _config(),
        get_profile=lambda _slug: _profile(),
        open_ble_request_client=fake_open_ble_request_client,
        publish_mqtt=lambda _config, messages: published.append(messages) or ["marstek/battery"],
        print_sample=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unexpected stdout")
        ),
        log_event=lambda *_args, **_kwargs: None,
        clock=lambda: datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        sleep=fake_sleep,
    )

    with suppress(StopRun):
        asyncio.run(run_bridge(RunOptions(config_path=Path("config.toml")), adapters))

    assert published[0][0].payload == {
        "ts": "2026-05-24T12:00:00+00:00",
        "soc_percent": 83.0,
    }


def test_sample_failure_reconnects() -> None:
    attempts = 0

    @asynccontextmanager
    async def fake_open_ble_request_client(**_kwargs):
        nonlocal attempts
        attempts += 1
        yield FakeClient(fail_sample=attempts == 1)

    async def fake_sleep(_delay: float) -> None:
        if attempts >= 2:
            raise StopRun

    adapters = RuntimeAdapters(
        load_config=lambda _path: _config(poll_interval=10.0),
        get_profile=lambda _slug: _profile(),
        open_ble_request_client=fake_open_ble_request_client,
        print_sample=lambda *_args, **_kwargs: None,
        log_event=lambda *_args, **_kwargs: None,
        sleep=fake_sleep,
    )

    with suppress(StopRun):
        asyncio.run(run_bridge(RunOptions(config_path=Path("config.toml"), stdout=True), adapters))

    assert attempts == 2


def test_connection_failure_retries() -> None:
    attempts = 0

    @asynccontextmanager
    async def fake_open_ble_request_client(**_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("cannot connect")
        yield FakeClient()

    async def fake_sleep(_delay: float) -> None:
        if attempts >= 2:
            raise StopRun

    adapters = RuntimeAdapters(
        load_config=lambda _path: _config(poll_interval=10.0),
        get_profile=lambda _slug: _profile(),
        open_ble_request_client=fake_open_ble_request_client,
        print_sample=lambda *_args, **_kwargs: None,
        log_event=lambda *_args, **_kwargs: None,
        sleep=fake_sleep,
    )

    with suppress(StopRun):
        asyncio.run(run_bridge(RunOptions(config_path=Path("config.toml"), stdout=True), adapters))

    assert attempts == 2
