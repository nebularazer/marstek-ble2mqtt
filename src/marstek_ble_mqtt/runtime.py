"""Runtime bridge orchestration for telemetry reads and output."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from marstek_ble_mqtt.capture import ProtocolWriteJsonlCapture
from marstek_ble_mqtt.config import AppConfig, load_config, require_ble_address
from marstek_ble_mqtt.mqtt import MqttConfig, open_mqtt_publisher
from marstek_ble_mqtt.output import print_json_event, print_sample_json
from marstek_ble_mqtt.profiles import DeviceProfile, get_profile
from marstek_ble_mqtt.requests import open_ble_request_client
from marstek_ble_mqtt.telemetry_projection import (
    ProjectionMessage,
    project_stdout_sample,
    project_telemetry_messages,
    validate_publish_groups,
)


@dataclass(frozen=True)
class RunOptions:
    """Public run command options."""

    config_path: Path
    stdout: bool = False


@dataclass(frozen=True)
class RuntimeAdapters:
    """Adapters used by the bridge runtime."""

    load_config: Callable[[Path], AppConfig] = load_config
    require_ble_address: Callable[[AppConfig], str] = require_ble_address
    get_profile: Callable[[str], DeviceProfile] = get_profile
    open_ble_request_client: Callable[..., Any] = open_ble_request_client
    open_mqtt_publisher: Callable[[MqttConfig], Any] = open_mqtt_publisher
    print_sample: Callable[..., None] = print_sample_json
    log_event: Callable[..., None] = print_json_event
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    stop_event: asyncio.Event | None = None
    stop_reason: Callable[[], str | None] = lambda: None
    stop_exit_code: Callable[[], int] = lambda: 0


async def run_bridge(options: RunOptions, adapters: RuntimeAdapters | None = None) -> int:
    """Run the BLE-to-output bridge until stopped."""

    adapters = adapters or RuntimeAdapters()
    config = adapters.load_config(options.config_path)
    profile = adapters.get_profile(config.device_profile)
    address = adapters.require_ble_address(config)
    publish_groups = validate_publish_groups(config.mqtt.publish_groups)
    stdout_mode = bool(options.stdout)
    write_capture_sink = (
        ProtocolWriteJsonlCapture(config.capture.protocol_writes_path)
        if config.capture.protocol_writes_path is not None
        else None
    )

    adapters.log_event(
        "info",
        "starting",
        profile=profile.slug,
        publish_groups=publish_groups,
        topic_prefix=config.mqtt.topic_prefix,
        output="stdout" if stdout_mode else "mqtt",
        write_capture=bool(write_capture_sink),
    )

    mqtt_publisher = None
    if not stdout_mode and not _stop_requested(adapters):
        mqtt_publisher = adapters.open_mqtt_publisher(config.mqtt)

    try:
        while not _stop_requested(adapters):
            try:
                async with adapters.open_ble_request_client(
                    address=address,
                    response_timeout=config.ble.response_timeout,
                    connect_timeout=config.ble.connect_timeout,
                    write_capture_sink=write_capture_sink,
                    clock=adapters.clock,
                ) as client:
                    adapters.log_event(
                        "info",
                        "ble_connected",
                        profile=profile.slug,
                        write_char=client.write_characteristic_uuid,
                        notify_chars=client.subscribed_characteristics,
                    )
                    while not _stop_requested(adapters):
                        sample_started_at = adapters.clock()
                        try:
                            telemetry = profile.decoder(await client.read(profile.read_command))
                            messages = project_telemetry_messages(
                                timestamp=sample_started_at,
                                telemetry=telemetry,
                                publish_groups=publish_groups,
                            )
                            if stdout_mode:
                                adapters.print_sample(
                                    project_stdout_sample(
                                        timestamp=sample_started_at,
                                        telemetry=telemetry,
                                        publish_groups=publish_groups,
                                    ),
                                    flush=True,
                                )
                            elif mqtt_publisher is not None:
                                _publish_mqtt_sample(
                                    publisher=mqtt_publisher,
                                    messages=messages,
                                    topic_prefix=config.mqtt.topic_prefix,
                                    log_event=adapters.log_event,
                                )
                        except Exception as exc:
                            adapters.log_event(
                                "warning",
                                "sample_failed",
                                error_type=type(exc).__name__,
                                error=str(exc),
                                reconnecting=True,
                            )
                            break
                        if await _sleep_or_stop(config.ble.poll_interval, adapters):
                            break
            except Exception as exc:
                if _stop_requested(adapters):
                    break
                adapters.log_event(
                    "warning",
                    "connection_failed",
                    error_type=type(exc).__name__,
                    error=str(exc),
                    reconnecting=True,
                )
                if await _sleep_or_stop(min(config.ble.poll_interval, 10.0), adapters):
                    break
    finally:
        if mqtt_publisher is not None:
            mqtt_publisher.close()

    if _stop_requested(adapters):
        adapters.log_event("info", "stopped", reason=adapters.stop_reason() or "stop_requested")
        return adapters.stop_exit_code()

    return 0


def _publish_mqtt_sample(
    *,
    publisher: Any,
    messages: tuple[ProjectionMessage, ...],
    topic_prefix: str,
    log_event: Callable[..., None],
) -> None:
    try:
        topics = publisher.publish(messages)
    except Exception as exc:
        log_event(
            "warning",
            "mqtt_publish_failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return

    log_event(
        "info",
        "mqtt_published",
        topic_count=len(topics),
        topics=topics,
        topic_prefix=topic_prefix,
    )


def _stop_requested(adapters: RuntimeAdapters) -> bool:
    return adapters.stop_event is not None and adapters.stop_event.is_set()


async def _sleep_or_stop(delay: float, adapters: RuntimeAdapters) -> bool:
    if adapters.stop_event is None:
        await adapters.sleep(delay)
        return False

    if adapters.stop_event.is_set():
        return True

    sleep_task = asyncio.create_task(adapters.sleep(delay))
    stop_task = asyncio.create_task(adapters.stop_event.wait())
    done, pending = await asyncio.wait(
        {sleep_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
    for task in pending:
        with suppress(asyncio.CancelledError):
            await task

    for task in done:
        task.result()

    return adapters.stop_event.is_set()
