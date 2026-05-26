from datetime import UTC, datetime

from marstek_ble_mqtt.notifications import (
    make_notification_frame,
)


def test_make_notification_frame_formats_hex_and_ascii_preview() -> None:
    frame = make_notification_frame(
        characteristic_uuid="0000ff01-0000-1000-8000-00805f9b34fb",
        payload=b"MST\x00\xff",
        timestamp=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
    )

    assert frame.timestamp == "2026-05-24T12:00:00+00:00"
    assert frame.characteristic_uuid == "0000ff01-0000-1000-8000-00805f9b34fb"
    assert frame.payload_hex == "4d535400ff"
    assert frame.ascii_preview == "MST.."
