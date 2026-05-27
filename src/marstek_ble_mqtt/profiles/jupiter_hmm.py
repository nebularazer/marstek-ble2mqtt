"""Jupiter C / HMM profile decoder."""

from __future__ import annotations

import struct
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from marstek_ble_mqtt.decoder import decode_frame
from marstek_ble_mqtt.models import (
    BatteryData,
    CellData,
    DiagnosticData,
    FrameMetadata,
    InverterData,
    PvData,
    PvStringData,
    Telemetry,
    TemperatureData,
)


def decode_telemetry_frame(
    frame: bytes | bytearray,
    *,
    timestamp: datetime | None = None,
) -> Telemetry:
    """Decode a response frame into normalized telemetry where known."""

    decoded = decode_frame(frame)
    timestamp = timestamp or datetime.now(UTC)
    raw: dict[str, Any] = {
        "command": f"0x{decoded.command:02x}",
        "payload_length": len(decoded.payload),
        "checksum_valid": decoded.checksum_valid,
        "length_valid": decoded.length_valid,
    }
    frame_metadata = FrameMetadata(
        command=raw["command"],
        payload_length=len(decoded.payload),
        checksum_valid=decoded.checksum_valid,
        length_valid=decoded.length_valid,
    )

    if not decoded.checksum_valid:
        raw["decoder"] = "invalid_checksum"
        return Telemetry(timestamp=timestamp, frame=frame_metadata, raw=raw)

    if decoded.command == 0x03:
        runtime = _decode_runtime_info(decoded.payload)
        raw.update(runtime)
        return Telemetry(timestamp=timestamp, frame=frame_metadata, raw=raw)

    if decoded.command == 0x14:
        bms = _decode_bms_data(decoded.payload)
        raw.update(bms)

        hmm = bms.get("hmm_bms_v1_experimental")
        if isinstance(hmm, dict):
            return _telemetry_from_hmm(
                timestamp=timestamp,
                frame=frame_metadata,
                hmm=hmm,
                raw=raw,
            )
        return Telemetry(timestamp=timestamp, frame=frame_metadata, raw=raw)

    raw["decoder"] = "unsupported_command"
    return Telemetry(timestamp=timestamp, frame=frame_metadata, raw=raw)


def _decode_runtime_info(payload: bytes) -> dict[str, Any]:
    raw: dict[str, Any] = {"decoder": "runtime_info_reference"}
    if len(payload) < 37:
        raw["error"] = "payload_too_short"
        return raw

    raw["reference"] = {
        "wifi_connected": bool(payload[15] & 0x01),
        "mqtt_connected": bool(payload[15] & 0x02),
        "out1_active": payload[16] != 0,
        "out1_power_w": float(_u16(payload, 20)),
        "extern1_connected": payload[28] != 0,
        "temp_low_c": _i16(payload, 33) / 10.0,
        "temp_high_c": _i16(payload, 35) / 10.0,
    }

    if len(payload) >= 100:
        raw["reference"].update(
            {
                "grid_power_w": float(_i16(payload, 0)),
                "solar_power_w": float(_i16(payload, 2)),
                "work_mode": payload[4],
                "product_code": _u16(payload, 12),
                "daily_energy_charged_kwh": _u32(payload, 14) / 100.0,
                "monthly_energy_charged_kwh": _u32(payload, 18) / 1000.0,
                "daily_energy_discharged_kwh": _u32(payload, 22) / 100.0,
                "monthly_energy_discharged_kwh": _u32(payload, 26) / 100.0,
                "total_energy_charged_kwh": _u32(payload, 41) / 100.0,
                "total_energy_discharged_kwh": _u32(payload, 45) / 100.0,
                "power_rating_w": _u16(payload, 74),
            }
        )

    raw["note"] = "Runtime offsets are from Venus references; HMM/Jupiter mapping is not confirmed."
    return raw


def _decode_bms_data(payload: bytes) -> dict[str, Any]:
    raw: dict[str, Any] = {"decoder": "bms_data"}
    if len(payload) < 80:
        raw["error"] = "payload_too_short"
        return raw

    raw["venus_reference"] = _decode_venus_bms_reference(payload)

    hmm = _decode_hmm_bms_experimental(payload)
    if hmm is not None:
        raw["hmm_bms_v1_experimental"] = hmm
    else:
        raw["note"] = "Payload does not match the experimental HMM/Jupiter BMS shape."

    return raw


