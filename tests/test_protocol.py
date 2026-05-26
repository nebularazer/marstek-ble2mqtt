import pytest

from marstek_ble_mqtt.protocol import (
    build_command_frame,
    is_response_for_command,
    parse_read_command,
)


def test_build_command_frame_bms_data() -> None:
    assert build_command_frame(0x14) == bytes.fromhex("7305231441")


def test_parse_read_command_accepts_name_and_hex_code() -> None:
    assert parse_read_command("bms-data").code == 0x14
    assert parse_read_command("0x14").name == "bms-data"


def test_parse_read_command_rejects_unknown_write_command() -> None:
    with pytest.raises(ValueError, match="not in the safe read allowlist"):
        parse_read_command("0x25")


@pytest.mark.parametrize(
    "value",
    [
        "runtime-info",
        "0x03",
        "device-info",
        "wifi-ssid",
        "system-data",
        "timer-info",
        "config-data",
        "logs",
        "meter-ip",
        "ct-polling-rate",
        "network-info",
        "local-api-status",
    ],
)
def test_parse_read_command_rejects_reference_commands(value: str) -> None:
    with pytest.raises(ValueError):
        parse_read_command(value)


def test_is_response_for_command_checks_header_command_and_checksum() -> None:
    frame = build_command_frame(0x03)

    assert is_response_for_command(frame, 0x03)
    assert not is_response_for_command(frame, 0x14)
    assert not is_response_for_command(bytes.fromhex("7305230300"), 0x03)
