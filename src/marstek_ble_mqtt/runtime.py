"""Runtime bridge orchestration for telemetry reads and output."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from marstek_ble_mqtt.capture import ProtocolWriteJsonlCapture
from marstek_ble_mqtt.config import AppConfig, load_config, require_ble_address
from marstek_ble_mqtt.mqtt import publish_messages_with_client
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
    publish_mqtt: Callable[[Any, tuple[ProjectionMessage, ...]], list[str]] | None = None
    print_sample: Callable[..., None] = print_sample_json
    log_event: Callable[..., None] = print_json_event
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep


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

    while True:
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
                while True:
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
                        else:
                            topics = _publish_mqtt(
                                config=config,
                                messages=messages,
                                adapters=adapters,
                            )
                            adapters.log_event(
                                "info",
                                "mqtt_published",
                                topic_count=len(topics),
                                topics=topics,
                                topic_prefix=config.mqtt.topic_prefix,
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
                    await adapters.sleep(config.ble.poll_interval)
        except Exception as exc:
            adapters.log_event(
                "warning",
                "connection_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                reconnecting=True,
            )
            await adapters.sleep(min(config.ble.poll_interval, 10.0))


def _publish_mqtt(
    *,
    config: AppConfig,
    messages: tuple[ProjectionMessage, ...],
    adapters: RuntimeAdapters,
) -> list[str]:
    if adapters.publish_mqtt is not None:
        return adapters.publish_mqtt(config.mqtt, messages)

    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "paho-mqtt is required for MQTT publishing. Install dependencies with: uv sync --dev"
        ) from exc

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if config.mqtt.username:
        client.username_pw_set(config.mqtt.username, config.mqtt.password)

    client.connect(config.mqtt.host, config.mqtt.port, keepalive=30)
    client.loop_start()
    try:
        return publish_messages_with_client(client, config.mqtt.topic_prefix, messages)
    finally:
        client.loop_stop()
        client.disconnect()
