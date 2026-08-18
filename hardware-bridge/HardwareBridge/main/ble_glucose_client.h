#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Starts the NimBLE host and begins scanning for, connecting to, and
// subscribing to notifications from any nearby device advertising the
// standard Bluetooth SIG Glucose Service (0x1808) — i.e. an ordinary
// consumer BLE-capable blood glucometer, not a CGM. Each parsed reading is
// posted to cloud-backend via device_reading_post(). Runs its own FreeRTOS
// task (via nimble_port_freertos_init) and returns immediately — safe to
// call before entering another loop in app_main, e.g. the Step 2 WiFi
// debug-telemetry loop.
void ble_glucose_client_start(void);

#ifdef __cplusplus
}
#endif
