"""Terminal output helpers for samples and operational events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from marstek_ble_mqtt.telemetry_projection import payload_to_json


def print_sample_json(
    sample: dict[str, Any],
    *,
    flush: bool = False,
) -> None:
    """Print one projected telemetry sample as JSON."""

    print(payload_to_json(sample), flush=flush)


def format_json_event(
    level: str,
    event: str,
    **fields: Any,
) -> str:
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        "level": level,
        "event": event,
        **_jsonable(fields),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def print_json_event(level: str, event: str, **fields: Any) -> None:
    print(format_json_event(level, event, **fields), flush=True)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            key: item
            for key, item in ((key, _jsonable(item)) for key, item in value.items())
            if item not in ({}, [], ())
        }
    if isinstance(value, (list, tuple)):
        return [item for item in (_jsonable(item) for item in value) if item not in ({}, [], ())]
    return value
