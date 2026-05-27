# marstek-ble2mqtt

Bluetooth-to-MQTT bridge for Marstek/Hame batteries.

`marstek-ble2mqtt` reads telemetry over Bluetooth Low Energy, decodes it through
a device profile, and publishes flat JSON payloads to MQTT. The runtime is
telemetry-only: it does not configure, schedule, charge, discharge, calibrate, or
control the battery.

## 🚀 Quick Start

Install the development environment:

```bash
uv sync --dev
```

Copy the example config and edit it:

```bash
cp config.example.toml config.toml
```

Set at least:

```toml
[ble]
address = "AA:BB:CC:DD:EE:FF"

[mqtt]
host = "localhost"
client_id = ""
publish_groups = [
  "battery",
  "pv",
  # "inverter",
  # "temperatures",
  # "cells",
  # "diagnostics",
]

[capture]
protocol_writes_path = ""
```

Find your BLE address with the scanner:

```bash
uv run marstek-ble2mqtt debug scan
```

Run the MQTT bridge:

```bash
uv run marstek-ble2mqtt run --config config.toml
```

Watch the same telemetry path without MQTT:

```bash
uv run marstek-ble2mqtt run --config config.toml --stdout
```

`run` intentionally accepts only `--config` and `--stdout`. Put runtime settings
in `config.toml` or environment variables instead of building long command-line
flag lists.

## ⚙️ Configuration

The default config path is `config.toml`; pass `--config` when you keep it
somewhere else.

Common config keys:

```toml
[ble]
address = "AA:BB:CC:DD:EE:FF"
poll_interval = 10
connect_timeout = 30
response_timeout = 8

[mqtt]
host = "localhost"
port = 1883
username = ""
password = ""
client_id = ""
topic_prefix = "marstek"
publish_groups = [
  "battery",
  "pv",
  # "inverter",
  # "temperatures",
  # "cells",
  # "diagnostics",
]

[device]
profile = "auto"
```

Environment variables override the config file:

```text
MARSTEK_BLE_ADDRESS
MARSTEK_POLL_INTERVAL
MARSTEK_CONNECT_TIMEOUT
MARSTEK_RESPONSE_TIMEOUT
MARSTEK_DEVICE_PROFILE
MQTT_HOST
MQTT_PORT
MQTT_USERNAME
MQTT_PASSWORD
MQTT_CLIENT_ID
MQTT_TOPIC_PREFIX
MQTT_PUBLISH_GROUPS
MARSTEK_CAPTURE_WRITES_PATH
```

`MQTT_PUBLISH_GROUPS` is a comma-separated list, for example:

```bash
MQTT_PUBLISH_GROUPS=battery,pv,inverter
```

`mqtt.client_id` is optional. Set it, or `MQTT_CLIENT_ID`, when your broker or
observability setup expects a stable MQTT client identifier.

## 📡 MQTT Payloads

The default topic prefix is `marstek`. Each selected publish group emits one
flat JSON payload with a `ts` timestamp and scalar fields, which keeps Telegraf
JSON ingestion straightforward.

For the example config:

```toml
publish_groups = [
  "battery",
  "pv",
  # "inverter",
  # "temperatures",
  # "cells",
  # "diagnostics",
]
```

the bridge publishes:

```text
marstek/battery
marstek/pv
```

Example `marstek/battery` payload:

```json
{"charge_current_limit_a":10.0,"current_a":11.3,"design_capacity_wh":2560.0,"discharge_current_limit_a":50.0,"power_w":609.861,"soc_percent":98.0,"soh_percent":97.0,"state":"discharging","ts":"2026-05-27T08:57:34.816750+00:00","voltage_limit_v":58.1,"voltage_v":53.97}
```

Example `marstek/pv` payload:

