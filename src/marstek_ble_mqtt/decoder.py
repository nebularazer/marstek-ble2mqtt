"""Shared Marstek/Hame BLE response frame validation."""

from __future__ import annotations

from dataclasses import dataclass

from marstek_ble_mqtt.protocol import FRAME_START, FRAME_TYPE, xor_checksum


@dataclass(frozen=True)
class DecodedFrame:
    """Validated BLE response frame."""

    command: int
    payload: bytes
    checksum_valid: bool
    length_valid: bool


def decode_frame(frame: bytes | bytearray) -> DecodedFrame:
    """Decode and validate a raw Marstek BLE response frame."""

    data = bytes(frame)
    if len(data) < 5:
        raise ValueError("frame is too short")
    if data[0] != FRAME_START or data[2] != FRAME_TYPE:
        raise ValueError("frame header is invalid")

    return DecodedFrame(
        command=data[3],
        payload=data[4:-1],
        checksum_valid=data[-1] == xor_checksum(data[:-1]),
        length_valid=data[1] == len(data),
    )
