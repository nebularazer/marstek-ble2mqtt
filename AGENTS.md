# AGENTS.md

## Project Goal

`marstek-ble2mqtt` is a Bluetooth-to-MQTT bridge for Marstek/Hame batteries.

The public runtime should stay focused:

- read telemetry from a configured BLE battery
- decode it through a device profile
- publish normalized and raw telemetry to MQTT
- provide `run --stdout` for no-MQTT terminal observation

The project is not a battery control tool.

## Safety Rules

- Normal runtime may send only allowlisted read telemetry requests.
- Do not add control, configuration, charge/discharge, schedule, calibration, or
  DOD commands without a separate design review.
- Do not expose arbitrary BLE command IDs through the main config or runtime CLI.
- Keep protocol writes logged with timestamp, purpose, characteristic UUID, and
  payload hex when captures are enabled.
- Do not brute-force, fuzz, or probe unknown command IDs.

## Public CLI Shape

Keep the public CLI minimal:

```bash
marstek-ble2mqtt run --config config.toml
marstek-ble2mqtt run --config config.toml --stdout
marstek-ble2mqtt profiles
marstek-ble2mqtt debug scan
marstek-ble2mqtt debug services --address AA:BB:CC:DD:EE:FF
```

Use config files and environment variables for runtime settings. Avoid adding
many one-off CLI flags to `run`.

## Device Profiles

Device-specific payload offsets belong in device profiles. Shared modules should
handle BLE transport, frame validation, MQTT publishing, config loading, and
common telemetry models.

Current profiles:

- `jupiter-hmm`: experimental normalized telemetry decoder for Jupiter C /
  HMM-style `0x14` BMS frames.
- `generic`: raw frame validation/publishing only.

Do not claim normalized support for a device until test fixtures and protocol
notes back it up.

## Privacy

Do not commit:

- captures
- `.env`
- local config files with real addresses or credentials
- BLE MAC addresses from real users
- Wi-Fi SSIDs
- account IDs, tokens, or MQTT credentials

Keep `.dev/`, `captures/`, caches, and virtual environments ignored.

## Checks

Before declaring work done:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Commit Policy

Use Conventional Commits for every commit that lands on `main`.

Recommended commit flow:

```bash
uv run cz commit
```

For local commit-message checks, install the repository hook:

```bash
uv run pre-commit install --hook-type commit-msg
```

Commit messages and PR titles should use the conventional format:

```text
type(optional-scope): summary
```

Common types are `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`,
`build`, and `perf`.

Do not manually edit generated release sections in `CHANGELOG.md`. The release
script updates the changelog from Conventional Commits through Commitizen.

## Releases

Releases are date-versioned:

- Git tags use `vYYYY.M.D`, for example `v2026.5.26`.
- Same-day follow-up releases append a numeric counter, for example
  `v2026.5.26.1`.
- Python package metadata uses the same version without the leading `v`.
- Docker image tags also omit the leading `v`, for example `2026.5.26`.

Create a release from a clean worktree:

```bash
scripts/release
```

The release script:

- fetches tags from `origin` when available
- chooses today's date version, or the next same-day patch counter
- accepts `--date` and `--patch` overrides
- prints the exact release actions and requires typing `release`
- runs the standard checks
- uses Commitizen to update `pyproject.toml`, `uv.lock`, and `CHANGELOG.md`
- creates `chore(release): vYYYY.M.D[.N]`
- creates the matching Git tag
- pushes the branch and tag to `origin`

Pushing the tag triggers the GitHub release workflow. It publishes a multi-arch
Docker image for `linux/amd64` and `linux/arm64` to:

```text
ghcr.io/<owner>/marstek-ble2mqtt
```

Published Docker tags are the version without `v` and `latest`.
