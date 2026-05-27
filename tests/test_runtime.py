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


class FakePublisher:
    def __init__(self, *, fail_first_publish: bool = False) -> None:
        self.fail_first_publish = fail_first_publish
        self.published: list[tuple] = []
        self.closed = False

    def publish(self, messages: tuple) -> list[str]:
        if self.fail_first_publish:
            self.fail_first_publish = False
            raise ConnectionError("mqtt offline")
        self.published.append(messages)
        return ["marstek/battery"]

    def close(self) -> None:
        self.closed = True


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
        open_mqtt_publisher=lambda _config: (_ for _ in ()).throw(
            AssertionError("unexpected mqtt")
        ),
        log_event=lambda *_args, **_kwargs: None,
        clock=lambda: datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        sleep=fake_sleep,
    )

    with suppress(StopRun):
        asyncio.run(run_bridge(RunOptions(config_path=Path("config.toml"), stdout=True), adapters))

    assert printed_samples == [
        {
            "ts": "2026-05-24T12:00:00+00:00",
            "battery": {
                "soc_percent": 83.0,
            },
        }
    ]
    assert sample_count == 1


def test_mqtt_mode_publishes_and_skips_stdout() -> None:
    publisher = FakePublisher()

    @asynccontextmanager
    async def fake_open_ble_request_client(**_kwargs):
        yield FakeClient()

    async def fake_sleep(_delay: float) -> None:
        raise StopRun

    adapters = RuntimeAdapters(
        load_config=lambda _path: _config(),
        get_profile=lambda _slug: _profile(),
        open_ble_request_client=fake_open_ble_request_client,
        open_mqtt_publisher=lambda _config: publisher,
        print_sample=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unexpected stdout")
        ),
        log_event=lambda *_args, **_kwargs: None,
        clock=lambda: datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        sleep=fake_sleep,
    )

    with suppress(StopRun):
        asyncio.run(run_bridge(RunOptions(config_path=Path("config.toml")), adapters))

    assert publisher.published[0][0].payload == {
        "ts": "2026-05-24T12:00:00+00:00",
        "soc_percent": 83.0,
    }
    assert publisher.closed is True


def test_mqtt_publisher_opens_once_for_multiple_samples() -> None:
    publishers: list[FakePublisher] = []
    sample_count = 0

    @asynccontextmanager
    async def fake_open_ble_request_client(**_kwargs):
        yield FakeClient()

    async def fake_sleep(_delay: float) -> None:
        nonlocal sample_count
        sample_count += 1
        if sample_count >= 2:
            raise StopRun

    def fake_open_mqtt_publisher(_config: MqttConfig) -> FakePublisher:
        publisher = FakePublisher()
        publishers.append(publisher)
        return publisher

    adapters = RuntimeAdapters(
        load_config=lambda _path: _config(),
        get_profile=lambda _slug: _profile(),
        open_ble_request_client=fake_open_ble_request_client,
        open_mqtt_publisher=fake_open_mqtt_publisher,
        print_sample=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unexpected stdout")
        ),
        log_event=lambda *_args, **_kwargs: None,
        clock=lambda: datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        sleep=fake_sleep,
    )

    with suppress(StopRun):
        asyncio.run(run_bridge(RunOptions(config_path=Path("config.toml")), adapters))

    assert len(publishers) == 1
    assert len(publishers[0].published) == 2
    assert publishers[0].closed is True


def test_mqtt_publish_failure_logs_and_sample_loop_continues() -> None:
    publisher = FakePublisher(fail_first_publish=True)
    sample_count = 0
    events = []

    @asynccontextmanager
    async def fake_open_ble_request_client(**_kwargs):
        yield FakeClient()

    async def fake_sleep(_delay: float) -> None:
        nonlocal sample_count
        sample_count += 1
        if sample_count >= 2:
            raise StopRun

    adapters = RuntimeAdapters(
        load_config=lambda _path: _config(),
        get_profile=lambda _slug: _profile(),
        open_ble_request_client=fake_open_ble_request_client,
        open_mqtt_publisher=lambda _config: publisher,
        print_sample=lambda *_args, **_kwargs: None,
        log_event=lambda *args, **kwargs: events.append((args, kwargs)),
        clock=lambda: datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        sleep=fake_sleep,
    )

    with suppress(StopRun):
        asyncio.run(run_bridge(RunOptions(config_path=Path("config.toml")), adapters))

    assert len(publisher.published) == 1
    assert [args[1] for args, _kwargs in events if args[0] == "warning"] == ["mqtt_publish_failed"]


def test_ble_sample_failure_reconnects_without_reopening_mqtt() -> None:
    attempts = 0
    publishers: list[FakePublisher] = []

    @asynccontextmanager
    async def fake_open_ble_request_client(**_kwargs):
        nonlocal attempts
        attempts += 1
        yield FakeClient(fail_sample=attempts == 1)

    async def fake_sleep(_delay: float) -> None:
        if attempts >= 2:
            raise StopRun

    def fake_open_mqtt_publisher(_config: MqttConfig) -> FakePublisher:
        publisher = FakePublisher()
        publishers.append(publisher)
        return publisher

    adapters = RuntimeAdapters(
        load_config=lambda _path: _config(poll_interval=10.0),
        get_profile=lambda _slug: _profile(),
        open_ble_request_client=fake_open_ble_request_client,
        open_mqtt_publisher=fake_open_mqtt_publisher,
        print_sample=lambda *_args, **_kwargs: None,
        log_event=lambda *_args, **_kwargs: None,
        sleep=fake_sleep,
    )

    with suppress(StopRun):
        asyncio.run(run_bridge(RunOptions(config_path=Path("config.toml")), adapters))

    assert attempts == 2
    assert len(publishers) == 1
    assert len(publishers[0].published) == 1


def test_stop_event_exits_and_closes_mqtt_publisher() -> None:
    stop_event = asyncio.Event()
    publisher = FakePublisher()
    exited_ble_context = False
    events = []

    @asynccontextmanager
    async def fake_open_ble_request_client(**_kwargs):
        nonlocal exited_ble_context
        try:
            yield FakeClient()
        finally:
            exited_ble_context = True

    async def fake_sleep(_delay: float) -> None:
        stop_event.set()

    adapters = RuntimeAdapters(
        load_config=lambda _path: _config(),
        get_profile=lambda _slug: _profile(),
        open_ble_request_client=fake_open_ble_request_client,
        open_mqtt_publisher=lambda _config: publisher,
        print_sample=lambda *_args, **_kwargs: None,
        log_event=lambda *args, **kwargs: events.append((args, kwargs)),
        clock=lambda: datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        sleep=fake_sleep,
        stop_event=stop_event,
        stop_reason=lambda: "SIGTERM",
        stop_exit_code=lambda: 143,
    )

    exit_code = asyncio.run(run_bridge(RunOptions(config_path=Path("config.toml")), adapters))

    assert exit_code == 143
    assert exited_ble_context is True
    assert publisher.closed is True
    assert events[-1] == (("info", "stopped"), {"reason": "SIGTERM"})


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
