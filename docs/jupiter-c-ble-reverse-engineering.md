# Reverse Engineering the Marstek Jupiter C BLE Telemetry

This document explains how the Jupiter C / HMM BLE telemetry path was discovered.
It is written for readers who are not familiar with Bluetooth Low Energy.

## Goal

The goal was to read useful battery telemetry locally over Bluetooth and publish
it to MQTT without depending on a cloud polling path.

The important values were:

- battery state of charge
- battery charge/discharge power
- PV power from all four solar inputs
- diagnostic raw data for future decoder work

## Safety Model

The investigation used a conservative sequence:

1. Listen for advertisements without connecting.
2. Connect once and inspect services read-only.
3. Subscribe passively to notifications.
4. Compare the observed service layout with existing Marstek/Hame projects.
5. Send only known read telemetry requests.

No random commands were sent. No control, configuration, schedule, calibration,
charge/discharge, or DOD commands were sent.

## BLE Concepts

BLE devices first advertise small packets. A scanner can see the address,
advertised name, service hints, and manufacturer data without connecting.

After connecting, a BLE device exposes a GATT database made of services and
characteristics. Characteristics advertise properties such as:

- `read`
- `write`
- `write-without-response`
- `notify`
- `indicate`

For this battery, telemetry is not pushed automatically. The client subscribes
to a notify characteristic, writes a read request to a request characteristic,
and receives the response as a notification.

## Discovery

The battery advertised a name beginning with `MST_AIOS_...`. The advertisement
did not expose useful telemetry, but it was enough to identify the likely target.

The custom service found during service discovery was:

```text
0000ff00-0000-1000-8000-00805f9b34fb
```

The relevant characteristics were:

```text
0000ff01-0000-1000-8000-00805f9b34fb  write-without-response, notify
0000ff02-0000-1000-8000-00805f9b34fb  write-without-response, notify
0000ff06-0000-1000-8000-00805f9b34fb  write-without-response, notify
```

Existing Venus-oriented references use the same service and identify `ff01` as
the request characteristic and `ff02` as the notify/response characteristic. The
Jupiter C / HMM device is not identical, but the request/response shape matched.

## Passive Notification Test

Subscribing to notify/indicate characteristics without sending a request produced
zero telemetry frames. That showed the device is not a spontaneous telemetry
stream.

The working model became:

1. subscribe to `ff02`
2. write an allowlisted read request to `ff01`
3. receive a matching response notification on `ff02`

## Frame Shape

Community references showed a common Marstek BLE frame shape:

```text
[start][length][type][command][payload...][xor checksum]
```

The useful read command for Jupiter C / HMM telemetry is:

```text
0x14  bms-data
```

The bridge sends this as a read telemetry request. Although it uses a BLE write
operation at the transport layer, the application command is a read request.

## Decoding the BMS Frame

The `0x14` response payload is longer than the Venus BMS payload. Directly
applying Venus offsets produced implausible values, so the decoder was built by
looking for physical consistency:

- PV voltage should be tens of volts.
- PV current should be a few amps.
- PV power should roughly match voltage times current.
- Battery pack voltage should be around the expected pack voltage.
- SOC should be a percentage.
- Cell voltage words should be around LFP cell voltage.
- Grid frequency should be around local mains frequency.

That identified four repeated PV blocks. Each PV block contains voltage, current,
and power, scaled by 10.

The battery section contains SOC, SOH, capacity, battery voltage, battery current,
and current limits. Battery power is computed from battery voltage and current.

## Current Useful Fields

The current Jupiter/HMM profile decodes:

- SOC
- battery voltage
- battery current
- computed battery power
- battery state inferred from power direction
- PV1 voltage/current/power
- PV2 voltage/current/power
- PV3 voltage/current/power
- PV4 voltage/current/power
- total PV power
- charge and discharge current limits
- grid voltage
- grid frequency
- inverter temperature
- MPPT temperature
- cell/pack temperature values
- environment temperature
- MOSFET temperature

## Remaining Unknowns

Some words in the `0x14` frame are still intentionally exposed only as raw
unknown fields:

- inverter counters or status words
- MPPT battery/base/PE/failure words
- BMS error, warning, flag, and status words

Some of these correspond to known cloud telemetry field names, but the binary
offsets and scaling are not fully confirmed. They should not be promoted to
normalized telemetry until captures prove their meaning.

## References

The most useful reference projects are listed in the README. BLE-focused
references helped with UUIDs, frame shape, and command IDs. MQTT/cloud-focused
references helped with field names and expected units.
