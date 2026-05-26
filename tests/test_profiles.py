from marstek_ble_mqtt.profiles import GENERIC, JUPITER_HMM, get_profile, suggest_profile
from tests.test_decoder import BMS_DATA_FRAME


def test_get_profile_auto_defaults_to_jupiter_hmm() -> None:
    assert get_profile("auto") is JUPITER_HMM


def test_suggest_profile_uses_markers() -> None:
    assert suggest_profile(("MST",)) is JUPITER_HMM
    assert suggest_profile(()) is GENERIC


def test_generic_profile_keeps_raw_without_normalized_values() -> None:
    telemetry = GENERIC.decoder(bytes.fromhex(BMS_DATA_FRAME))

    assert telemetry.soc_percent is None
    assert telemetry.raw["decoder"] == "generic"
    assert telemetry.raw["command"] == "0x14"
    assert "payload_hex" in telemetry.raw


def test_jupiter_profile_decodes_normalized_values() -> None:
    telemetry = JUPITER_HMM.decoder(bytes.fromhex(BMS_DATA_FRAME))

    assert telemetry.soc_percent == 46.0
    assert telemetry.pv_total_power_w == 890.1
