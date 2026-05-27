"""Marstek/Hame BLE frame helpers."""

from __future__ import annotations

from dataclasses import dataclass

FRAME_START = 0x73
FRAME_TYPE = 0x23


@dataclass(frozen=True)
class ReadCommand:
    """Known read-style BLE command."""

    code: int
    name: str
    purpose: str


SAFE_READ_COMMANDS: dict[str, ReadCommand] = {
    "bms-data": ReadCommand(0x14, "bms-data", "Live battery/PV/inverter/cell telemetry"),
}

SAFE_READ_COMMAND_CODES = frozenset(command.code for command in SAFE_READ_COMMANDS.values())


def build_command_frame(command: int, payload: bytes = b"") -> bytes:
    """Build a Marstek BLE command frame with XOR checksum."""

    if not 0 <= command <= 0xFF:
        raise ValueError("command must fit in one byte")

    frame = bytearray([FRAME_START, 0x00, FRAME_TYPE, command])
    frame.extend(payload)
    frame[1] = len(frame) + 1
    frame.append(xor_checksum(frame))
    return bytes(frame)


def xor_checksum(data: bytes | bytearray) -> int:
    """Return XOR checksum for bytes."""

    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum


def parse_read_command(value: str) -> ReadCommand:
    """Parse a known safe read command name or numeric command code."""

    normalized = value.strip().lower()
    if normalized in SAFE_READ_COMMANDS:
        return SAFE_READ_COMMANDS[normalized]

    try:
        code = int(normalized, 16 if normalized.startswith("0x") else 10)
    except ValueError as exc:
        raise ValueError(f"unknown read command: {value}") from exc

    for command in SAFE_READ_COMMANDS.values():
        if command.code == code:
            return command

    safe_names = ", ".join(SAFE_READ_COMMANDS)
    raise ValueError(f"command 0x{code:02x} is not in the safe read allowlist: {safe_names}")


def ensure_safe_read_command(command: ReadCommand) -> ReadCommand:
    """Return the command only if it is in the read telemetry allowlist."""

    if command.code not in SAFE_READ_COMMAND_CODES:
        safe_names = ", ".join(SAFE_READ_COMMANDS)
        raise ValueError(
            f"command 0x{command.code:02x} is not in the safe read allowlist: {safe_names}"
        )
    return command


def is_response_for_command(frame: bytes | bytearray, command: int) -> bool:
    """Return whether a notification frame appears to answer a command."""

    return (
        len(frame) >= 5
        and frame[0] == FRAME_START
        and frame[2] == FRAME_TYPE
        and frame[3] == command
        and frame[-1] == xor_checksum(frame[:-1])
    )
