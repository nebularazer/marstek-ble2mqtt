import json
from datetime import UTC, datetime

import pytest

from marstek_ble_mqtt.mqtt import publish_messages_with_client
from marstek_ble_mqtt.profiles.jupiter_hmm import decode_telemetry_frame
from marstek_ble_mqtt.telemetry_projection import project_telemetry_messages
from tests.test_decoder import BMS_DATA_FRAME


class FakeMqttClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, bool]] = []

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
    assert "marstek/grid" not in messages
    assert "marstek/full" not in messages


def test_publish_messages_with_client_filters_detailed_groups_independently() -> None:
    client = FakeMqttClient()
    telemetry = decode_telemetry_frame(bytes.fromhex(BMS_DATA_FRAME))

    messages_to_publish = project_telemetry_messages(
        timestamp=telemetry.timestamp,
        telemetry=telemetry,
        publish_groups=("grid", "temperatures", "cells", "diagnostics"),
    )
    publish_messages_with_client(
        client,
        "marstek",
        messages_to_publish,
    )

    messages = {topic: json.loads(payload) for topic, payload, _ in client.messages}
    assert messages["marstek/grid"]["frequency_hz"] == 50.01
    assert messages["marstek/temperatures"]["environment_c"] == 38.0
    assert messages["marstek/cells"]["cell01_voltage_v"] == 3.314
    assert messages["marstek/diagnostics"]["mppt_error"] == 0
    assert messages["marstek/diagnostics"]["bms_error"] == 0
    assert messages["marstek/diagnostics"]["cell_flag"] == 192
    assert messages["marstek/diagnostics"]["bms_number"] == 1
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
            publish_groups=("battery", "summary"),
        )
