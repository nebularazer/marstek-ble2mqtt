"""Configuration loading for marstek-ble2mqtt."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from marstek_ble_mqtt.mqtt import MqttConfig


@dataclass(frozen=True)
class BleConfig:
    """Bluetooth runtime configuration."""

    address: str | None = None
    connect_timeout: float = 30.0
    response_timeout: float = 8.0
    poll_interval: float = 10.0


@dataclass(frozen=True)
class CaptureConfig:
    """Local capture settings for explicit debugging hooks."""

    protocol_writes_path: Path | None = None


@dataclass(frozen=True)
class AppConfig:
    """Full application configuration."""

    ble: BleConfig = BleConfig()
    mqtt: MqttConfig = MqttConfig(topic_prefix="marstek")
    capture: CaptureConfig = CaptureConfig()
    device_profile: str = "auto"


def load_config(path: Path | None) -> AppConfig:
    """Load TOML config and environment overrides."""

    data: dict = {}
    if path is not None and path.exists():
        with path.open("rb") as config_file:
            data = tomllib.load(config_file)

    ble_data = data.get("ble", {})
    mqtt_data = data.get("mqtt", {})
    capture_data = data.get("capture", {})
    profile_data = data.get("device", {})

    ble = BleConfig(
        address=_env("MARSTEK_BLE_ADDRESS", ble_data.get("address")),
        connect_timeout=float(
            _env("MARSTEK_CONNECT_TIMEOUT", ble_data.get("connect_timeout", 30.0))
        ),
        response_timeout=float(
            _env("MARSTEK_RESPONSE_TIMEOUT", ble_data.get("response_timeout", 8.0))
        ),
        poll_interval=float(_env("MARSTEK_POLL_INTERVAL", ble_data.get("poll_interval", 10.0))),
    )
    mqtt = MqttConfig(
        host=str(_env("MQTT_HOST", mqtt_data.get("host", "localhost"))),
        port=int(_env("MQTT_PORT", mqtt_data.get("port", 1883))),
        username=_env("MQTT_USERNAME", mqtt_data.get("username")),
        password=_env("MQTT_PASSWORD", mqtt_data.get("password")),
        topic_prefix=str(_env("MQTT_TOPIC_PREFIX", mqtt_data.get("topic_prefix", "marstek"))),
        publish_groups=_string_tuple(
            _env("MQTT_PUBLISH_GROUPS", mqtt_data.get("publish_groups", ()))
        ),
    )
    capture = CaptureConfig(
        protocol_writes_path=_optional_path(
            _env(
                "MARSTEK_CAPTURE_WRITES_PATH",
                capture_data.get("protocol_writes_path"),
            )
        )
    )
    profile = str(_env("MARSTEK_DEVICE_PROFILE", profile_data.get("profile", "auto")))

    return AppConfig(ble=ble, mqtt=mqtt, capture=capture, device_profile=profile)


def require_ble_address(config: AppConfig) -> str:
    """Return configured BLE address or raise a user-facing error."""

    if config.ble.address:
        return config.ble.address
    raise ValueError(
        "No BLE address configured. Set [ble].address in config.toml or MARSTEK_BLE_ADDRESS."
    )


def _env(name: str, default):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return ()


def _optional_path(value: object) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(text)