def _decode_venus_bms_reference(payload: bytes) -> dict[str, Any]:
    cells = [_u16(payload, 48 + index * 2) / 1000.0 for index in range(16)]
    return {
        "bms_version": _u16(payload, 0),
        "voltage_limit_v": _u16(payload, 2) / 10.0,
        "charge_current_limit_a": _u16(payload, 4) / 10.0,
        "discharge_current_limit_a": _i16(payload, 6) / 10.0,
        "soc_percent": float(_u16(payload, 8)),
        "soh_percent": float(_u16(payload, 10)),
        "design_capacity_wh": float(_u16(payload, 12)),
        "battery_voltage_v": _u16(payload, 14) / 100.0,
        "battery_current_a": _i16(payload, 16) / 10.0,
        "battery_temp_c": float(_u16(payload, 18)),
        "error_code": _u16(payload, 26),
        "warning_code": _u32(payload, 28),
        "runtime_hours": _u32(payload, 32) / 3600000.0,
        "mosfet_temp_c": float(_u16(payload, 38)),
        "temp_sensor_1_c": float(_u16(payload, 40)),
        "temp_sensor_2_c": float(_u16(payload, 42)),
        "temp_sensor_3_c": float(_u16(payload, 44)),
        "temp_sensor_4_c": float(_u16(payload, 46)),
        "cell_voltages_v": cells,
        "cell_voltage_min_v": min(cells),
        "cell_voltage_max_v": max(cells),
    }


def _decode_hmm_bms_experimental(payload: bytes) -> dict[str, Any] | None:
    if len(payload) < 156:
        return None

    cell_voltages = [_u16(payload, 122 + index * 2) / 1000.0 for index in range(16)]
    plausible_cells = [voltage for voltage in cell_voltages if 2.5 <= voltage <= 4.0]
    if len(plausible_cells) < 12:
        return None

    battery_voltage_v = _u16(payload, 102) / 100.0
    battery_current_a = _i16(payload, 100) / 10.0
    pv_strings = [_decode_hmm_mppt_pv(payload, 40 + index * 6) for index in range(4)]
    cell_temperatures_c = [_i16(payload, 154 + index * 2) for index in range(4)]
    raw_field_values = _decode_raw_field_values(payload)
    return {
        "inverter": {
            "state_word": _u16(payload, 0),
            "grid_voltage_v": _u16(payload, 6) / 10.0,
            "grid_current_a": _i16(payload, 8) / 10.0,
            "grid_power_factor_raw": _u16(payload, 10),
            "grid_frequency_hz": _u16(payload, 12) / 100.0,
            "battery_voltage_v": _u16(payload, 14) / 10.0,
            "grid_power_w": float(_i16(payload, 16)),
            "temperature_c": _temperature_from_int16_word(payload, 18),
            "unknown_words": _word_map(payload, (20, 22, 24, 26, 28, 30)),
        },
        "mppt": {
            "state": _u16(payload, 32),
            "error": _u16(payload, 34),
            "temperature_c": _temperature_from_int16_word(payload, 36),
            "warning": _u16(payload, 38),
            "pv": pv_strings,
            "pv_total_power_w": sum(pv["power_w"] for pv in pv_strings),
            "unknown_words": _word_map(payload, range(64, 80, 2)),
        },
        "voltage_limit_v": _u16(payload, 88) / 10.0,
        "charge_current_limit_a": _u16(payload, 90) / 10.0,
        "discharge_current_limit_a": _u16(payload, 92) / 10.0,
        "soc_percent": float(_u16(payload, 94)),
        "soh_percent": float(_u16(payload, 96)),
        "design_capacity_wh": float(_u16(payload, 98)),
        "battery_current_a": battery_current_a,
        "battery_voltage_v": battery_voltage_v,
        "battery_temp_c_unconfirmed": _temperature_from_int16_word(payload, 104),
        "mosfet_temp_c": _u16(payload, 106) / 10.0,
        "bms_error": _u16(payload, 108),
        "bms_warning": _u16(payload, 110),
        "bms_error2": _u16(payload, 112),
        "bms_warning2": _u16(payload, 114),
        "cell_flag": _u16(payload, 116),
        "bms_number": _u16(payload, 118),
        "unknown_words": _word_map(payload, (120,)),
        "cell_voltages_v": cell_voltages,
        "cell_voltage_min_v": min(cell_voltages),
        "cell_voltage_max_v": max(cell_voltages),
        "cell_voltage_avg_v": sum(cell_voltages) / len(cell_voltages),
        "cell_voltage_delta_v": max(cell_voltages) - min(cell_voltages),
        "cell_temperatures_c": cell_temperatures_c,
        "cell_temperature_avg_c": sum(cell_temperatures_c) / len(cell_temperatures_c),
        "environment_temp_c": _temperature_from_int16_word(payload, 162),
        "tail_mosfet_temp_c": _temperature_from_int16_word(payload, 164),
        "battery_power_w_experimental": battery_voltage_v * battery_current_a,
        "raw_field_values": raw_field_values,
        "note": (
            "Experimental HMM/Jupiter offsets inferred from local BLE captures "
            "and compared with known Jupiter/HMM field names."
        ),
    }


