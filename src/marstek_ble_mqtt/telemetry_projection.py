"""Projection of decoded telemetry into publishable JSON payloads."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from marstek_ble_mqtt.models import Telemetry

VALID_PUBLISH_GROUPS = frozenset(
    {
        "battery",
        "pv",
        "grid",
        "temperatures",
        "cells",
        "diagnostics",
        "full",
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
    if "full" in groups:
        return _full_payload(timestamp=timestamp, telemetry=telemetry)

    messages = project_telemetry_messages(
        timestamp=timestamp,
        telemetry=telemetry,
        publish_groups=groups,
    )
    sample: dict[str, Any] = {
        "ts": _timestamp_json(timestamp),
        "frame": _jsonable(asdict(telemetry.frame)),
    }
    for message in messages:
        sample[message.group] = {
            key: value for key, value in message.payload.items() if key != "ts"
        }
    return sample


def payload_to_json(payload: dict[str, Any]) -> str:
    """Return stable compact JSON for an already projected payload."""

    return _stable_json(payload)


def _payload_for_group(*, timestamp: datetime, telemetry: Telemetry, group: str) -> dict[str, Any]:
    if group == "full":
        return _full_payload(timestamp=timestamp, telemetry=telemetry)

    return {
        "ts": _timestamp_json(timestamp),
        **_jsonable(asdict(getattr(telemetry, group))),
    }


def _full_payload(*, timestamp: datetime, telemetry: Telemetry) -> dict[str, Any]:
    payload = _jsonable(asdict(telemetry), strip_empty=False)
    payload.pop("timestamp", None)
    return {"ts": _timestamp_json(timestamp), **payload}


def _stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _timestamp_json(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).isoformat()


def _jsonable(value: Any, *, strip_empty: bool = True) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        result = {
            key: _jsonable(item, strip_empty=strip_empty)
            for key, item in value.items()
            if item is not None
        }
        if strip_empty:
            return {key: item for key, item in result.items() if item not in ({}, [], ())}
        return result
    if isinstance(value, (list, tuple)):
        return [
            item
            for item in (_jsonable(item, strip_empty=strip_empty) for item in value)
            if not strip_empty or item not in ({}, [], ())
        ]
    return value
