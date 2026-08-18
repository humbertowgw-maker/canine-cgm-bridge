// Standalone host-compiled test for glucose_profile.c's pure parser — no
// ESP-IDF toolchain needed, so this runs even before any board/BLE hardware
// exists. Compile & run directly on this machine:
//
//   cc -std=c11 -Wall -Wextra -Werror glucose_profile.c glucose_profile_test.c \
//     -o /tmp/glucose_profile_test && /tmp/glucose_profile_test
//
// Test vectors are hand-constructed per the verified Bluetooth SIG Glucose
// Measurement (0x2A18) byte layout, cross-checked against
// jbravo94/simple-ble-glucose-reader (itself ported from xDrip+'s
// GlucoseReadingRx.java) during this session.
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "glucose_profile.h"

static int failures = 0;

#define CHECK(cond, msg)                                                     \
    do {                                                                     \
        if (!(cond)) {                                                       \
            printf("FAIL: %s (%s:%d)\n", msg, __FILE__, __LINE__);           \
            failures++;                                                      \
        }                                                                    \
    } while (0)

static bool approx(double a, double b) { return fabs(a - b) < 1e-6; }

// SFLOAT encode helper for building test vectors (inverse of the decoder):
// mantissa is a signed 12-bit value, exponent a signed 4-bit value.
static uint16_t encode_sfloat(int32_t mantissa, int32_t exponent) {
    uint16_t m = (uint16_t)(mantissa & 0x0FFF);
    uint16_t e = (uint16_t)(exponent & 0x0F);
    return (uint16_t)((e << 12) | m);
}

int main(void) {
    // Vector 1: kg/L units, no time offset, no sensor status, no context.
    // 120 mg/dL == 0.00120 kg/L == mantissa 120, exponent -5 (120 * 10^-5 = 0.00120).
    // Flags: bit1 (concentration+type/location present) set, bit2 (units) clear (kg/L).
    {
        uint8_t packet[15];
        packet[0] = 0x02; // flags: concentration present, kg/L, no offset/status/context
        packet[1] = 0x2A; packet[2] = 0x00; // sequence = 42
        packet[3] = 0xEA; packet[4] = 0x07; // year = 2026 (0x07EA)
        packet[5] = 8;   // month
        packet[6] = 18;  // day
        packet[7] = 14;  // hour
        packet[8] = 30;  // minute
        packet[9] = 0;   // second
        uint16_t sf = encode_sfloat(120, -5);
        packet[10] = (uint8_t)(sf & 0xFF);
        packet[11] = (uint8_t)(sf >> 8);
        packet[12] = 0x00; // type/sample-location (unused by us)

        glucose_measurement_t out;
        bool ok = glucose_profile_parse_measurement(packet, sizeof(packet), &out);
        CHECK(ok, "vector 1: parse should succeed");
        CHECK(out.sequence == 42, "vector 1: sequence == 42");
        CHECK(out.year == 2026, "vector 1: year == 2026");
        CHECK(out.month == 8 && out.day == 18, "vector 1: month/day");
        CHECK(approx(out.glucose_mg_dl, 120.0), "vector 1: 120 mg/dL");
    }

    // Vector 2: mol/L units. 6.5 mmol/L ~= 117.12 mg/dL (6.5 * 18.0182).
    // mmol/L value 6.5 == 0.0065 mol/L == mantissa 65, exponent -4.
    {
        uint8_t packet[13];
        packet[0] = 0x06; // flags: concentration present (bit1) + mol/L units (bit2)
        packet[1] = 0x01; packet[2] = 0x00; // sequence = 1
        packet[3] = 0xEA; packet[4] = 0x07; // year 2026
        packet[5] = 1; packet[6] = 1; packet[7] = 0; packet[8] = 0; packet[9] = 0;
        uint16_t sf = encode_sfloat(65, -4);
        packet[10] = (uint8_t)(sf & 0xFF);
        packet[11] = (uint8_t)(sf >> 8);
        packet[12] = 0x00;

        glucose_measurement_t out;
        bool ok = glucose_profile_parse_measurement(packet, sizeof(packet), &out);
        CHECK(ok, "vector 2: parse should succeed");
        CHECK(fabs(out.glucose_mg_dl - 117.1183) < 1e-3, "vector 2: ~117.12 mg/dL from 6.5 mmol/L");
    }

    // Vector 3: NaN sentinel (0x07FF) — glucometer reported no value.
    {
        uint8_t packet[13];
        packet[0] = 0x02;
        packet[1] = 0x00; packet[2] = 0x00;
        packet[3] = 0xEA; packet[4] = 0x07;
        packet[5] = 1; packet[6] = 1; packet[7] = 0; packet[8] = 0; packet[9] = 0;
        packet[10] = 0xFF; packet[11] = 0x07; // raw SFLOAT 0x07FF == NaN
        packet[12] = 0x00;

        glucose_measurement_t out;
        bool ok = glucose_profile_parse_measurement(packet, sizeof(packet), &out);
        CHECK(!ok, "vector 3: NaN sentinel must be rejected, not treated as a real value");
    }

    // Vector 4: time offset present, glucose concentration present, sensor
    // status present — exercises every optional field's offset arithmetic.
    {
        uint8_t packet[17];
        packet[0] = 0x0B; // bits 0(time offset) + 1(concentration) + 3(sensor status)
        packet[1] = 0x05; packet[2] = 0x00; // sequence = 5
        packet[3] = 0xEA; packet[4] = 0x07;
        packet[5] = 3; packet[6] = 4; packet[7] = 5; packet[8] = 6; packet[9] = 7;
        packet[10] = 0x0A; packet[11] = 0x00; // time offset = 10 minutes
        uint16_t sf = encode_sfloat(95, -4); // 95 * 10^-4 = 0.0095 kg/L -> * 100000 = 950 mg/dL
        packet[12] = (uint8_t)(sf & 0xFF);
        packet[13] = (uint8_t)(sf >> 8);
        packet[14] = 0x00; // type/location
        packet[15] = 0x00; packet[16] = 0x00; // sensor status

        glucose_measurement_t out;
        bool ok = glucose_profile_parse_measurement(packet, sizeof(packet), &out);
        CHECK(ok, "vector 4: parse with all optional fields should succeed");
        CHECK(approx(out.glucose_mg_dl, 950.0), "vector 4: offset arithmetic lands on the right concentration bytes");
    }

    // Vector 5: too-short buffer claiming a field it doesn't have room for.
    {
        uint8_t packet[11]; // flags say concentration present, but buffer ends right after
        packet[0] = 0x02;
        packet[1] = 0x00; packet[2] = 0x00;
        packet[3] = 0xEA; packet[4] = 0x07;
        packet[5] = 1; packet[6] = 1; packet[7] = 0; packet[8] = 0; packet[9] = 0;
        packet[10] = 0x00; // only 1 of the 2 concentration bytes present

        glucose_measurement_t out;
        bool ok = glucose_profile_parse_measurement(packet, sizeof(packet), &out);
        CHECK(!ok, "vector 5: truncated buffer must be rejected, not read out of bounds");
    }

    if (failures == 0) {
        printf("All glucose_profile parser test vectors passed.\n");
        return 0;
    }
    printf("%d test vector(s) FAILED.\n", failures);
    return 1;
}
