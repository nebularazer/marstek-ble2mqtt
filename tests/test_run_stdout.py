from datetime import UTC, datetime

from marstek_ble_mqtt.models import (
    BatteryData,
    FrameMetadata,
    PvData,
    PvStringData,
    Telemetry,
)
from marstek_ble_mqtt.output import format_json_event, print_sample_json
from marstek_ble_mqtt.telemetry_projection import project_sample_payload


def test_format_sample_json_includes_selected_groups_only() -> None:
    payload = project_sample_payload(
        timestamp=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        telemetry=Telemetry(
            timestamp=datetime(2026, 5, 24, 11, 59, tzinfo=UTC),
            frame=FrameMetadata(command="0x14", checksum_valid=True, length_valid=True),
            battery=BatteryData(soc_percent=83.0, power_w=605.68),
            pv=PvData(
                total_power_w=1139.4,
                strings=(
                    PvStringData(index=1, voltage_v=27.7, current_a=10.6, power_w=294.0),
                    PvStringData(index=2, voltage_v=29.2, current_a=8.0, power_w=232.9),
                ),
            ),
        ),
        publish_groups=("battery", "pv"),
    )

    assert payload == {
        "ts": "2026-05-24T12:00:00+00:00",
        "frame_command": "0x14",
        "frame_checksum_valid": True,
        "frame_length_valid": True,
        "battery_soc_percent": 83.0,
        "battery_power_w": 605.68,
        "pv1_voltage_v": 27.7,
        "pv1_current_a": 10.6,
        "pv1_power_w": 294.0,
        "pv2_voltage_v": 29.2,
        "pv2_current_a": 8.0,
        "pv2_power_w": 232.9,
        "pv_total_power_w": 1139.4,
    }
    assert "grid" not in payload


def test_format_sample_json_full_includes_complete_telemetry() -> None:
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
    assert payload["frame"]["payload_length"] == 166
    assert payload["battery"]["soc_percent"] == 83.0
    assert payload["pv"] == {"strings": []}
    assert payload["raw"] == {"command": "0x14"}
    assert "timestamp" not in payload


def test_print_sample_json_writes_compact_json(capsys) -> None:
    print_sample_json(
        {"ts": "2026-05-24T12:00:00+00:00", "battery_soc_percent": 83.0},
    )

    assert capsys.readouterr().out == (
        '{"battery_soc_percent":83.0,"ts":"2026-05-24T12:00:00+00:00"}\n'
    )


def test_format_json_event_writes_structured_operational_log() -> None:
    output = format_json_event(
        "warning",
        "sample_failed",
        error_type="TimeoutError",
        error="timed out",
        reconnecting=True,
    )

    assert '"event":"sample_failed"' in output
    assert '"level":"warning"' in output
    assert '"error_type":"TimeoutError"' in output
    assert '"reconnecting":true' in output
