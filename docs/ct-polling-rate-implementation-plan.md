# CT Polling Rate Implementation Plan

## Goal

Add a safe diagnostic path to read the Marstek/Hame CT polling-rate setting
(`0x22`) and, only after confirming the exact vendor write command from source
or captures, optionally allow changing it.

This must not turn `marstek-ble2mqtt run` into a battery control tool. Normal
runtime must continue to send only the live telemetry read command (`0x14`).

## Safety Boundaries

- Do not add `0x22` back to `SAFE_READ_COMMANDS`; that allowlist is for normal
  runtime telemetry only.
- Do not expose arbitrary BLE command IDs in config or CLI.
- Do not brute-force, fuzz, or probe adjacent command IDs or payload values.
- Do not add a setter from inference. Implement writes only after finding an
  exact reference implementation or verified local protocol notes for command
  code, payload layout, response command, and valid values.
- Do not commit captures, BLE MAC addresses, Wi-Fi SSIDs, tokens, MQTT
  credentials, or raw full-frame dumps.
- Keep all protocol writes compatible with existing write-capture logging:
  timestamp, purpose, characteristic UUID, and payload hex.

## Phase 1: Read-Only Diagnostic Support

Implement a dedicated CT polling-rate diagnostic path separate from runtime
telemetry.

Required behavior:

- Define a dedicated `ReadCommand(0x22, "ct-polling-rate", "CT polling rate read")`
  outside `SAFE_READ_COMMANDS`, preferably in a new small module such as
  `marstek_ble_mqtt.ct_polling`.
- Extend `BleRequestClient` with an instance-level command policy, for example
  `allowed_command_codes: frozenset[int] = SAFE_READ_COMMAND_CODES`.
- Keep the default policy unchanged, so runtime and existing tests still reject
  `0x22`.
- Add a diagnostic opener/helper that explicitly allows only `0x22` for this
  feature. Do not create a generic “send any command” helper.
- Decode the `0x22` response defensively:
  - Validate frame header, length, checksum, and command byte.
  - Always expose `payload_hex` and payload length.
  - Set `rate` only if the payload is clearly a single enum value in `{0, 1, 2}`.
  - Map known labels as `0 = fastest`, `1 = medium`, `2 = slowest`.
  - For any other payload shape, return raw data plus `rate = null` and a note
    that the layout is unconfirmed.

Suggested CLI:

```bash
marstek-ble2mqtt debug ct-polling-rate --address AA:BB:CC:DD:EE:FF
```

Output one compact JSON document, for example:

```json
{"command":"0x22","payload_hex":"01","rate":1,"label":"medium","confirmed":true}
```

This adds one debug command, but does not change `run`, config files, MQTT
publishing, or normal telemetry behavior.

## Phase 2: Research Before Any Setter

Before implementing writes, the agent must find authoritative evidence for the
setter protocol.

Required evidence:

- Exact BLE command code used to set CT polling rate.
- Exact payload bytes for rates `0`, `1`, and `2`.
- Expected response frame, if any.
- Whether the operation persists across reboot.
- Whether unsupported values are rejected by the device or silently accepted.

Acceptable sources:

- Vendor/community source code that directly implements the BLE setter.
- A local capture made by intentionally changing the setting through an existing
  trusted tool.

Unacceptable sources:

- Guessing from the read command.
- Trying neighboring command IDs.
- Trying unverified payload values.

Document the evidence in `docs/protocol-notes.md` without committing raw full
captures. Summarize the command, payload shape, and observed response.

## Phase 3: Optional Setter

Only implement this phase after Phase 2 evidence exists.

Required behavior:

- Add a specific setter helper, not a generic command sender:
  `set_ct_polling_rate(rate: Literal[0, 1, 2])`.
- Validate the requested rate before opening BLE.
- Require an explicit CLI write gate:

```bash
marstek-ble2mqtt debug ct-polling-rate --address AA:BB:CC:DD:EE:FF --set 1 --i-understand-this-writes-device-config
```

- If `--set` is present without the confirmation flag, exit with a user-facing
  error before connecting.
- After writing, read `0x22` again and print both requested and observed values.
- If read-back does not match the requested value, exit non-zero and include the
  raw read-back payload in JSON.
- Use existing protocol write capture for both the setter write and read-back
  request.

Do not add this setting to `config.toml`, environment variables, MQTT topics, or
the normal `run` loop.

## Implementation Touch Points

- `src/marstek_ble_mqtt/requests.py`
  - Add instance-level allowed command-code policy.
  - Preserve default runtime policy as `SAFE_READ_COMMAND_CODES`.
  - Add tests proving default clients still reject `0x22`.

- `src/marstek_ble_mqtt/ct_polling.py`
  - Add dedicated command constants, decoder, read helper, and optional setter.
  - Keep raw output available for unconfirmed payload layouts.

- `src/marstek_ble_mqtt/cli.py`
  - Add only the dedicated `debug ct-polling-rate` command.
  - Do not add flags to `run`.
  - Gate writes with `--i-understand-this-writes-device-config`.

- `tests/`
  - Unit-test `0x22` frame decoding for known enum payloads and unknown payloads.
  - Unit-test command-policy behavior in `BleRequestClient`.
  - CLI-test read-only parsing and write-gate rejection.
  - Runtime-test that normal `run` still uses only profile read command `0x14`.

- `docs/protocol-notes.md`
  - Keep `0x22` listed as reference material.
  - Add a short dated note once the read payload shape is confirmed.
  - Add setter details only after Phase 2 evidence exists.

## Acceptance Criteria

- `marstek-ble2mqtt run` behavior is unchanged.
- `SAFE_READ_COMMANDS` still contains only `bms-data`.
- A default `BleRequestClient` rejects `ReadCommand(0x22, ...)`.
- The dedicated CT diagnostic read path can send only `0x22`.
- No arbitrary command-code input exists anywhere in public config or CLI.
- Setter code, if implemented, cannot run without explicit confirmation and
  rate validation.
- Tests cover read decode, policy rejection, CLI gating, and read-back mismatch.
- Checks pass:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

If the local sandbox cannot resolve dependencies, use the existing environment
only for verification:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync ruff format --check .
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest
```
