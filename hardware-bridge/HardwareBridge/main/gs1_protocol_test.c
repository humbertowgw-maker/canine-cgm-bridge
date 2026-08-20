// Standalone host-compiled test for gs1_protocol.c's pure functions — no
// ESP-IDF toolchain or real GS1 sensor needed. Compile & run directly:
//
//   cc -std=c11 -Wall -Wextra -Werror gs1_protocol.c gs1_protocol_test.c \
//     -o /tmp/gs1_protocol_test && /tmp/gs1_protocol_test
//
// Test vectors are hand-built from the packet layouts and checksum formulas
// transcribed from Juggluco's real source (see gs1_protocol.h/.c headers
// for exact file citations) — not fabricated. Since no real GS1 sensor is
// available, the "receive" side is exercised by RC4-encrypting a
// hand-constructed plaintext packet with this file's own key/cipher (the
// same key gs1_protocol.c uses) and confirming gs1_parse_notification
// correctly reverses that and extracts the right values — this validates
// the parsing/checksum logic is internally consistent and matches the
// documented wire format, though it cannot validate that a real sensor's
// bytes match this format until one is available to test against.
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "gs1_protocol.h"

static int failures = 0;

#define CHECK(cond, msg)                                                     \
    do {                                                                     \
        if (!(cond)) {                                                       \
            printf("FAIL: %s (%s:%d)\n", msg, __FILE__, __LINE__);           \
            failures++;                                                      \
        }                                                                    \
    } while (0)

static bool approx(double a, double b) { return fabs(a - b) < 1e-6; }

