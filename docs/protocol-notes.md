# Protocol Notes

## 2026-05-24 BLE discovery

Observed likely Marstek/Hame advertisement:

- Advertised name pattern: `MST_AIOS_...`
- Advertisement service UUIDs: none
- Advertisement manufacturer data: none

The BLE address is intentionally omitted from this document.

## 2026-05-24 service dump

Observed services and characteristics:

```text
00001801-0000-1000-8000-00805f9b34fb
  00002b2a-0000-1000-8000-00805f9b34fb read
  00002a05-0000-1000-8000-00805f9b34fb indicate
  00002b29-0000-1000-8000-00805f9b34fb read, write

0000ff00-0000-1000-8000-00805f9b34fb
  0000ff01-0000-1000-8000-00805f9b34fb write-without-response, notify
  0000ff02-0000-1000-8000-00805f9b34fb write-without-response, notify
  0000ff06-0000-1000-8000-00805f9b34fb write-without-response, notify
```

Known Marstek Venus BLE references use the same custom service UUID:

```text
0000ff00-0000-1000-8000-00805f9b34fb
```

`jaapp/ha-marstek-ble` identifies:

- `0000ff01-0000-1000-8000-00805f9b34fb` as the write characteristic.
- `0000ff02-0000-1000-8000-00805f9b34fb` as the notify characteristic.
- Command frames shaped as `[0x73][length][0x23][command][payload...][xor]`.

`rweijnen/marstek-venus-monitor` documents the same custom service and frame shape,
with read-style commands beyond the live `0x14` telemetry request.

Known or suspected read-style frames from references:

```text
0x03 runtime-info       runtime/status values; Jupiter C/HMM mapping partly unconfirmed
0x04 device-info        device identity information
0x08 wifi-ssid          Wi-Fi SSID read; privacy-sensitive, not useful for telemetry
0x0d system-data        system status data
0x13 timer-info         timer/error information
0x14 bms-data           live battery/PV/grid/cell telemetry used by this bridge
0x1a config-data        configuration/status data
0x1c logs               event log read
0x21 meter-ip           meter IP read
0x22 ct-polling-rate    CT polling rate read
0x24 network-info       network configuration read
0x28 local-api-status   local API status read
```

The bridge permits only `0x14` in executable runtime code. The other command IDs
are documented reference material only. They may be useful for future diagnostics
or metadata, but their Jupiter C/HMM payload layouts are not fully confirmed and
some may expose private network details. Promoting any of them into executable
code needs a separate design review.

## Difference from Venus references

This Jupiter C / HMM-advertised device also exposes `0000ff06` with
`write-without-response, notify`, and `0000ff01` itself advertises `notify`.
Do not assume the Venus characteristic split is complete for this device.

## Passive notification result

Two bounded passive notification captures subscribed successfully to all
`notify`/`indicate` characteristics, including `ff01`, `ff02`, `ff06`, and `2a05`.
Both captures produced zero frames.

Current inference: this device likely does not stream telemetry spontaneously after
notification subscription. It probably requires a protocol command request before it
returns telemetry on a notify characteristic.

No protocol command writes have been sent yet.

## Controlled request plan

The first protocol write used the known frame shape and only known read-style
commands. The public bridge now keeps only the live telemetry command executable:

```text
bms-data     0x14
```

Send to `0000ff01-0000-1000-8000-00805f9b34fb` and subscribe before sending,
starting with the documented notify characteristic
`0000ff02-0000-1000-8000-00805f9b34fb`.

## 2026-05-24 runtime-info request

A single `runtime-info` reference request returned a valid response frame with
command byte `0x03`. The raw request and response bytes are intentionally omitted
because committed docs should not contain local capture material. This command is
not part of the executable runtime allowlist.

## 2026-05-24 bms-data request

Sent one `bms-data` read request. The response frame had a valid checksum and
command byte `0x14`. The raw request and response bytes are intentionally
omitted because committed docs should not contain local capture material.

Despite the `bms-data` name, this Jupiter C/HMM response contains more than
strict battery-management data. The confirmed fields include battery/BMS values,
PV/MPPT values, grid/inverter values, temperatures, cell voltages, and diagnostic
status/error/warning words. No additional BLE command is needed for the currently
decoded live PV and grid-like telemetry.

## Experimental HMM/Jupiter BMS offsets

The `0x14` response from this device is 166 payload bytes, not the 80-byte Venus
shape. The Venus offsets produce implausible values for this capture, but a later
block is internally consistent with pack voltage and 16 LFP cell voltages.

The field names below were cross-checked against known Jupiter/HMM cloud
telemetry names. That cloud form is already key/value data, not raw BLE bytes,
so these names are used only where the BLE values and scale factors line up.

