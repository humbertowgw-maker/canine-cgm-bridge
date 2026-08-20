#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Starts the NimBLE host and begins scanning for, connecting to, and
// running the Sibionics GS1 handshake (see gs1_protocol.h) against any
// nearby device advertising GATT service 0000ff30-...-34fb. Parsed glucose
// records are posted to cloud-backend via device_reading_post() with
// source "gs1_direct_ble" — real-time, no delay, unlike the Tier 3
// HealthKit-sync path. Runs its own FreeRTOS task and returns immediately.
//
// NOTE: shares the same constraint as ble_glucose_client_start() — NimBLE
// only supports one host per build. Do not enable both
// CGM_ENABLE_BLE_GLUCOMETER and CGM_ENABLE_GS1_SENSOR in the same firmware
// image; a physical collar runs whichever single tier its owner's hardware
// matches.
void gs1_sensor_client_start(void);

#ifdef __cplusplus
}
#endif
