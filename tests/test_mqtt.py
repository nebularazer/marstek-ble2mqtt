import json
from datetime import UTC, datetime

import pytest

from marstek_ble_mqtt.mqtt import MqttConfig, MqttPublisher, publish_messages_with_client
from marstek_ble_mqtt.profiles.jupiter_hmm import decode_telemetry_frame
from marstek_ble_mqtt.telemetry_projection import project_telemetry_messages
from tests.test_decoder import BMS_DATA_FRAME


class FakeMqttClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, bool]] = []

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        self.messages.append((topic, payload, retain))


class FakePersistentClient:
    def __init__(self, *, client_id: str | None = None) -> None:
        self.client_id = client_id
        self.username: str | None = None
        self.password: str | None = None
        self.reconnect_delay: tuple[int, int] | None = None
        self.connected: tuple[str, int, int] | None = None
        self.loop_started = False
        self.loop_stopped = False
        self.disconnected = False
        self.messages: list[tuple[str, str, bool]] = []

    def username_pw_set(self, username: str, password: str | None = None) -> None:
        self.username = username
        self.password = password

    def reconnect_delay_set(self, *, min_delay: int, max_delay: int) -> None:
        self.reconnect_delay = (min_delay, max_delay)

    def connect(self, host: str, port: int, keepalive: int) -> None:
        self.connected = (host, port, keepalive)

    def loop_start(self) -> None:
        self.loop_started = True

    def loop_stop(self) -> None:
        self.loop_stopped = True

    def disconnect(self) -> None:
        self.disconnected = True

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        self.messages.append((topic, payload, retain))


def test_publish_messages_with_client_publishes_configured_group_json_topics() -> None:
    client = FakeMqttClient()
    telemetry = decode_telemetry_frame(
        bytes.fromhex(BMS_DATA_FRAME),
        timestamp=datetime(2026, 5, 24, 10, 0, tzinfo=UTC),
    )

    messages_to_publish = project_telemetry_messages(
        timestamp=telemetry.timestamp,
        telemetry=telemetry,
        publish_groups=("battery", "pv"),
    )
    topics = publish_messages_with_client(
        client,
        "marstek",
        messages_to_publish,
    )

    messages = {topic: json.loads(payload) for topic, payload, _ in client.messages}
    assert topics == ["marstek/battery", "marstek/pv"]
    assert messages["marstek/battery"]["ts"] == "2026-05-24T10:00:00+00:00"
    assert "source" not in messages["marstek/battery"]
    assert messages["marstek/battery"]["soc_percent"] == 46.0
    assert messages["marstek/battery"]["voltage_v"] == 52.98
    assert messages["marstek/battery"]["power_w"] == 598.674
    assert messages["marstek/pv"]["total_power_w"] == 890.1
    assert messages["marstek/pv"]["pv1_voltage_v"] == 27.7
    assert messages["marstek/pv"]["pv4_power_w"] == 233.2
    assert "marstek/inverter" not in messages
    assert "marstek/full" not in messages


def test_persistent_publisher_opens_once_and_closes() -> None:
    clients: list[FakePersistentClient] = []

    def fake_client_factory(*, client_id: str | None) -> FakePersistentClient:
        client = FakePersistentClient(client_id=client_id)
        clients.append(client)
        return client

    publisher = MqttPublisher(
        MqttConfig(
            host="mqtt.example.test",
            port=1884,
            username="user",
            password="secret",
            client_id="battery-bridge",
            topic_prefix="marstek/test",
        ),
        client_factory=fake_client_factory,
    )

    publisher.close()
    publisher.close()

    assert len(clients) == 1
    client = clients[0]
    assert client.client_id == "battery-bridge"
    assert client.username == "user"
    assert client.password == "secret"
    assert client.reconnect_delay == (1, 60)
    assert client.connected == ("mqtt.example.test", 1884, 30)
    assert client.loop_started is True
    assert client.loop_stopped is True
    assert client.disconnected is True


def test_persistent_publisher_delegates_publish() -> None:
    client = FakePersistentClient(client_id="battery-bridge")
    publisher = MqttPublisher(
        MqttConfig(client_id="battery-bridge", topic_prefix="marstek/test"),
        client_factory=lambda *, client_id: client,
    )
    telemetry = decode_telemetry_frame(
        bytes.fromhex(BMS_DATA_FRAME),
        timestamp=datetime(2026, 5, 24, 10, 0, tzinfo=UTC),
    )
    messages_to_publish = project_telemetry_messages(
        timestamp=telemetry.timestamp,
        telemetry=telemetry,
        publish_groups=("battery",),
    )

    topics = publisher.publish(messages_to_publish)

    assert topics == ["marstek/test/battery"]
    assert client.messages[0][0] == "marstek/test/battery"


def test_publish_messages_with_client_filters_detailed_groups_independently() -> None:
    client = FakeMqttClient()
    telemetry = decode_telemetry_frame(bytes.fromhex(BMS_DATA_FRAME))

    messages_to_publish = project_telemetry_messages(
        timestamp=telemetry.timestamp,
        telemetry=telemetry,
        publish_groups=("inverter", "temperatures", "cells", "diagnostics"),
    )
    publish_messages_with_client(
        client,
        "marstek",
        messages_to_publish,
    )

    messages = {topic: json.loads(payload) for topic, payload, _ in client.messages}
    assert messages["marstek/inverter"]["frequency_hz"] == 50.01
    assert messages["marstek/temperatures"]["environment_c"] == 38.0
    assert messages["marstek/cells"]["cell01_voltage_v"] == 3.314
    assert messages["marstek/cells"]["pack_temp01_c"] == 31.0
    assert messages["marstek/diagnostics"]["mppt_error"] == 0
    assert messages["marstek/diagnostics"]["bms_error"] == 0
    assert messages["marstek/diagnostics"]["battery_temp_unconfirmed_c"] == 30.0
    assert messages["marstek/diagnostics"]["cell_flag"] == 192
    assert messages["marstek/diagnostics"]["bms_number"] == 1
    assert "battery_unconfirmed_c" not in messages["marstek/temperatures"]
    assert "cell_temp01_c" not in messages["marstek/cells"]
    assert "inverter_unknown_words" not in messages["marstek/diagnostics"]
    assert "marstek/battery" not in messages
    assert "marstek/pv" not in messages


def test_project_messages_requires_publish_groups() -> None:
    with pytest.raises(ValueError, match="No MQTT publish groups configured"):
        project_telemetry_messages(
            timestamp=datetime(2026, 5, 24, 10, 0, tzinfo=UTC),
            telemetry=decode_telemetry_frame(bytes.fromhex(BMS_DATA_FRAME)),
            publish_groups=(),
        )


def test_project_messages_rejects_unknown_publish_groups() -> None:
    with pytest.raises(ValueError, match="Unknown MQTT publish group"):
        project_telemetry_messages(
            timestamp=datetime(2026, 5, 24, 10, 0, tzinfo=UTC),
            telemetry=decode_telemetry_frame(bytes.fromhex(BMS_DATA_FRAME)),
            publish_groups=("battery", "grid"),
        )