```json
{"mppt_error":0,"mppt_state":244,"mppt_temperature_c":41.0,"mppt_warning":0,"pv1_current_a":9.8,"pv1_power_w":272.9,"pv1_voltage_v":27.7,"pv2_current_a":5.5,"pv2_power_w":165.7,"pv2_voltage_v":29.7,"pv3_current_a":10.1,"pv3_power_w":290.0,"pv3_voltage_v":28.4,"pv4_current_a":10.1,"pv4_power_w":289.0,"pv4_voltage_v":28.5,"total_power_w":1017.6,"ts":"2026-05-27T08:57:34.816750+00:00"}
```

Example `marstek/inverter` payload:

```json
{"current_a":0.0,"frequency_hz":50.02,"inverter_battery_voltage_v":53.7,"inverter_state_word":7,"inverter_temperature_c":40.0,"power_factor_raw":0,"power_w":635.0,"ts":"2026-05-27T08:57:34.816750+00:00","voltage_v":247.4}
```

Example `marstek/temperatures` payload:

```json
{"cell_average_c":28.0,"environment_c":34.0,"inverter_c":40.0,"mosfet_c":28.0,"mppt_c":41.0,"tail_mosfet_c":27.0,"ts":"2026-05-27T08:57:34.816750+00:00"}
```

Example `marstek/cells` payload:

```json
{"cell01_voltage_v":3.37,"cell02_voltage_v":3.372,"cell03_voltage_v":3.373,"cell04_voltage_v":3.373,"cell05_voltage_v":3.371,"cell06_voltage_v":3.372,"cell07_voltage_v":3.372,"cell08_voltage_v":3.372,"cell09_voltage_v":3.373,"cell10_voltage_v":3.374,"cell11_voltage_v":3.374,"cell12_voltage_v":3.375,"cell13_voltage_v":3.374,"cell14_voltage_v":3.378,"cell15_voltage_v":3.373,"cell16_voltage_v":3.373,"pack_temp01_c":28.0,"pack_temp02_c":28.0,"pack_temp03_c":28.0,"pack_temp04_c":28.0,"ts":"2026-05-27T08:57:34.816750+00:00","voltage_avg_v":3.373,"voltage_delta_v":0.008,"voltage_max_v":3.378,"voltage_min_v":3.37}
```

Available groups:

- `battery`: SOC, SOH, battery voltage/current/power/state, capacity, voltage
  and current limits.
- `pv`: PV1-PV4 voltage/current/power, total PV power, MPPT state, error,
  warning, and temperature.
- `inverter`: inverter/grid-side voltage, current, frequency, send-to-grid
  power-like value, power factor raw, inverter state, and inverter temperature.
- `temperatures`: inverter, MPPT, MOSFET, cell average, environment, and tail
  MOSFET temperatures.
- `cells`: 16 cell voltages, min/max/average/delta, and 4 pack temperature
  sensor words.
- `diagnostics`: known scalar inverter/MPPT/BMS state, error, warning, and flag
  words, including unconfirmed temperature-like fields kept out of normal
  telemetry. Unknown protocol word maps are intentionally not published.

Float values in MQTT and stdout payloads are rounded to at most 3 decimal
places. `battery.power_w` is BMS-side DC pack power computed from battery
voltage/current. `inverter.power_w` is a device-reported inverter/grid-side
value for send-to-grid behavior. These values can differ because they are
measured at different points and may include conversion loss, inverter
self-consumption, timing differences, and different voltage measurements.

`battery.state` describes battery power direction. For this device, battery
charging is expected from the PV strings, not from the grid.

`run --stdout` prints one compact JSON object per sample. Telemetry groups are
nested under the same group names used for MQTT topics, with frame metadata kept
in a top-level `frame` object when present:

```json
{"battery":{"power_w":609.861,"soc_percent":98.0,"state":"discharging","voltage_v":53.97},"frame":{"checksum_valid":true,"command":"0x14","length_valid":true},"pv":{"pv1_power_w":272.9,"pv1_voltage_v":27.7,"total_power_w":1017.6},"ts":"2026-05-27T08:57:34.816750+00:00"}
```

Operational logs are JSON Lines on stdout. MQTT telemetry is not duplicated in
the service logs.