Current experimental offsets:

```text
payload[0:2]     inverter state word = 7
payload[6:8]     inverter/grid voltage / 10 = 246.5 V
payload[8:10]    inverter/grid current / 10 = 0.0 A
payload[10:12]   inverter/grid power factor raw = 0
payload[12:14]   inverter/grid frequency / 100 = 50.01 Hz
payload[14:16]   inverter battery voltage / 10 = 53.1 V
payload[16:18]   inverter/grid power = 613 W
payload[18:20]   inverter temperature = 53 °C
payload[20:32]   unknown inverter words; likely status/counter data
payload[32:34]   MPPT state = 244
payload[34:36]   MPPT error = 0
payload[36:38]   MPPT temperature = 46 °C
payload[38:40]   MPPT warning = 0
payload[40:46]   PV1 voltage/current/power / 10 = 27.7 V, 8.5 A, 238.3 W
payload[46:52]   PV2 voltage/current/power / 10 = 29.2 V, 5.6 A, 166.2 W
payload[52:58]   PV3 voltage/current/power / 10 = 28.0 V, 8.9 A, 252.4 W
payload[58:64]   PV4 voltage/current/power / 10 = 30.0 V, 7.7 A, 233.2 W
payload[64:80]   unknown MPPT words
payload[80:82]   MPPT `b_vol` / 10 = 52.9 V
payload[82:84]   MPPT `b_cur` / 10 = 16.6 A
payload[84:86]   MPPT `base_v` raw = 223
payload[86:88]   MPPT `pe_v` raw = 168
payload[88:90]   voltage limit / 10 = 58.1 V
payload[90:92]   charge current limit / 10 = 50.0 A
payload[92:94]   discharge current limit / 10 = 50.0 A
payload[94:96]   SOC = 46 %
payload[96:98]   SOH = 97 %
payload[98:100]  design capacity = 2560 Wh
payload[100:102] battery current / 10 = 11.3 A
payload[102:104] battery voltage / 100 = 52.98 V
payload[104:106] unconfirmed signed temperature-like word = 30 °C
payload[106:108] MOSFET-like temperature / 10 = 31.0 °C
payload[108:110] BMS error (`b_err`) = 0
payload[110:112] BMS warning (`b_war`) = 0
payload[112:114] BMS error 2 (`b_err2`) = 0
payload[114:116] BMS warning 2 (`b_war2`) = 0
payload[116:118] cell flag (`c_flag`) = 192
payload[118:120] BMS number (`b_num`) = 1
payload[120:122] unknown BMS word
payload[122:154] 16 cell voltages / 1000 = 3.312-3.315 V
payload[154:162] 4 cell/pack temperature words = 31, 30, 30, 31 °C
payload[162:164] environment temperature = 38 °C
payload[164:166] tail MOSFET temperature; known as `mos_t` in cloud fields = 31 °C
```

Normalized decoder output currently uses these offsets and marks the raw decoder
block as `hmm_bms_v1_experimental`. The raw block also includes
`raw_field_values`, which preserves the matching Jupiter/HMM field names in raw
pre-conversion units for easier comparison with cloud MQTT captures.

## 2026-05-24 unknown-field capture

Captured eight additional `bms-data` responses over one persistent BLE connection
at five-second spacing. This was still request/notification based: write the
allowlisted read frame to `ff01`, receive the response on `ff02`; no control
commands were sent.

The capture confirmed these additional fields:

```text
payload[6:8]     grid voltage: 246.2-247.3 V
payload[12:14]   grid frequency: 50.00-50.03 Hz
payload[14:16]   inverter-side battery voltage: 53.1-53.6 V
payload[16:18]   inverter/grid power-like value: 794-801 W
payload[18:20]   inverter temperature: 51-53 °C
payload[154:162] stable cell/pack temperatures: 39, 39, 39, 39 °C
payload[162:164] environment temperature: 44 °C
payload[164:166] tail MOSFET temperature: 38-39 °C
```

The word at `payload[104:106]`, previously treated as `battery_temp_c`, is not
safe as an unsigned temperature. During this capture it moved through signed
values such as `22`, `-19`, `-4`, `-20`, `-28`, `61`, `12`, `-61`. The decoder
now keeps it as `battery_temp_c_unconfirmed` and uses the stable tail
cell-temperature block for normalized `temperature_c`.

Still-undecoded words are preserved in raw output as `unknown_words` under the
`inverter`, `mppt`, and BMS sections. The most interesting remaining blocks are:

```text
payload[20:32]   inverter counters/status words
payload[64:80]   MPPT status/counter words before MPPT b_vol/b_cur
payload[120:122] final BMS status word before cell voltages
```
