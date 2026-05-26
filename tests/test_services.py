from marstek_ble_mqtt.services import CharacteristicDump, ServiceDump, format_service_dump


def test_format_service_dump_includes_readable_value() -> None:
    service = ServiceDump(
        uuid="0000180a-0000-1000-8000-00805f9b34fb",
        handle=1,
        characteristics=(
            CharacteristicDump(
                uuid="00002a29-0000-1000-8000-00805f9b34fb",
                handle=2,
                properties=("read", "notify"),
                value_hex="4d5354",
            ),
        ),
    )

    output = format_service_dump([service])

    assert "service 0000180a-0000-1000-8000-00805f9b34fb  handle=1" in output
    assert "char 00002a29-0000-1000-8000-00805f9b34fb  handle=2" in output
    assert "properties: read, notify" in output
    assert "value: 4d5354" in output


def test_format_service_dump_does_not_print_value_for_non_readable_characteristic() -> None:
    service = ServiceDump(
        uuid="0000ffe0-0000-1000-8000-00805f9b34fb",
        handle=None,
        characteristics=(
            CharacteristicDump(
                uuid="0000ffe1-0000-1000-8000-00805f9b34fb",
                handle=None,
                properties=("write", "notify"),
            ),
        ),
    )

    output = format_service_dump([service])

    assert "properties: write, notify" in output
    assert "value:" not in output


def test_format_service_dump_reports_read_error() -> None:
    service = ServiceDump(
        uuid="service-uuid",
        handle=1,
        characteristics=(
            CharacteristicDump(
                uuid="char-uuid",
                handle=2,
                properties=("read",),
                read_error="BleakError: failed",
            ),
        ),
    )

    output = format_service_dump([service])

    assert "value: <read failed: BleakError: failed>" in output
