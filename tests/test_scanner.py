from marstek_ble_mqtt.scanner import BleScanResult, find_marstek_markers, format_scan_results


def test_find_marstek_markers_from_name() -> None:
    markers = find_marstek_markers(name="HMM-1 Jupiter", manufacturer_data={})

    assert markers == ("HMM", "JUPITER")


def test_find_marstek_markers_from_ascii_manufacturer_data() -> None:
    markers = find_marstek_markers(name=None, manufacturer_data={65535: b"hello HAME".hex()})

    assert markers == ("HAME",)


def test_format_scan_results_highlights_likely_devices() -> None:
    result = BleScanResult(
        address="AA:BB:CC:DD:EE:FF",
        name="HMM-1",
        manufacturer_data={65535: "484d4d"},
        service_uuids=("0000180a-0000-1000-8000-00805f9b34fb",),
        is_likely_marstek=True,
        matched_markers=("HMM",),
    )

    output = format_scan_results([result])

    assert "[LIKELY MARSTEK/HAME] AA:BB:CC:DD:EE:FF  HMM-1" in output
    assert "Manufacturer data: 0xffff=484d4d" in output
    assert "Service UUIDs: 0000180a-0000-1000-8000-00805f9b34fb" in output
    assert "Matched markers: HMM" in output