The MQTT publisher keeps one connection open for the process lifetime. Paho's
network loop handles broker reconnects with a bounded 1-60 second backoff.
Individual MQTT publish failures are logged as `mqtt_publish_failed` and do not
force a BLE reconnect.

## 🧭 Device Profiles

List available profiles:

```bash
uv run marstek-ble2mqtt profiles
```

Built-in profiles:

- `auto`: currently resolves to `jupiter-hmm`.
- `jupiter-hmm`: experimental normalized decoder verified against one Jupiter C
  / HMM-style device.

Do not assume normalized support for other Marstek/Hame devices until fixtures
and protocol notes back it up. Use the debug tools for passive discovery.

## 🛡️ Safety

Marstek/Hame telemetry over BLE uses a request/response protocol: the bridge
must write an allowlisted read request to the battery's BLE request
characteristic before the battery sends telemetry back on a notify
characteristic.

Normal operation only sends allowlisted read telemetry requests. It does not
send control, configuration, schedule, charge/discharge, calibration, or DOD
commands.

For explicit local debugging, protocol write capture can be enabled in config or
with `MARSTEK_CAPTURE_WRITES_PATH`. It writes JSON Lines containing only the
timestamp, purpose, characteristic UUID, and payload hex for each allowlisted
read request. Leave the path empty to disable capture.

## 🔎 Debug Tools

Scan for likely Marstek/Hame advertisements:

```bash
uv run marstek-ble2mqtt debug scan
```

The scanner ranks devices whose advertised name or manufacturer data contains
known markers such as `MST`, `MARSTEK`, `HAME`, `HMM`, `HMJ`, `JUPITER`, or
`VENUS`, and prints a suggested BLE address.

Inspect GATT services read-only:

```bash
uv run marstek-ble2mqtt debug services --address AA:BB:CC:DD:EE:FF
```

`debug services` connects once and reads only characteristics that advertise the
BLE `read` property.

## 🐳 Docker

Build the image locally:

```bash
docker build -t marstek-ble2mqtt .
```

Run with Docker Compose:

```bash
docker compose -f docker-compose.example.yml up
```

Ctrl-C and Docker stop request a graceful shutdown. The bridge exits the BLE
context, closes the MQTT publisher, logs `stopped`, and returns the conventional
signal exit code: `130` for SIGINT and `143` for SIGTERM.

Bluetooth access from containers is host-specific. The example compose file
shows the common Linux DBus/host-network setup, but your host may need different
Bluetooth device or permission mappings.

Published releases include multi-arch Docker images on GitHub Container
Registry:

```bash
docker pull ghcr.io/nebularazer/marstek-ble2mqtt:latest
```

Versioned Docker tags omit the leading `v` from the Git tag. For example, Git
tag `v2026.5.26` publishes Docker tag `2026.5.26`.

## 🧪 Development

Run the standard checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

This repository uses Conventional Commits and Commitizen:

```bash
uv run cz commit
uv run pre-commit install --hook-type commit-msg
```

Releases are generated from Conventional Commits:

```bash
scripts/release
```

The release script updates `pyproject.toml`, `uv.lock`, and `CHANGELOG.md`, then
pushes a release branch for review. After the release PR is squash-merged into
`main`, publish the tag from the merged commit:

```bash
scripts/release finalize v2026.5.26
```

The finalized tag triggers GitHub Actions.

## 📚 References

This project was built by comparing local BLE captures with existing community
work:

- `tomquist/hm2mqtt`: https://github.com/tomquist/hm2mqtt
- `tomquist/hame-relay`: https://github.com/tomquist/hame-relay
- `jaapp/ha-marstek-ble`: https://github.com/jaapp/ha-marstek-ble
- `jaapp/marstek-ble-gateway`: https://github.com/jaapp/marstek-ble-gateway
- `rweijnen/marstek-venus-monitor`: https://github.com/rweijnen/marstek-venus-monitor

See `docs/` for protocol notes and reverse-engineering context.
