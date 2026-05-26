"""Typed telemetry models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class FrameMetadata:
    """Metadata for one decoded BLE protocol frame."""

    command: str | None = None
    payload_length: int | None = None
    checksum_valid: bool | None = None
    length_valid: bool | None = None


@dataclass(frozen=True)
class BatteryData:
    """Battery and BMS values decoded from the telemetry frame."""

    soc_percent: float | None = None
    soh_percent: float | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    power_w: float | None = None
    state: str | None = None
    design_capacity_wh: float | None = None
    voltage_limit_v: float | None = None
    charge_current_limit_a: float | None = None
    discharge_current_limit_a: float | None = None


@dataclass(frozen=True)
class PvStringData:
    """One PV input string."""

    index: int
    voltage_v: float | None = None
    current_a: float | None = None
    power_w: float | None = None


@dataclass(frozen=True)
class PvData:
    """PV and MPPT values decoded from the telemetry frame."""

    strings: tuple[PvStringData, ...] = ()
    total_power_w: float | None = None
    mppt_state: int | None = None
    mppt_error: int | None = None
    mppt_warning: int | None = None
    mppt_temperature_c: float | None = None


@dataclass(frozen=True)
class GridData:
    """Grid and inverter values decoded from the telemetry frame."""

    inverter_state_word: int | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    power_factor_raw: int | None = None
    frequency_hz: float | None = None
    power_w: float | None = None
    inverter_battery_voltage_v: float | None = None
    inverter_temperature_c: float | None = None


@dataclass(frozen=True)
class TemperatureData:
    """Temperature values decoded from the telemetry frame."""

    inverter_c: float | None = None
    mppt_c: float | None = None
    mosfet_c: float | None = None
    cell_average_c: float | None = None
    cell_temperatures_c: tuple[float, ...] = ()
    environment_c: float | None = None
    tail_mosfet_c: float | None = None
    battery_unconfirmed_c: float | None = None


@dataclass(frozen=True)
class CellData:
    """Cell voltage and temperature values decoded from the telemetry frame."""

    voltages_v: tuple[float, ...] = ()
    voltage_min_v: float | None = None
    voltage_max_v: float | None = None
    voltage_avg_v: float | None = None
    voltage_delta_v: float | None = None
    temperatures_c: tuple[float, ...] = ()


@dataclass(frozen=True)
class DiagnosticData:
    """State, error, warning, and currently unknown words."""

    inverter_state_word: int | None = None
    mppt_state: int | None = None
    mppt_error: int | None = None
    mppt_warning: int | None = None
    bms_error: int | None = None
    bms_warning: int | None = None
    bms_error2: int | None = None
    bms_warning2: int | None = None
    cell_flag: int | None = None
    bms_number: int | None = None
    inverter_unknown_words: dict[str, dict[str, int]] = field(default_factory=dict)
    mppt_unknown_words: dict[str, dict[str, int]] = field(default_factory=dict)
    bms_unknown_words: dict[str, dict[str, int]] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Telemetry:
    """Grouped telemetry plus raw decoded fields."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    frame: FrameMetadata = FrameMetadata()
    battery: BatteryData = BatteryData()
    pv: PvData = PvData()
    grid: GridData = GridData()
    temperatures: TemperatureData = TemperatureData()
    cells: CellData = CellData()
    diagnostics: DiagnosticData = DiagnosticData()
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def soc_percent(self) -> float | None:
        return self.battery.soc_percent

    @property
    def battery_power_w(self) -> float | None:
        return self.battery.power_w

    @property
    def battery_state(self) -> str | None:
        return self.battery.state

    @property
    def pv_total_power_w(self) -> float | None:
        return self.pv.total_power_w

    @property
    def pv1_power_w(self) -> float | None:
        return _pv_power(self.pv, 1)

    @property
    def pv2_power_w(self) -> float | None:
        return _pv_power(self.pv, 2)

    @property
    def pv3_power_w(self) -> float | None:
        return _pv_power(self.pv, 3)

    @property
    def pv4_power_w(self) -> float | None:
        return _pv_power(self.pv, 4)

    @property
    def temperature_c(self) -> float | None:
        return self.temperatures.cell_average_c


def _pv_power(pv: PvData, index: int) -> float | None:
    for pv_string in pv.strings:
        if pv_string.index == index:
            return pv_string.power_w
    return None
