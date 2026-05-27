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
publish_groups = [
  "battery",
  "pv",
  # "grid",
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
topic_prefix = "marstek"
publish_groups = [
  "battery",
  "pv",
  # "grid",
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
MQTT_TOPIC_PREFIX
MQTT_PUBLISH_GROUPS
MARSTEK_CAPTURE_WRITES_PATH
```

`MQTT_PUBLISH_GROUPS` is a comma-separated list, for example:

```bash
MQTT_PUBLISH_GROUPS=battery,pv,grid
```

## 📡 MQTT Payloads

The default topic prefix is `marstek`. Each selected publish group emits one
flat JSON payload with a `ts` timestamp and scalar fields, which keeps Telegraf
JSON ingestion straightforward.

For the example config:

```toml
publish_groups = [
  "battery",
  "pv",
  # "grid",
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
{"power_w":598.674,"soc_percent":46.0,"ts":"2026-05-24T10:00:00+00:00","voltage_v":52.98}
```

Example `marstek/pv` payload:

```json
{"pv1_power_w":238.3,"pv1_voltage_v":27.7,"pv4_power_w":233.2,"total_power_w":890.1,"ts":"2026-05-24T10:00:00+00:00"}
```

Available groups:

- `battery`: SOC, SOH, battery voltage/current/power/state, capacity, voltage
  and current limits.
- `pv`: PV1-PV4 voltage/current/power, total PV power, MPPT state, error,
  warning, and temperature.
- `grid`: grid/inverter voltage, current, frequency, power-like value, power
  factor raw, inverter state, and inverter temperature.
- `temperatures`: inverter, MPPT, MOSFET, cell average, per-cell temperature,
  environment, tail MOSFET, and unconfirmed battery temperature.
- `cells`: 16 cell voltages, min/max/average/delta, and cell temperature words.
- `diagnostics`: known scalar inverter/MPPT/BMS state, error, warning, and flag
  words. Unknown protocol word maps are intentionally not published.

`run --stdout` prints one compact JSON object per sample. Because stdout combines
selected groups into one object, group prefixes are used where needed:

```json
{"battery_soc_percent":46.0,"pv1_power_w":238.3,"pv_total_power_w":890.1,"ts":"2026-05-24T10:00:00+00:00"}
```

Operational logs are JSON Lines on stdout. MQTT telemetry is not duplicated in
the service logs.

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
