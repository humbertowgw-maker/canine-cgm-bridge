#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Posts an already-final mg/dL glucose value straight to cloud-backend's
// POST /readings/device — bypassing mobile-bridge, since (unlike raw sensor
// telemetry) a BLE glucometer's value needs no calibration step. Returns
// true on a 2xx response from cloud-backend. Implemented in C++
// (device_reading.cpp, matching telemetry.cpp's style) but called from the
// plain-C ble_glucose_client.c — the extern "C" linkage here is required for
// that to link, not just style.
bool device_reading_post(int dog_id, double glucose_mg_dl, const char *source);

#ifdef __cplusplus
}
#endif
