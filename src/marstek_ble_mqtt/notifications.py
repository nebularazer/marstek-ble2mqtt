"""BLE notification frame helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class NotificationFrame:
    """A BLE notification or indication frame."""

    timestamp: str
    characteristic_uuid: str
    payload_hex: str
    ascii_preview: str


def make_notification_frame(
    *,
    characteristic_uuid: str,
    payload: bytes | bytearray,
    timestamp: datetime | None = None,
) -> NotificationFrame:
    """Create a frame model from raw BLE notification bytes."""

    timestamp = timestamp or datetime.now(UTC)
    payload_bytes = bytes(payload)
    return NotificationFrame(
        timestamp=timestamp.isoformat(),
        characteristic_uuid=characteristic_uuid,
        payload_hex=payload_bytes.hex(),
        ascii_preview=_ascii_preview(payload_bytes),
    )


def _ascii_preview(payload: bytes) -> str:
    return re.sub(r"[^ -~]", ".", payload.decode("latin1", errors="replace"))