def _telemetry_from_hmm(
    *,
    timestamp: datetime,
    frame: FrameMetadata,
    hmm: dict[str, Any],
    raw: dict[str, Any],
) -> Telemetry:
    power_w = hmm["battery_power_w_experimental"]
    pv = hmm["mppt"]["pv"]
    state = "idle"
    if power_w > 10:
        state = "discharging"
    elif power_w < -10:
        state = "charging"

    pv_strings = tuple(
        PvStringData(
            index=index + 1,
            voltage_v=pv_string["voltage_v"],
            current_a=pv_string["current_a"],
            power_w=pv_string["power_w"],
        )
        for index, pv_string in enumerate(pv)
    )

    inverter = hmm["inverter"]
    mppt = hmm["mppt"]
    cell_temperatures = tuple(float(value) for value in hmm["cell_temperatures_c"])
    note = hmm.get("note")
    notes = (note,) if isinstance(note, str) else ()

    return Telemetry(
        timestamp=timestamp,
        frame=frame,
        battery=BatteryData(
            soc_percent=hmm["soc_percent"],
            soh_percent=hmm["soh_percent"],
            voltage_v=hmm["battery_voltage_v"],
            current_a=hmm["battery_current_a"],
            power_w=power_w,
            state=state,
            design_capacity_wh=hmm["design_capacity_wh"],
            voltage_limit_v=hmm["voltage_limit_v"],
            charge_current_limit_a=hmm["charge_current_limit_a"],
            discharge_current_limit_a=hmm["discharge_current_limit_a"],
        ),
        pv=PvData(
            strings=pv_strings,
            total_power_w=mppt["pv_total_power_w"],
            mppt_state=mppt["state"],
            mppt_error=mppt["error"],
            mppt_warning=mppt["warning"],
            mppt_temperature_c=mppt["temperature_c"],
        ),
        inverter=InverterData(
            inverter_state_word=inverter["state_word"],
            voltage_v=inverter["grid_voltage_v"],
            current_a=inverter["grid_current_a"],
            power_factor_raw=inverter["grid_power_factor_raw"],
            frequency_hz=inverter["grid_frequency_hz"],
            power_w=inverter["grid_power_w"],
            inverter_battery_voltage_v=inverter["battery_voltage_v"],
            inverter_temperature_c=inverter["temperature_c"],
        ),
        temperatures=TemperatureData(
            inverter_c=inverter["temperature_c"],
            mppt_c=mppt["temperature_c"],
            mosfet_c=hmm["mosfet_temp_c"],
            cell_average_c=hmm["cell_temperature_avg_c"],
            cell_temperatures_c=cell_temperatures,
            environment_c=hmm["environment_temp_c"],
            tail_mosfet_c=hmm["tail_mosfet_temp_c"],
        ),
        cells=CellData(
            voltages_v=tuple(hmm["cell_voltages_v"]),
            voltage_min_v=hmm["cell_voltage_min_v"],
            voltage_max_v=hmm["cell_voltage_max_v"],
            voltage_avg_v=hmm["cell_voltage_avg_v"],
            voltage_delta_v=hmm["cell_voltage_delta_v"],
            temperatures_c=cell_temperatures,
        ),
        diagnostics=DiagnosticData(
            inverter_state_word=inverter["state_word"],
            mppt_state=mppt["state"],
            mppt_error=mppt["error"],
            mppt_warning=mppt["warning"],
            bms_error=hmm["bms_error"],
            bms_warning=hmm["bms_warning"],
            bms_error2=hmm["bms_error2"],
            bms_warning2=hmm["bms_warning2"],
            cell_flag=hmm["cell_flag"],
            bms_number=hmm["bms_number"],
            battery_temp_unconfirmed_c=hmm["battery_temp_c_unconfirmed"],
            inverter_unknown_words=inverter["unknown_words"],
            mppt_unknown_words=mppt["unknown_words"],
            bms_unknown_words=hmm["unknown_words"],
            notes=notes,
        ),
        raw=raw,
    )


