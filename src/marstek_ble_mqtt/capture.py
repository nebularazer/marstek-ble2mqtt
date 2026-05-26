"""Capture hooks for explicit local debugging."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ProtocolWriteCaptureRecord:
    """One protocol write emitted by the BLE transport Adapter."""

    timestamp: datetime
    purpose: str
    characteristic_uuid: str
    payload_hex: str

    def to_jsonable(self) -> dict[str, str]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


class ProtocolWriteJsonlCapture:
    """Append protocol write capture records as JSON lines."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def __call__(self, record: ProtocolWriteCaptureRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as capture_file:
            capture_file.write(
                json.dumps(record.to_jsonable(), sort_keys=True, separators=(",", ":")) + "\n"
            )
