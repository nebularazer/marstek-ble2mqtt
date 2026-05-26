import json
from datetime import UTC, datetime

import pytest

from marstek_ble_mqtt.models import (
    BatteryData,
    FrameMetadata,
    PvData,
    PvStringData,
    Telemetry,
)
from marstek_ble_mqtt.telemetry_projection import (
    project_sample_payload,
    project_telemetry_messages,
    validate_publish_groups,
)


def test_validate_publish_groups_normalizes_and_deduplicates() -> None:
    assert validate_publish_groups((" Battery ", "pv", "battery")) == ("battery", "pv")


def test_validate_publish_groups_rejects_empty_and_unknown() -> None:
    with pytest.raises(ValueError, match="No MQTT publish groups configured"):
        validate_publish_groups(())
    with pytest.raises(ValueError, match="Unknown MQTT publish group"):
        validate_publish_groups(("battery", "summary"))


def test_project_messages_uses_selected_groups_topic_suffixes_and_stable_json() -> None:
    timestamp = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    telemetry = Telemetry(
        timestamp=datetime(2026, 5, 24, 11, 59, tzinfo=UTC),
        frame=FrameMetadata(command="0x14"),
        battery=BatteryData(soc_percent=83.0, power_w=605.68),
        pv=PvData(
            total_power_w=1139.4,
            strings=(PvStringData(index=1, voltage_v=27.7, current_a=None, power_w=294.0),),
        ),
    )

    messages = project_telemetry_messages(
        timestamp=timestamp,
        telemetry=telemetry,
        publish_groups=("battery", "pv"),
    )

    assert [message.group for message in messages] == ["battery", "pv"]
    assert [message.topic_suffix for message in messages] == ["battery", "pv"]
    assert messages[0].payload == {
        "ts": "2026-05-24T12:00:00+00:00",
        "soc_percent": 83.0,
        "power_w": 605.68,
    }
    assert json.loads(messages[1].payload_json)["strings"] == [
        {"index": 1, "voltage_v": 27.7, "power_w": 294.0}
    ]
    assert "current_a" not in messages[1].payload_json


def test_project_sample_payload_includes_frame_once_for_selected_groups() -> None:
    payload = project_sample_payload(
        timestamp=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        telemetry=Telemetry(
            frame=FrameMetadata(command="0x14", checksum_valid=True),
            battery=BatteryData(soc_percent=83.0),
        ),
        publish_groups=("battery",),
    )

    assert payload == {
        "ts": "2026-05-24T12:00:00+00:00",
        "frame": {"command": "0x14", "checksum_valid": True},
        "battery": {"soc_percent": 83.0},
    }


def test_project_sample_payload_full_keeps_empty_fields_and_uses_sample_timestamp() -> None:
    payload = project_sample_payload(
        timestamp=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        telemetry=Telemetry(
            timestamp=datetime(2026, 5, 24, 11, 59, tzinfo=UTC),
            frame=FrameMetadata(command="0x14", payload_length=166),
            battery=BatteryData(soc_percent=83.0),
            raw={"command": "0x14"},
        ),
        publish_groups=("full",),
    )

    assert payload["ts"] == "2026-05-24T12:00:00+00:00"
    assert "timestamp" not in payload
    assert payload["pv"] == {"strings": []}
    assert payload["raw"] == {"command": "0x14"}
