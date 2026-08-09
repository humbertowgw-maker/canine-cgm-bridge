# hardware-bridge

ESP32/ESP-IDF firmware that will eventually read a real FreeStyle Libre 2 sensor (via a
Bubble/MiaoMiao NFC→BLE transmitter) and forward readings to `mobile-bridge` over WiFi,
using the exact same `POST /telemetry/frame` schema `cloud-backend/simulator/simulate_dog_sensor.py`
already uses — so `mobile-bridge` and `cloud-backend` need zero changes.

## Current state (Step 2 of the build plan)

WiFi connect + SNTP time sync + a debug timer that posts a fake, slowly-varying
`TelemetryFrame` on a configurable interval. This proves the WiFi → HTTP →
mobile-bridge → cloud-backend path on real hardware *before* any Libre/Bubble sensor is
in hand. `main/main.cpp`'s `next_debug_raw_value()` is explicitly a placeholder, replaced
in Step 3 once a Bubble/MiaoMiao transmitter is available: a BLE central connection reads
it directly, using the real packet format pulled from xDrip+'s open-source implementation
(`NightscoutFoundation/xDrip` on GitHub) at that point — not fabricated in advance.

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
