from datetime import UTC, datetime
from struct import pack_into

from marstek_ble_mqtt.decoder import decode_frame
from marstek_ble_mqtt.profiles.jupiter_hmm import decode_telemetry_frame
from marstek_ble_mqtt.protocol import build_command_frame


def _u16(payload: bytearray, offset: int, value: int) -> None:
    pack_into("<H", payload, offset, value)


def _i16(payload: bytearray, offset: int, value: int) -> None:
    pack_into("<h", payload, offset, value)


def _build_runtime_info_frame() -> str:
    payload = bytearray(71)
    payload[15] = 0x01
    return build_command_frame(0x03, payload).hex()


def _build_bms_data_frame() -> str:
    payload = bytearray(166)

    _u16(payload, 0, 7)
    _u16(payload, 6, 2465)
    _i16(payload, 8, 0)
    _u16(payload, 10, 0)
    _u16(payload, 12, 5001)
    _u16(payload, 14, 531)
    _i16(payload, 16, 613)
    _i16(payload, 18, 48)

    _u16(payload, 32, 244)
    _u16(payload, 34, 0)
    _i16(payload, 36, 46)
    _u16(payload, 38, 0)
    for offset, values in zip(
        range(40, 64, 6),
        (
            (277, 85, 2383),
            (292, 56, 1662),
            (280, 89, 2524),
            (300, 77, 2332),
        ),
        strict=True,
    ):
        for value_offset, value in zip((0, 2, 4), values, strict=True):
            _u16(payload, offset + value_offset, value)

    _u16(payload, 80, 529)
    _i16(payload, 82, 166)
    _u16(payload, 84, 223)
    _u16(payload, 86, 168)
    _u16(payload, 88, 581)
    _u16(payload, 90, 500)
    _u16(payload, 92, 500)
    _u16(payload, 94, 46)
    _u16(payload, 96, 97)
    _u16(payload, 98, 2560)
    _i16(payload, 100, 113)
    _u16(payload, 102, 5298)
    _i16(payload, 104, 30)
    _u16(payload, 106, 310)
    _u16(payload, 108, 0)
    _u16(payload, 110, 0)
    _u16(payload, 112, 0)
    _u16(payload, 114, 0)
    _u16(payload, 116, 192)
    _u16(payload, 118, 1)
    _u16(payload, 120, 1177)

    cell_voltages = (
        3314,
        3313,
        3312,
        3315,
        3313,
        3313,
        3313,
        3313,
        3312,
        3314,
        3312,
        3313,
        3312,
        3315,
        3312,
        3314,
    )
    for index, value in enumerate(cell_voltages):
        _u16(payload, 122 + index * 2, value)

    for index, value in enumerate((31, 30, 30, 31)):
        _i16(payload, 154 + index * 2, value)
    _i16(payload, 162, 38)
    _i16(payload, 164, 31)

    return build_command_frame(0x14, payload).hex()


RUNTIME_INFO_FRAME = _build_runtime_info_frame()
BMS_DATA_FRAME = _build_bms_data_frame()


def test_decode_frame_validates_runtime_response() -> None:
    decoded = decode_frame(bytes.fromhex(RUNTIME_INFO_FRAME))

    assert decoded.command == 0x03
    assert len(decoded.payload) == 71
    assert decoded.checksum_valid is True
    assert decoded.length_valid is True


def test_decode_runtime_frame_keeps_reference_fields_raw() -> None:
    telemetry = decode_telemetry_frame(
        bytes.fromhex(RUNTIME_INFO_FRAME),
        timestamp=datetime(2026, 5, 24, 8, 53, 20, tzinfo=UTC),
    )

    assert telemetry.timestamp.isoformat() == "2026-05-24T08:53:20+00:00"
    assert telemetry.soc_percent is None
    assert telemetry.frame.command == "0x03"
    assert telemetry.raw["command"] == "0x03"
    assert telemetry.raw["reference"]["wifi_connected"] is True


def test_decode_bms_frame_uses_experimental_hmm_offsets() -> None:
    telemetry = decode_telemetry_frame(
        bytes.fromhex(BMS_DATA_FRAME),
        timestamp=datetime(2026, 5, 24, 8, 54, 18, tzinfo=UTC),
    )

    hmm = telemetry.raw["hmm_bms_v1_experimental"]
    assert telemetry.frame.command == "0x14"
    assert telemetry.battery.soc_percent == 46.0
    assert telemetry.battery.soh_percent == 97.0
    assert telemetry.battery.voltage_v == 52.98
    assert telemetry.battery.current_a == 11.3
    assert round(telemetry.battery.power_w or 0, 1) == 598.7
    assert telemetry.battery.state == "discharging"
    assert telemetry.battery.design_capacity_wh == 2560.0
    assert telemetry.battery.charge_current_limit_a == 50.0
    assert telemetry.battery.discharge_current_limit_a == 50.0
    assert telemetry.inverter.voltage_v == 246.5
    assert telemetry.inverter.frequency_hz == 50.01
    assert telemetry.inverter.power_w == 613.0
    assert telemetry.inverter.inverter_temperature_c == 48.0
    assert telemetry.pv.strings[0].voltage_v == 27.7
    assert telemetry.pv.strings[0].current_a == 8.5
    assert telemetry.pv.strings[0].power_w == 238.3
    assert telemetry.pv1_power_w == 238.3
    assert telemetry.pv2_power_w == 166.2
    assert telemetry.pv3_power_w == 252.4
    assert telemetry.pv4_power_w == 233.2
    assert round(telemetry.pv.total_power_w or 0, 1) == 890.1
    assert telemetry.temperatures.mppt_c == 46.0
    assert telemetry.temperatures.cell_average_c == 30.5
    assert telemetry.temperatures.environment_c == 38.0
    assert telemetry.temperatures.tail_mosfet_c == 31.0
    assert not hasattr(telemetry.temperatures, "battery_unconfirmed_c")
    assert list(telemetry.cells.voltages_v[:4]) == [3.314, 3.313, 3.312, 3.315]
    assert round(telemetry.cells.voltage_delta_v or 0, 3) == 0.003
    assert telemetry.cells.temperatures_c == (31.0, 30.0, 30.0, 31.0)
    assert telemetry.diagnostics.mppt_error == 0
    assert telemetry.diagnostics.bms_error == 0
    assert telemetry.diagnostics.bms_warning == 0
    assert telemetry.diagnostics.cell_flag == 192
    assert telemetry.diagnostics.bms_number == 1
    assert telemetry.diagnostics.battery_temp_unconfirmed_c == 30.0
    assert "20" in telemetry.diagnostics.inverter_unknown_words
    assert telemetry.diagnostics.bms_unknown_words == {"120": {"u16": 1177, "i16": 1177}}
    assert hmm["mppt"]["pv"][0] == {"voltage_v": 27.7, "current_a": 8.5, "power_w": 238.3}
    assert hmm["raw_field_values"]["inverter"]["g_vol"] == 2465
    assert hmm["raw_field_values"]["mppt"]["pv1"] == "277|85|2383"
    assert hmm["raw_field_values"]["mppt"]["b_vol"] == 529
    assert hmm["raw_field_values"]["bms"]["b_vol"] == 5298
    assert hmm["raw_field_values"]["bms"]["vol0"] == 3314
    assert hmm["raw_field_values"]["bms"]["b_temp0"] == 31
    assert hmm["raw_field_values"]["bms"]["mos_t"] == 31
