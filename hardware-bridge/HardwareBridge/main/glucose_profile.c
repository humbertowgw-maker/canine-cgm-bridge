#include "glucose_profile.h"

#define FLAG_TIME_OFFSET_PRESENT 0x01
#define FLAG_CONCENTRATION_TYPE_LOCATION_PRESENT 0x02
#define FLAG_UNIT_IS_MOL_L 0x04
#define FLAG_SENSOR_STATUS_PRESENT 0x08

#define SFLOAT_NAN 0x07FF

static uint16_t read_u16le(const uint8_t *p) {
    return (uint16_t)(p[0] | (p[1] << 8));
}

static int32_t sign_extend(uint32_t value, int bits) {
    uint32_t mask = 1u << (bits - 1);
    if (value & mask) {
        return (int32_t)(value | ~((1u << bits) - 1));
    }
    return (int32_t)value;
}

// IEEE 11073-20601 16-bit SFLOAT: 4-bit signed exponent (high nibble of the
// high byte), 12-bit signed mantissa. Returns false for the NaN sentinel
// (raw == 0x07FF) — the glucometer explicitly reporting "no value".
static bool decode_sfloat(uint16_t raw, double *out) {
    if (raw == SFLOAT_NAN) {
        return false;
    }
    int32_t mantissa = sign_extend(raw & 0x0FFF, 12);
    int32_t exponent = sign_extend((raw >> 12) & 0x0F, 4);

    double value = (double)mantissa;
    if (exponent > 0) {
        for (int i = 0; i < exponent; i++) value *= 10.0;
    } else {
        for (int i = 0; i < -exponent; i++) value /= 10.0;
    }
    *out = value;
    return true;
}

bool glucose_profile_parse_measurement(const uint8_t *data, size_t len, glucose_measurement_t *out) {
    if (data == NULL || out == NULL || len < 10) {
        return false;
    }

    uint8_t flags = data[0];
    out->sequence = read_u16le(&data[1]);
    out->year = read_u16le(&data[3]);
    out->month = data[5];
    out->day = data[6];
    out->hour = data[7];
    out->minute = data[8];
    out->second = data[9];

    size_t index = 10;

    if (flags & FLAG_TIME_OFFSET_PRESENT) {
        if (len < index + 2) return false;
        // Time Offset (minutes, signed) not currently consumed — the caller
        // timestamps with its own synced clock rather than trusting this.
        index += 2;
    }

    if (!(flags & FLAG_CONCENTRATION_TYPE_LOCATION_PRESENT)) {
        // Glucose Concentration is optional per the spec, but useless to us
        // without it — this measurement has nothing to report.
        return false;
    }

    if (len < index + 2) return false;
    uint16_t raw_concentration = read_u16le(&data[index]);
    double concentration;
    if (!decode_sfloat(raw_concentration, &concentration)) {
        return false; // NaN sentinel — glucometer reported no value
    }
    index += 2;

    if (flags & FLAG_UNIT_IS_MOL_L) {
        // mol/L -> mmol/L -> mg/dL. 1 mmol/L glucose = 18.0182 mg/dL.
        out->glucose_mg_dl = concentration * 1000.0 * 18.0182;
    } else {
        // kg/L -> mg/dL: 1 kg/L = 100,000 mg/dL. Verified against
        // simple-ble-glucose-reader's GlucoseReadingRx.js (`kgl * 100000`),
        // itself ported from xDrip+'s GlucoseReadingRx.java.
        out->glucose_mg_dl = concentration * 100000.0;
    }

    // Type/Sample-Location byte follows (guaranteed present — we returned
    // above if that flag bit was clear). We don't use it (not relevant to
    // the trend/alert pipeline), so just skip over it.
    if (len < index + 1) return false;
    index += 1;

    if (flags & FLAG_SENSOR_STATUS_PRESENT) {
        if (len < index + 2) return false;
        // Sensor Status Annunciation not currently consumed.
        index += 2;
    }

    return true;
}
