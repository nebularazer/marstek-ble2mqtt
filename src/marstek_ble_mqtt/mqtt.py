"""MQTT publishing for projected telemetry messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from marstek_ble_mqtt.telemetry_projection import ProjectionMessage


@dataclass(frozen=True)
class MqttConfig:
    """MQTT connection, topic, and publishing configuration."""

    host: str = "localhost"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    topic_prefix: str = "marstek"
    publish_groups: tuple[str, ...] = ()


def publish_messages_with_client(
    client: Any,
    topic_prefix: str,
    messages: tuple[ProjectionMessage, ...],
) -> list[str]:
    """Publish already-projected telemetry messages with an MQTT client."""

    prefix = topic_prefix.rstrip("/")
    published = []
    for message in messages:
        topic = f"{prefix}/{message.topic_suffix}"
        client.publish(topic, message.payload_json, retain=False)
        published.append(topic)

    return published