int main(void) {
    // RC4 round-trip: encrypting then decrypting with the same key must
    // recover the original plaintext exactly (basic cipher self-consistency).
    {
        const uint8_t plain[] = "the quick brown fox jumps";
        uint8_t enc[sizeof(plain)];
        uint8_t dec[sizeof(plain)];
        gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, plain, enc, sizeof(plain));
        gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, enc, dec, sizeof(plain));
        CHECK(memcmp(plain, dec, sizeof(plain)) == 0, "RC4 encrypt-then-decrypt recovers plaintext");
        CHECK(memcmp(plain, enc, sizeof(plain)) != 0, "RC4 ciphertext actually differs from plaintext");
    }

    // Auth packet: build it, then decrypt with the same key and confirm the
    // plaintext header/address/key-block/checksum land where the format says.
    {
        uint8_t addr[6] = {0x11, 0x22, 0x33, 0x44, 0x55, 0x66};
        uint8_t out[26];
        bool ok = gs1_build_auth_packet(addr, GS1_DEFAULT_KEY_INDEX, out, sizeof(out));
        CHECK(ok, "auth packet builds successfully");

        uint8_t plain[26];
        gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, out, plain, 26);
        CHECK(plain[0] == 0x19 && plain[1] == 0x01 && plain[2] == 0x00, "auth packet magic header");
        CHECK(memcmp(plain + 3, addr, 6) == 0, "auth packet embeds device address");
        CHECK(memcmp(plain + 9, gs1_key_table[GS1_DEFAULT_KEY_INDEX], 16) == 0, "auth packet embeds the key-table string");
        uint8_t sum = 0;
        for (int i = 0; i < 25; i++) sum = (uint8_t)(sum + plain[i]);
        CHECK(plain[25] == (uint8_t)(0 - sum), "auth packet checksum matches formula");
    }

    // Time packet: magic 0x0306, given timestamp, correct checksum.
    {
        uint8_t out[7];
        uint32_t t = 0x12345678;
        bool ok = gs1_build_time_packet(t, out, sizeof(out));
        CHECK(ok, "time packet builds successfully");
        uint8_t plain[7];
        gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, out, plain, 7);
        CHECK(plain[0] == 0x06 && plain[1] == 0x03, "time packet magic == 0x0306 little-endian");
        uint32_t decoded_t = (uint32_t)plain[2] | ((uint32_t)plain[3] << 8) |
                              ((uint32_t)plain[4] << 16) | ((uint32_t)plain[5] << 24);
        CHECK(decoded_t == t, "time packet embeds the exact timestamp");
        uint8_t tsum = (uint8_t)(plain[2] + plain[3] + plain[4] + plain[5]);
        CHECK(plain[6] == (uint8_t)(-9 - tsum), "time packet checksum matches formula");
    }

    // Ask-values packet: cmd 0x0806, requested index, start always 0.
    {
        uint8_t out[7];
        bool ok = gs1_build_ask_values_packet(0x00AB, out, sizeof(out));
        CHECK(ok, "ask-values packet builds successfully");
        uint8_t plain[7];
        gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, out, plain, 7);
        CHECK(plain[0] == 0x06 && plain[1] == 0x08, "ask-values cmd == 0x0806 little-endian");
        CHECK(plain[2] == 0xAB && plain[3] == 0x00, "ask-values index encoded little-endian");
        CHECK(plain[4] == 0x00 && plain[5] == 0x00, "ask-values start always 0");
    }

    // Full round trip: hand-build a plaintext glucose-data response exactly
    // per the confirmed format (glucoseRecordsStart + 2 glucoseItem records
    // + glucoseRecordsEnd), RC4-encrypt it as a real sensor notification
    // would arrive, and confirm gs1_parse_notification recovers the right
    // mg/dL values and timestamps.
    {
        uint8_t plain[3 + 6 + 2 * 8 + 3 + 1]; // header(3) + recordsStart(6) + 2*item(8) + recordsEnd(3) + checksum(1)
        int n = 0;
        plain[n++] = 0; // length placeholder, fixed below
        plain[n++] = 0x08; // cmd_id: glucose data
        plain[n++] = 2;    // status: record count == 2

        // glucoseRecordsStart{u16 index; u32 itime}
        uint16_t start_index = 100;
        uint32_t itime = 1700000000;
        memcpy(plain + n, &start_index, 2); n += 2;
        memcpy(plain + n, &itime, 4); n += 4;

        // record 0: current = 1330 -> 133.0 mg/dL
        uint16_t temp0 = 0, dump0 = 0, current0 = 1330, extra0 = 0;
        memcpy(plain + n, &temp0, 2); n += 2;
        memcpy(plain + n, &dump0, 2); n += 2;
        memcpy(plain + n, &current0, 2); n += 2;
        memcpy(plain + n, &extra0, 2); n += 2;

        // record 1: current = 985 -> 98.5 mg/dL
        uint16_t temp1 = 0, dump1 = 0, current1 = 985, extra1 = 0;
        memcpy(plain + n, &temp1, 2); n += 2;
        memcpy(plain + n, &dump1, 2); n += 2;
        memcpy(plain + n, &current1, 2); n += 2;
        memcpy(plain + n, &extra1, 2); n += 2;

        // glucoseRecordsEnd{u16 reindex; u8 sign}
        uint16_t reindex = 1;
        plain[n++] = (uint8_t)(reindex & 0xFF);
        plain[n++] = (uint8_t)((reindex >> 8) & 0xFF);
        plain[n++] = 0; // sign

        uint8_t length = (uint8_t)n; // length field covers bytes [0..n-1]
        plain[0] = length;

        uint8_t sum = 0;
        for (int i = 0; i < n; i++) sum = (uint8_t)(sum + plain[i]);
        uint8_t checksum = (uint8_t)(-sum);
        plain[n++] = checksum;

        uint8_t encrypted[64];
        gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, plain, encrypted, (uint32_t)n);

        gs1_glucose_record_t records[8];
        gs1_dispatch_code_t dispatch;
        int count = gs1_parse_notification(encrypted, (size_t)n, records, 8, &dispatch);

        CHECK(count == 2, "glucose response: parsed 2 records");
        CHECK(records[0].index == 100, "record 0 index");
        CHECK(approx(records[0].glucose_mg_dl, 133.0), "record 0 glucose == 133.0 mg/dL");
        CHECK(records[0].itime == itime, "record 0 itime == batch start time");
        CHECK(records[1].index == 101, "record 1 index increments");
        CHECK(approx(records[1].glucose_mg_dl, 98.5), "record 1 glucose == 98.5 mg/dL");
        CHECK(records[1].itime == itime + 60, "record 1 itime is 60s after record 0");
    }

    // Corrupted checksum must be rejected, not silently parsed.
    {
        uint8_t plain[8] = {4, 0x07, 1, 3, 0}; // ACK-shaped, length=4
        uint8_t sum = (uint8_t)(plain[1] + plain[2] + plain[3] + 4);
        plain[4] = (uint8_t)(-sum + 1); // deliberately wrong checksum
        uint8_t encrypted[8];
        gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, plain, encrypted, 5);

        gs1_glucose_record_t records[4];
        gs1_dispatch_code_t dispatch;
        int result = gs1_parse_notification(encrypted, 5, records, 4, &dispatch);
        CHECK(result == -1, "corrupted ACK checksum is rejected");
    }

    // Valid ACK packet with cmd_id 0x07 must dispatch to SEND_TIME.
    {
        uint8_t plain[5];
        plain[0] = 4;    // length
        plain[1] = 0x07; // cmd_id
        plain[2] = 0;    // status
        plain[3] = 0;    // aux
        uint8_t sum = (uint8_t)(plain[1] + plain[2] + plain[3] + 4);
        plain[4] = (uint8_t)(-sum);
        uint8_t encrypted[5];
        gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, plain, encrypted, 5);

        gs1_glucose_record_t records[4];
        gs1_dispatch_code_t dispatch = GS1_DISPATCH_NONE;
        int result = gs1_parse_notification(encrypted, 5, records, 4, &dispatch);
        CHECK(result == 0, "valid ACK packet parses with 0 records");
        CHECK(dispatch == GS1_DISPATCH_SEND_TIME, "cmd_id 0x07 ACK dispatches to SEND_TIME");
    }

    if (failures == 0) {
        printf("All gs1_protocol parser test vectors passed.\n");
        return 0;
    }
    printf("%d test vector(s) FAILED.\n", failures);
    return 1;
}
