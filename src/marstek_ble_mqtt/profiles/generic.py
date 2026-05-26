"""Generic raw-frame profile decoder."""

from __future__ import annotations

from datetime import UTC, datetime

from marstek_ble_mqtt.decoder import decode_frame
from marstek_ble_mqtt.models import FrameMetadata, Telemetry


def decode_generic_frame(frame: bytes | bytearray) -> Telemetry:
    """Validate and preserve a frame without guessing normalized telemetry."""

    decoded = decode_frame(frame)
    frame_metadata = FrameMetadata(
        command=f"0x{decoded.command:02x}",
        payload_length=len(decoded.payload),
        checksum_valid=decoded.checksum_valid,
        length_valid=decoded.length_valid,
    )
    return Telemetry(
        timestamp=datetime.now(UTC),
        frame=frame_metadata,
        raw={
            "decoder": "generic",
            "command": f"0x{decoded.command:02x}",
            "payload_length": len(decoded.payload),
            "checksum_valid": decoded.checksum_valid,
            "length_valid": decoded.length_valid,
            "payload_hex": decoded.payload.hex(),
        },
    )
