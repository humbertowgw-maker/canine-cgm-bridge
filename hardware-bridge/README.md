# hardware-bridge

ESP32/ESP-IDF firmware intended to forward CGM readings to `mobile-bridge` over WiFi,
using the exact same `POST /telemetry/frame` schema
`cloud-backend/simulator/simulate_dog_sensor.py` already uses — so `mobile-bridge` and
`cloud-backend` need zero changes regardless of what feeds this firmware's readings.

**How readings actually get read is an open question as of 2026-08-18** — see
`DEXCOM_BLE_PROTOCOL_RESEARCH.md` in this directory. The original assumption here (that
Stelo broadcasts BLE natively the same way G6/G7 do, so an ESP32 could act as a BLE
central and read it directly) turned out not to be confirmed by real research: digging
into xDrip+'s actual open-source implementation shows it has a complete, working,
reverse-engineered raw-BLE protocol for the **G5 and G6 only**. For G7 and Stelo, xDrip+
instead reads glucose values out of Android notifications posted by Dexcom's own official
app — a phone-side mechanism an ESP32 can't replicate. Read the research doc before
starting Step 3; it lays out the real options (G5/G6 as a protocol testbed, an
Android-phone-in-the-loop design for Stelo, or original reverse-engineering once a real
Stelo is in hand).

## Current state

**Step 2 — WiFi debug loop (done).** WiFi connect + SNTP time sync + a debug timer that
posts a fake, slowly-varying `TelemetryFrame` on a configurable interval. Proves the
WiFi → HTTP → mobile-bridge → cloud-backend path on real hardware before any sensor
integration is wired in. `main/main.cpp`'s `next_debug_raw_value()` is a placeholder.

**Tier 2 — BLE glucometer client (done, untested against real hardware).** A
completely separate capability from Step 2/3 above, gated behind
`CGM_ENABLE_BLE_GLUCOMETER` in menuconfig (default off) so it doesn't interfere with the
WiFi debug loop. Unlike Stelo/G7 (see the research doc), ordinary consumer BLE-capable
blood glucometers implement a real, standardized, publicly-documented protocol — the
Bluetooth SIG "Glucose Profile" (service `0x1808`, characteristic `0x2A18`) — no
reverse-engineering required. This firmware scans for any nearby device advertising
that service, connects, subscribes to Glucose Measurement notifications, and posts each
parsed reading directly to **cloud-backend's `POST /readings/device`** (bypassing
`mobile-bridge` entirely — a glucometer's value is already a final mg/dL number, unlike
raw sensor telemetry, so there's no calibration step to apply).

Implementation:
- `main/glucose_profile.c`/`.h` — a pure, ESP-IDF-independent parser for the Glucose
  Measurement byte format. Verified against real test vectors in
  `main/glucose_profile_test.c` (`cc glucose_profile.c glucose_profile_test.c -lm -o
  /tmp/t && /tmp/t` — no ESP-IDF toolchain needed), including the exact
  kg/L→mg/dL conversion factor and byte offsets cross-checked against a real working
  reference implementation (`jbravo94/simple-ble-glucose-reader`, itself ported from
  xDrip+'s own `GlucoseReadingRx.java`) rather than derived from spec text alone.
- `main/ble_glucose_client.c`/`.h` — the NimBLE central: scan/connect/discover/subscribe
  flow adapted from ESP-IDF's own bundled `examples/bluetooth/nimble/blecent` (reusing
  its `nimble_central_utils` peer-tracking component via `main/idf_component.yml`,
  rather than reimplementing that bookkeeping blind against no hardware).
- `main/device_reading.c`/`.h` — posts to cloud-backend directly (needs
  `CGM_CLOUD_BACKEND_URL` + `CGM_CLOUD_BACKEND_API_KEY` in menuconfig, matching
  cloud-backend's `CGM_SHARED_SECRET`).
- Adding BLE required switching the partition table to `Single App (large)`
  (`idf.py menuconfig` → Partition Table) — the combined WiFi+BLE/NimBLE image no
  longer fits the default `Single App` (1MB) factory partition.

**Honest limitation:** no real BLE glucometer has been tested against this yet — same
situation Step 2 was in before any sensor existed. What's actually verified: it compiles
cleanly with the flag on or off (`idf.py build`, both configurations), and the parser
logic is verified against hand-constructed byte-level test vectors covering both unit
systems, the NaN-reading sentinel, all-optional-fields-present offset arithmetic, and a
truncated-buffer rejection case.

**Step 3 — CGM sensor integration (blocked, see `DEXCOM_BLE_PROTOCOL_RESEARCH.md`).** The
original assumption here (that Stelo broadcasts BLE natively the same way G6/G7 do, so
an ESP32 could act as a BLE central and read it directly) turned out not to be confirmed
by real research: digging into xDrip+'s actual open-source implementation shows it has a
complete, working, reverse-engineered raw-BLE protocol for the **G5 and G6 only**. For
G7 and Stelo, xDrip+ instead reads glucose values out of Android notifications posted by
Dexcom's own official app — a phone-side mechanism an ESP32 can't replicate. The research
doc lays out the real options (G5/G6 as a protocol testbed, an Android-phone-in-the-loop
design for Stelo, original reverse-engineering once a real Stelo is in hand, or a pivot
to Sibionics GS1 — a sensor with a real open-source BLE protocol implementation
via the `Juggluco` project — that a future white-label tier could target directly).

## Build & flash

Same toolchain already proven working for PhysicalKey (`~/esp-idf-test/esp-idf`,
ESP-IDF v5.3.1), but this project's ESP32 board(s) are new/separate hardware, not
PhysicalKey's — no flash/NVS encryption is enabled here, so a plain flash is correct
(PhysicalKey's `encrypted-flash` requirement does not apply to this project's boards).

```bash
source ~/esp-idf-test/esp-idf/export.sh
cd hardware-bridge/HardwareBridge
idf.py set-target esp32
idf.py menuconfig   # under "Canine CGM Hardware Bridge Configuration":
                     #   - WiFi SSID / password
                     #   - mobile-bridge base URL (e.g. http://<your-machine-ip>:9000)
                     #   - Dog ID (must already exist in cloud-backend, e.g. via
                     #     POST /profile against mobile-bridge)
                     #   - Enable tier-2 BLE glucometer client (off by default) +
                     #     cloud-backend base URL / API key, if using tier 2
                     # Also under Partition Table: "Single App (large)" is required
                     # once BLE is enabled — the default 1MB factory partition is too
                     # small for WiFi+BLE/NimBLE together.
idf.py -p /dev/cu.usbserial-XXXX build flash monitor
```

## Verifying Step 2 end-to-end

With `cloud-backend` and `mobile-bridge` running locally (see the top-level README) and a
dog already created, flash this firmware pointed at your machine's LAN IP (not
`localhost` — the board is a separate device on the network) and watch:

- The serial monitor log a `POST .../telemetry/frame -> HTTP 200 (ok)` line every
  `CGM_DEBUG_FRAME_INTERVAL_SECONDS`.
- `cloud-backend`'s own log show the usual `Dog BG: ... mg/dL` line per reading.
- `/dashboard/` update live with the debug sine-wave values.
