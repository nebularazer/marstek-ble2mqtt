import json
from datetime import UTC, datetime

import pytest

from marstek_ble_mqtt.models import (
    BatteryData,
    CellData,
    DiagnosticData,
    FrameMetadata,
    PvData,
    PvStringData,
    Telemetry,
)
from marstek_ble_mqtt.telemetry_projection import (
    project_stdout_sample,
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
    with pytest.raises(ValueError, match="Unknown MQTT publish group"):
        validate_publish_groups(("grid",))


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
    assert json.loads(messages[1].payload_json) == {
        "ts": "2026-05-24T12:00:00+00:00",
        "total_power_w": 1139.4,
        "pv1_voltage_v": 27.7,
        "pv1_power_w": 294.0,
    }
    assert "current_a" not in messages[1].payload_json


def test_project_stdout_sample_nests_frame_and_selected_groups() -> None:
    payload = project_stdout_sample(
        timestamp=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        telemetry=Telemetry(
            frame=FrameMetadata(command="0x14", checksum_valid=True),
            battery=BatteryData(soc_percent=83.0),
        ),
        publish_groups=("battery",),
    )

    assert payload == {
        "ts": "2026-05-24T12:00:00+00:00",
        "frame": {
            "command": "0x14",
            "checksum_valid": True,
        },
        "battery": {
            "soc_percent": 83.0,
        },
    }


def test_projected_payloads_round_float_artifacts_without_changing_telemetry() -> None:
    timestamp = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    telemetry = Telemetry(
        battery=BatteryData(power_w=609.8610000000001),
        pv=PvData(total_power_w=1017.5999999999999),
    )

    messages = project_telemetry_messages(
        timestamp=timestamp,
        telemetry=telemetry,
        publish_groups=("battery", "pv"),
    )
    sample = project_stdout_sample(
        timestamp=timestamp,
        telemetry=telemetry,
        publish_groups=("battery", "pv"),
    )

    assert messages[0].payload["power_w"] == 609.861
    assert messages[1].payload["total_power_w"] == 1017.6
    assert sample["battery"]["power_w"] == 609.861
    assert sample["pv"]["total_power_w"] == 1017.6
    assert telemetry.pv.total_power_w == 1017.5999999999999


def test_projected_cells_use_pack_temperature_sensor_names() -> None:
    timestamp = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    telemetry = Telemetry(
        cells=CellData(
            voltages_v=(3.314,),
            temperatures_c=(31.0, 30.0),
            voltage_delta_v=0.008000000000000007,
        ),
        diagnostics=DiagnosticData(battery_temp_unconfirmed_c=74.0),
    )

    messages = project_telemetry_messages(
        timestamp=timestamp,
        telemetry=telemetry,
        publish_groups=("cells", "diagnostics"),
    )
    sample = project_stdout_sample(
        timestamp=timestamp,
        telemetry=telemetry,
        publish_groups=("cells", "diagnostics"),
    )

    assert messages[0].payload["cell01_voltage_v"] == 3.314
    assert messages[0].payload["pack_temp01_c"] == 31.0
    assert messages[0].payload["voltage_delta_v"] == 0.008
    assert "cell_temp01_c" not in messages[0].payload
    assert sample["cells"]["pack_temp01_c"] == 31.0
    assert sample["diagnostics"]["battery_temp_unconfirmed_c"] == 74.0


def test_project_stdout_sample_omits_empty_selected_groups() -> None:
    payload = project_stdout_sample(
        timestamp=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        telemetry=Telemetry(),
        publish_groups=("battery", "pv"),
    )

    assert payload == {"ts": "2026-05-24T12:00:00+00:00"}


def test_full_publish_group_is_not_supported() -> None:
    with pytest.raises(ValueError, match="Unknown MQTT publish group"):
        project_stdout_sample(
            timestamp=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
            telemetry=Telemetry(),
            publish_groups=("full",),
        )
