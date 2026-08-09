#pragma once

// Posts one telemetry frame to mobile-bridge's POST /telemetry/frame, matching
// the exact schema TelemetryFrame expects (mobile-bridge/app/models.py):
// dog_id, timestamp (ISO-8601 UTC), raw_value, temperature_f, battery_voltage.
// This is the same endpoint and schema simulate_dog_sensor.py's HTTP mode
// already uses, so mobile-bridge/cloud-backend need no changes.
// Returns true on a 2xx response from mobile-bridge.
bool telemetry_post_frame(int dog_id, double raw_value, double temperature_f,
                           double battery_voltage);
