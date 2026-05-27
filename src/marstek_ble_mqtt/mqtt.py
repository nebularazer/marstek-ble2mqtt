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
    client_id: str | None = None
    topic_prefix: str = "marstek"
    publish_groups: tuple[str, ...] = ()


class MqttPublisher:
    """Long-lived MQTT publisher for runtime telemetry samples."""

    def __init__(self, config: MqttConfig, client_factory: Any | None = None) -> None:
        self._config = config
        self._client = self._create_client(config, client_factory)
        self._closed = False

        if config.username:
            self._client.username_pw_set(config.username, config.password)

        self._client.reconnect_delay_set(min_delay=1, max_delay=60)
        self._client.connect(config.host, config.port, keepalive=30)
        self._client.loop_start()

    def publish(self, messages: tuple[ProjectionMessage, ...]) -> list[str]:
        """Publish projected telemetry messages on the existing connection."""

        return publish_messages_with_client(self._client, self._config.topic_prefix, messages)

    def close(self) -> None:
        """Stop the network loop and disconnect the MQTT client."""

        if self._closed:
            return
        self._closed = True
        self._client.loop_stop()
        self._client.disconnect()

    @staticmethod
    def _create_client(config: MqttConfig, client_factory: Any | None) -> Any:
        if client_factory is not None:
            return client_factory(client_id=config.client_id)

        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover - depends on local environment
            raise RuntimeError(
                "paho-mqtt is required for MQTT publishing. "
                "Install dependencies with: uv sync --dev"
            ) from exc

        return mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id or "",
        )


def open_mqtt_publisher(config: MqttConfig) -> MqttPublisher:
    """Open a long-lived MQTT publisher for the bridge runtime."""

    return MqttPublisher(config)


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
