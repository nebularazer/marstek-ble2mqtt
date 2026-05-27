from pathlib import Path

from marstek_ble_mqtt.config import load_config


def test_load_config_from_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[ble]
address = "AA:BB:CC:DD:EE:FF"
poll_interval = 12

[mqtt]
host = "mqtt.example.test"
port = 1884
topic_prefix = "marstek/test"
publish_groups = ["battery", "pv", "diagnostics"]

[device]
profile = "jupiter-hmm"

[capture]
protocol_writes_path = "captures/writes.jsonl"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.ble.address == "AA:BB:CC:DD:EE:FF"
    assert config.ble.poll_interval == 12
    assert config.mqtt.host == "mqtt.example.test"
    assert config.mqtt.port == 1884
    assert config.mqtt.topic_prefix == "marstek/test"
    assert config.mqtt.publish_groups == ("battery", "pv", "diagnostics")
    assert config.capture.protocol_writes_path == Path("captures/writes.jsonl")
    assert config.device_profile == "jupiter-hmm"


def test_environment_overrides_config(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[mqtt]\nhost = "from-file"\n', encoding="utf-8")
    monkeypatch.setenv("MQTT_HOST", "from-env")

    config = load_config(config_path)

    assert config.mqtt.host == "from-env"


def test_environment_overrides_publish_groups(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[mqtt]\npublish_groups = ["battery"]\n', encoding="utf-8")
    monkeypatch.setenv("MQTT_PUBLISH_GROUPS", "inverter, temperatures")

    config = load_config(config_path)

    assert config.mqtt.publish_groups == ("inverter", "temperatures")


def test_environment_overrides_capture_writes_path(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[capture]\nprotocol_writes_path = "from-file.jsonl"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MARSTEK_CAPTURE_WRITES_PATH", "from-env.jsonl")

    config = load_config(config_path)

    assert config.capture.protocol_writes_path == Path("from-env.jsonl")
