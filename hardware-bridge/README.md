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

## Current state (Step 2 of the build plan — done)

WiFi connect + SNTP time sync + a debug timer that posts a fake, slowly-varying
`TelemetryFrame` on a configurable interval. This proves the WiFi → HTTP →
mobile-bridge → cloud-backend path on real hardware before any sensor integration is
wired in. `main/main.cpp`'s `next_debug_raw_value()` is explicitly a placeholder, to be
replaced once Step 3's approach is decided (see `DEXCOM_BLE_PROTOCOL_RESEARCH.md`).

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
