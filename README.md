# marstek-ble2mqtt

Bluetooth-to-MQTT bridge for Marstek/Hame batteries.

The project reads battery telemetry over Bluetooth Low Energy and publishes
normalized values to MQTT. It currently has one verified normalized profile for a
Jupiter C / HMM-style device. Other Marstek/Hame devices can still be inspected
and captured, but they need verified device profiles before normalized telemetry
is promised.

## Safety

Marstek/Hame telemetry over BLE uses a request/response protocol: the bridge must
write a read request to the battery's BLE request characteristic before the
battery sends telemetry back on a notify characteristic.

Normal operation only sends allowlisted read telemetry requests. It does not send
control, configuration, schedule, charge/discharge, calibration, or DOD commands.

For explicit local debugging, protocol write capture can be enabled in config or
with `MARSTEK_CAPTURE_WRITES_PATH`. It writes JSON Lines containing only the
timestamp, purpose, characteristic UUID, and payload hex for each allowlisted
read request. Leave the path empty to disable capture.

## Install

```bash
uv sync --dev
```

Copy and edit the example config:

```bash
cp config.example.toml config.toml
```

Set at least:

```toml
[ble]
address = "AA:BB:CC:DD:EE:FF"

[mqtt]
host = "localhost"
publish_groups = ["battery", "pv"]

[capture]
protocol_writes_path = ""
```

## Find the BLE Address

Use the debug scanner to find likely Marstek/Hame advertisements:

```bash
uv run marstek-ble2mqtt debug scan
```

The scanner ranks devices whose advertised name or manufacturer data contains
known markers such as `MST`, `MARSTEK`, `HAME`, `HMM`, `HMJ`, `JUPITER`, or
`VENUS`, and prints a suggested BLE address.

## Run the MQTT Bridge

```bash
uv run marstek-ble2mqtt run --config config.toml
```

`run` writes operational logs as JSON Lines on stdout. Telemetry values are
published to MQTT, not duplicated in the service logs.

## Run Without MQTT

For a terminal-only view of the same BLE telemetry path:

```bash
uv run marstek-ble2mqtt run --config config.toml --stdout
```

This keeps one BLE connection open, sends one read telemetry request per poll
interval, prints one compact JSON object per sample, and stops on Ctrl-C. The
JSON contains the same telemetry groups selected by `[mqtt].publish_groups`.
Operational messages such as connect, reconnect, and sample errors are also
printed as JSON lines with an `event` field.

## MQTT Publish Groups

The default topic prefix is `marstek`. Telemetry publishing is controlled by
explicit MQTT groups in `config.toml`; the bridge has no hidden telemetry group
default. The example config enables:

```toml
publish_groups = ["battery", "pv"]
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
- `diagnostics`: inverter/MPPT state and error words, BMS error/warning/flag
  words, plus still-unknown word maps.
- `full`: one complete decoded JSON document with all groups, frame
  metadata, raw decoded fields, and unknown words.

Each selected group publishes one JSON payload. JSON is implied by the payload,
so topics do not carry a `/json` suffix. For example, `battery` and `pv` publish:

```text
marstek/battery
marstek/pv
```

Each group payload includes `ts` so Telegraf can parse the message as a
self-contained JSON measurement. `full` publishes:

```text
marstek/full
```

Profiles that cannot decode normalized telemetry can still publish their raw
validated frame data through `full`.

## Device Profiles

List available profiles:

```bash
uv run marstek-ble2mqtt profiles
```

Built-in profiles:

- `jupiter-hmm`: experimental normalized decoder verified against one Jupiter C /
  HMM-style device.
- `generic`: validates frames and publishes raw JSON only.
- `auto`: currently defaults to `jupiter-hmm`.

## Debug Tools

The debug namespace is for discovery and passive inspection:

```bash
uv run marstek-ble2mqtt debug scan
uv run marstek-ble2mqtt debug services --address AA:BB:CC:DD:EE:FF
```

`debug services` connects once and reads only characteristics that advertise the
BLE `read` property.

## Docker

Build the image:

```bash
docker build -t marstek-ble2mqtt .
```

Run with Docker Compose:

```bash
docker compose -f docker-compose.example.yml up
```

Bluetooth access from containers is host-specific. The example compose file shows
the common Linux DBus/host-network setup, but your host may need different
Bluetooth device or permission mappings.

Published releases include multi-arch Docker images on GitHub Container
Registry:

```bash
docker pull ghcr.io/<owner>/marstek-ble2mqtt:latest
docker pull ghcr.io/<owner>/marstek-ble2mqtt:2026.5.26
```

Versioned Docker tags omit the leading `v` from the Git tag.

## Development

This repository uses Conventional Commits and Commitizen:

```bash
uv run cz commit
uv run pre-commit install --hook-type commit-msg
```

Releases are generated from Conventional Commits:

```bash
scripts/release
```

The release script updates `pyproject.toml`, `uv.lock`, and `CHANGELOG.md`,
creates a date-versioned Git tag such as `v2026.5.26`, and pushes the tag to
trigger GitHub Actions.

## References

This project was built by comparing local BLE captures with existing community
work:

- `tomquist/hm2mqtt`: https://github.com/tomquist/hm2mqtt
- `tomquist/hame-relay`: https://github.com/tomquist/hame-relay
- `jaapp/ha-marstek-ble`: https://github.com/jaapp/ha-marstek-ble
- `jaapp/marstek-ble-gateway`: https://github.com/jaapp/marstek-ble-gateway
- `rweijnen/marstek-venus-monitor`: https://github.com/rweijnen/marstek-venus-monitor

See `docs/` for protocol notes and reverse-engineering context.
