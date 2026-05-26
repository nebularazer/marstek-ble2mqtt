"""Device profile registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from marstek_ble_mqtt.models import Telemetry
from marstek_ble_mqtt.profiles.generic import decode_generic_frame
from marstek_ble_mqtt.profiles.jupiter_hmm import decode_telemetry_frame
from marstek_ble_mqtt.protocol import ReadCommand, parse_read_command

TelemetryDecoder = Callable[[bytes | bytearray], Telemetry]


@dataclass(frozen=True)
class DeviceProfile:
    """Known device profile."""

    slug: str
    display_name: str
    maturity: str
    read_command: ReadCommand
    decoder: TelemetryDecoder
    markers: tuple[str, ...] = ()
    description: str = ""


JUPITER_HMM = DeviceProfile(
    slug="jupiter-hmm",
    display_name="Marstek Jupiter C / HMM",
    maturity="experimental",
    read_command=parse_read_command("bms-data"),
    decoder=decode_telemetry_frame,
    markers=("MST", "HMM", "JUPITER"),
    description="Verified against one Jupiter C / HMM-style battery.",
)

GENERIC = DeviceProfile(
    slug="generic",
    display_name="Generic Marstek/Hame BLE frame capture",
    maturity="raw",
    read_command=parse_read_command("bms-data"),
    decoder=decode_generic_frame,
    markers=(),
    description="Validates frames and publishes raw JSON only; no normalized telemetry.",
)

PROFILES: dict[str, DeviceProfile] = {
    JUPITER_HMM.slug: JUPITER_HMM,
    GENERIC.slug: GENERIC,
}


def get_profile(slug: str) -> DeviceProfile:
    """Return a profile by slug."""

    normalized = slug.strip().lower()
    if normalized == "auto":
        return JUPITER_HMM
    try:
        return PROFILES[normalized]
    except KeyError as exc:
        available = ", ".join(("auto", *PROFILES))
        raise ValueError(
            f"Unknown device profile {slug!r}. Available profiles: {available}"
        ) from exc


def suggest_profile(markers: tuple[str, ...]) -> DeviceProfile:
    """Suggest a profile from advertisement markers."""

    marker_set = set(markers)
    if marker_set.intersection(JUPITER_HMM.markers):
        return JUPITER_HMM
    return GENERIC


def format_profiles() -> str:
    """Format available profiles for terminal output."""

    lines = ["Available device profiles:"]
    lines.append("  auto: automatic selection; currently defaults to jupiter-hmm")
    for profile in PROFILES.values():
        lines.append(
            f"  {profile.slug}: {profile.display_name} ({profile.maturity}) - {profile.description}"
        )
    return "\n".join(lines)
