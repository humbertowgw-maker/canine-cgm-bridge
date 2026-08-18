// Pure parser for the Bluetooth SIG "Glucose Measurement" characteristic
// (service 0x1808, characteristic 0x2A18). Deliberately has zero ESP-IDF
// dependencies so it can be compiled and unit-tested with a plain host
// compiler, independent of the idf.py toolchain — see glucose_profile_test.c.
//
// Byte layout and the kg/L -> mg/dL conversion factor were verified against
// a real, working reference implementation (jbravo94/simple-ble-glucose-reader,
// itself ported from NightscoutFoundation/xDrip's GlucoseReadingRx.java) during
// this session, not derived from the Bluetooth SIG spec text alone.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint16_t sequence;
    double glucose_mg_dl;
    // Base Time fields, as broadcast by the glucometer (its own clock, not
    // necessarily synced to anything) — kept for logging/debugging; the
    // caller timestamps the HTTP POST with its own synced clock instead of
    // trusting these.
    uint16_t year;
    uint8_t month, day, hour, minute, second;
} glucose_measurement_t;

// Parses one Glucose Measurement (0x2A18) notification payload.
// Returns false if `len` is too short for the fields the Flags byte claims
// are present, or if the Glucose Concentration field is the IEEE 11073-20601
// NaN sentinel (0x07FF mantissa/exponent bits) — i.e. the glucometer itself
// reported "no value" (e.g. a control/QC strip reading).
bool glucose_profile_parse_measurement(const uint8_t *data, size_t len,
                                        glucose_measurement_t *out);

#ifdef __cplusplus
}
#endif
