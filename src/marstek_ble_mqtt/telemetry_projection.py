"""Projection of decoded telemetry into publishable JSON payloads."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from marstek_ble_mqtt.models import CellData, DiagnosticData, PvData, Telemetry

VALID_PUBLISH_GROUPS = frozenset(
    {
        "battery",
        "pv",
        "inverter",
        "temperatures",
        "cells",
        "diagnostics",
    }
)


@dataclass(frozen=True)
class ProjectionMessage:
    """One telemetry payload destined for a topic suffix."""

    group: str
    topic_suffix: str
    payload: dict[str, Any]
    payload_json: str


def validate_publish_groups(groups: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize and validate configured telemetry publish groups."""

    normalized = tuple(dict.fromkeys(group.strip().lower() for group in groups if group.strip()))
    if not normalized:
        raise ValueError(
            "No MQTT publish groups configured. Set [mqtt].publish_groups to one or more of: "
            f"{', '.join(sorted(VALID_PUBLISH_GROUPS))}."
        )

    invalid = sorted(set(normalized) - VALID_PUBLISH_GROUPS)
    if invalid:
        raise ValueError(
            "Unknown MQTT publish group(s): "
            f"{', '.join(invalid)}. Valid groups: {', '.join(sorted(VALID_PUBLISH_GROUPS))}."
        )
    return normalized


def project_telemetry_messages(
    *,
    timestamp: datetime,
    telemetry: Telemetry,
    publish_groups: tuple[str, ...],
) -> tuple[ProjectionMessage, ...]:
    """Return per-group telemetry messages with stable JSON payloads."""

    groups = validate_publish_groups(publish_groups)
    return tuple(
        ProjectionMessage(
            group=group,
            topic_suffix=group,
            payload=payload,
            payload_json=_stable_json(payload),
        )
        for group in groups
        for payload in (_payload_for_group(timestamp=timestamp, telemetry=telemetry, group=group),)
    )


def project_sample_payload(
    *,
    timestamp: datetime,
    telemetry: Telemetry,
    publish_groups: tuple[str, ...],
) -> dict[str, Any]:
    """Return the single stdout sample payload for configured publish groups."""

    groups = validate_publish_groups(publish_groups)
    sample: dict[str, Any] = {
        "ts": _timestamp_json(timestamp),
    }
    sample.update(
        {
            f"frame_{key}": value
            for key, value in _flat_scalar_mapping(asdict(telemetry.frame)).items()
        }
    )
    for group in groups:
        for key, value in _flat_payload_for_group(telemetry=telemetry, group=group).items():
            sample[_sample_field_name(group, key)] = value
    return sample


def payload_to_json(payload: dict[str, Any]) -> str:
    """Return stable compact JSON for an already projected payload."""

    return _stable_json(payload)


def _payload_for_group(*, timestamp: datetime, telemetry: Telemetry, group: str) -> dict[str, Any]:
    return {
        "ts": _timestamp_json(timestamp),
        **_flat_payload_for_group(telemetry=telemetry, group=group),
    }


def _flat_payload_for_group(*, telemetry: Telemetry, group: str) -> dict[str, Any]:
    data = getattr(telemetry, group)
    if isinstance(data, PvData):
        return _flat_pv_payload(data)
    if isinstance(data, CellData):
        return _flat_cell_payload(data)
    if isinstance(data, DiagnosticData):
        return _flat_scalar_mapping(asdict(data))
    return _flat_scalar_mapping(asdict(data))


def _flat_pv_payload(pv: PvData) -> dict[str, Any]:
    payload = _flat_scalar_mapping(
        {
            "total_power_w": pv.total_power_w,
            "mppt_state": pv.mppt_state,
            "mppt_error": pv.mppt_error,
            "mppt_warning": pv.mppt_warning,
            "mppt_temperature_c": pv.mppt_temperature_c,
        }
    )
    for pv_string in pv.strings:
        prefix = f"pv{pv_string.index}"
        payload.update(
            _flat_scalar_mapping(
                {
                    f"{prefix}_voltage_v": pv_string.voltage_v,
                    f"{prefix}_current_a": pv_string.current_a,
                    f"{prefix}_power_w": pv_string.power_w,
                }
            )
        )
    return payload


def _flat_cell_payload(cells: CellData) -> dict[str, Any]:
    payload = _flat_scalar_mapping(
        {
            "voltage_min_v": cells.voltage_min_v,
            "voltage_max_v": cells.voltage_max_v,
            "voltage_avg_v": cells.voltage_avg_v,
            "voltage_delta_v": cells.voltage_delta_v,
        }
    )
    for index, voltage in enumerate(cells.voltages_v, start=1):
        if voltage is not None:
            payload[f"cell{index:02d}_voltage_v"] = voltage
    for index, temperature in enumerate(cells.temperatures_c, start=1):
        if temperature is not None:
            payload[f"pack_temp{index:02d}_c"] = temperature
    return payload


def _flat_scalar_mapping(data: dict[str, Any]) -> dict[str, Any]:
    return {key: _project_scalar(value) for key, value in data.items() if _is_scalar(value)}


def _is_scalar(value: Any) -> bool:
    return value is not None and isinstance(value, (str, int, float, bool))


def _project_scalar(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 3)
    return value


def _sample_field_name(group: str, key: str) -> str:
    if group == "pv" and key.startswith("pv"):
        return key
    if group == "cells" and (key.startswith("cell") or key.startswith("pack")):
        return key
    prefix = "cell" if group == "cells" else group
    return f"{prefix}_{key}"


def _stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _timestamp_json(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).isoformat()
