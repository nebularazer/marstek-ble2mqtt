# Changelog

All notable changes to this project are generated from Conventional Commits by
Commitizen.

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
