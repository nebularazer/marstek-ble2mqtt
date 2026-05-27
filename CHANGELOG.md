# Changelog

All notable changes to this project are generated from Conventional Commits by
Commitizen.

## v2026.5.27.1 (2026-05-27)

### Feat

- aggregate PR release notes
- link PRs in release notes

### Fix

- clean up telemetry output and stabilize runtime

### Details

- [PR 6](https://github.com/nebularazer/marstek-ble2mqtt/pull/6): fix: clean up telemetry output and stabilize runtime
  - Breaking: MQTT publish group `grid` is renamed to `inverter`.
  - Breaking: `run --stdout` now prints nested telemetry groups instead of prefixed flat keys.
  - Telemetry float output is rounded to at most 3 decimals.
  - Unconfirmed battery temperature-like data now appears under diagnostics instead of normal temperature telemetry.
  - MQTT publishing now uses one long-lived connection with bounded 1-60 second reconnect backoff.
  - MQTT publish failures are logged as `mqtt_publish_failed` and do not interrupt BLE polling.
  - `mqtt.client_id` and `MQTT_CLIENT_ID` can set a stable MQTT client identifier.
  - `run` handles SIGINT/SIGTERM gracefully, closes BLE/MQTT resources, logs `stopped`, and exits with 130/143.
- [PR 8](https://github.com/nebularazer/marstek-ble2mqtt/pull/8): feat: aggregate PR release notes
  - Release PRs now include detailed changelog notes gathered from merged PR release-note sections.
  - The generated changelog uses `PR N:` detail labels to avoid noisy GitHub autolink formatting.
- [PR 9](https://github.com/nebularazer/marstek-ble2mqtt/pull/9): feat: link PRs in release notes
  - Release changelog details now link directly to the source pull request while keeping the rendered Markdown compact.

## v2026.5.27 (2026-05-27)

### BREAKING CHANGE

- MQTT payloads and stdout samples now use flat scalar fields. The full publish group and public generic runtime profile were removed.

### Refactor

- flatten MQTT telemetry payloads

### Details

- [PR 4](https://github.com/nebularazer/marstek-ble2mqtt/pull/4): refactor!: flatten MQTT telemetry payloads
  - MQTT payloads and stdout samples now use flat scalar fields.
  - The `full` publish group and public `generic` runtime profile were removed.
  - Unknown `run` flags now point users to config/env settings.
  - README usage and publish group examples were refreshed.

## v2026.5.26 (2026-05-26)

### Feat

- add marstek ble2mqtt bridge