def _decode_raw_field_values(payload: bytes) -> dict[str, Any]:
    """Return raw named values before normalized unit conversion."""

    pv_fields = {
        f"pv{index + 1}": "|".join(
            str(_u16(payload, 40 + index * 6 + offset)) for offset in (0, 2, 4)
        )
        for index in range(4)
    }
    return {
        "inverter": {
            "g_state": _u16(payload, 0),
            "w_state1": _u16(payload, 2),
            "w_state2": _u16(payload, 4),
            "g_vol": _u16(payload, 6),
            "g_cur": _i16(payload, 8),
            "g_pf": _u16(payload, 10),
            "g_fre": _u16(payload, 12),
            "b_vol": _u16(payload, 14),
            "g_power": _i16(payload, 16),
            "i_temp": _i16(payload, 18),
        },
        "mppt": {
            "m_state": _u16(payload, 32),
            "m_err": _u16(payload, 34),
            "m_temp": _i16(payload, 36),
            "m_war": _u16(payload, 38),
            **pv_fields,
            "b_vol": _u16(payload, 80),
            "b_cur": _i16(payload, 82),
            "base_v": _u16(payload, 84),
            "pe_v": _u16(payload, 86),
        },
        "bms": {
            "c_vol": _u16(payload, 88),
            "c_cur": _u16(payload, 90),
            "d_cur": _u16(payload, 92),
            "soc": _u16(payload, 94),
            "soh": _u16(payload, 96),
            "b_cap": _u16(payload, 98),
            "b_cur": _i16(payload, 100),
            "b_vol": _u16(payload, 102),
            "b_temp": _i16(payload, 104),
            "b_err": _u16(payload, 108),
            "b_war": _u16(payload, 110),
            "b_err2": _u16(payload, 112),
            "b_war2": _u16(payload, 114),
            "c_flag": _u16(payload, 116),
            "b_num": _u16(payload, 118),
            **{f"vol{index}": _u16(payload, 122 + index * 2) for index in range(16)},
            **{f"b_temp{index}": _i16(payload, 154 + index * 2) for index in range(4)},
            "env_t": _i16(payload, 162),
            "mos_t": _i16(payload, 164),
        },
    }


def _decode_hmm_mppt_pv(payload: bytes, offset: int) -> dict[str, float]:
    return {
        "voltage_v": _u16(payload, offset) / 10.0,
        "current_a": _u16(payload, offset + 2) / 10.0,
        "power_w": _u16(payload, offset + 4) / 10.0,
    }


def _temperature_from_int16_word(payload: bytes, offset: int) -> float:
    return float(_i16(payload, offset))


def _word_map(payload: bytes, offsets: Iterable[int]) -> dict[str, dict[str, int]]:
    return {
        str(offset): {
            "u16": _u16(payload, offset),
            "i16": _i16(payload, offset),
        }
        for offset in offsets
    }


def _u16(payload: bytes, offset: int) -> int:
    return struct.unpack_from("<H", payload, offset)[0]


def _i16(payload: bytes, offset: int) -> int:
    return struct.unpack_from("<h", payload, offset)[0]


def _u32(payload: bytes, offset: int) -> int:
    return struct.unpack_from("<I", payload, offset)[0]
