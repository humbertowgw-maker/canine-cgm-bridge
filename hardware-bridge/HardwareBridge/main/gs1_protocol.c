// Sibionics GS1 protocol implementation. See gs1_protocol.h for the full
// provenance note. Every packet layout, checksum formula, and the RC4 key
// itself are transcribed directly from Juggluco's interpret_data.cpp /
// handleData.cpp (github.com/j-kaltes/Juggluco, GPL-3.0) — nothing here is
// guessed except where a comment says so explicitly (the auth key-table
// index, and the exact retry/backoff timing of the full state machine,
// which this file does not attempt to fully replicate — see the dispatch
// code comments in gs1_protocol.h).
#include "gs1_protocol.h"

#include <string.h>

const uint8_t gs1_rc4_key[GS1_RC4_KEY_LEN] = {
    0x01, 0x38, 0x0b, 0x9a, 0x00, 0x5b, 0x02, 0x5d,
    0xcd, 0x9e, 0xc3, 0x99, 0x09, 0x37, 0xaa, 0xe8,
};

const char *const gs1_key_table[GS1_KEY_TABLE_SIZE] = {
    "THE544U0TYITE461", // com.sisensing.sijoy
    "LQSS54U0RURUA99J", // com.sisensing.rusibionics
    "GKSHGDU0TYA456G4", // com.sisensing.sisensingcgm
    "GKSHGDU0TYA456G4", // com.sisensing.eco
    "THE544U0TYITE461", // com.sisensing.gs3
    "GKSHGDU0TYA456G4", // com.sibionics.gstoc  -- marked "Guess" in Juggluco's own source
};

const uint8_t gs1_reset_bytes[4] = {0x24, 0xE7, 0x6F, 0x34};

void gs1_rc4_xor(const uint8_t *key, uint32_t key_len, int skip_count,
                  const uint8_t *in, uint8_t *out, uint32_t len) {
    uint8_t S[256];
    for (int i = 0; i < 256; i++) S[i] = (uint8_t)i;

    uint32_t j = 0;
    for (uint32_t i = 0; i < 256; i++) {
        j = (j + S[i] + key[i % key_len]) & 0xFF;
        uint8_t tmp = S[i];
        S[i] = S[j];
        S[j] = tmp;
    }

    uint32_t si = 0, sj = 0;
    for (int k = 0; k < skip_count; k++) {
        si = (si + 1) & 0xFF;
        uint8_t a = S[si];
        sj = (sj + a) & 0xFF;
        uint8_t b = S[sj];
        S[si] = b;
        S[sj] = a;
    }

    for (uint32_t k = 0; k < len; k++) {
        si = (si + 1) & 0xFF;
        uint8_t a = S[si];
        sj = (sj + a) & 0xFF;
        uint8_t b = S[sj];
        S[si] = b;
        S[sj] = a;
        out[k] = S[(a + b) & 0xFF] ^ in[k];
    }
}

bool gs1_build_auth_packet(const uint8_t device_addr_reversed[6], int key_index,
                            uint8_t *out, size_t out_cap) {
    if (out == NULL || out_cap < 26 || key_index < 0 || key_index >= GS1_KEY_TABLE_SIZE) {
        return false;
    }
    uint8_t buf[26];
    buf[0] = 0x19;
    buf[1] = 0x01;
    buf[2] = 0x00;
    memcpy(&buf[3], device_addr_reversed, 6);
    memcpy(&buf[9], gs1_key_table[key_index], 16);

    uint8_t sum = 0;
    for (int i = 0; i < 25; i++) sum = (uint8_t)(sum + buf[i]);
    buf[25] = (uint8_t)(0 - sum);

    gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, buf, out, 26);
    return true;
}

bool gs1_build_time_packet(uint32_t unix_time, uint8_t *out, size_t out_cap) {
    if (out == NULL || out_cap < 7) return false;
    uint8_t payload[7];
    payload[0] = 0x06; // magic 0x0306, little-endian
    payload[1] = 0x03;
    payload[2] = (uint8_t)(unix_time & 0xFF);
    payload[3] = (uint8_t)((unix_time >> 8) & 0xFF);
    payload[4] = (uint8_t)((unix_time >> 16) & 0xFF);
    payload[5] = (uint8_t)((unix_time >> 24) & 0xFF);
    uint8_t tsum = (uint8_t)(payload[2] + payload[3] + payload[4] + payload[5]);
    payload[6] = (uint8_t)(-9 - tsum);

    gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, payload, out, 7);
    return true;
}

bool gs1_build_activation_packet(uint32_t unix_time, uint8_t *out, size_t out_cap) {
    if (out == NULL || out_cap < 11) return false;
    uint8_t payload[11];
    payload[0] = 0x0a; // magic 0x070a, little-endian
    payload[1] = 0x07;
    uint32_t num = 1234; // fixed constant, matches Juggluco's getActivation()
    payload[2] = (uint8_t)(unix_time & 0xFF);
    payload[3] = (uint8_t)((unix_time >> 8) & 0xFF);
    payload[4] = (uint8_t)((unix_time >> 16) & 0xFF);
    payload[5] = (uint8_t)((unix_time >> 24) & 0xFF);
    payload[6] = (uint8_t)(num & 0xFF);
    payload[7] = (uint8_t)((num >> 8) & 0xFF);
    payload[8] = (uint8_t)((num >> 16) & 0xFF);
    payload[9] = (uint8_t)((num >> 24) & 0xFF);
    uint8_t sum = 0;
    for (int i = 2; i < 10; i++) sum = (uint8_t)(sum + payload[i]);
    payload[10] = (uint8_t)(-0x11 - sum);

    gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, payload, out, 11);
    return true;
}

bool gs1_build_ask_values_packet(uint16_t index, uint8_t *out, size_t out_cap) {
    if (out == NULL || out_cap < 7) return false;
    uint8_t payload[7];
    payload[0] = 0x06; // cmd 0x0806, little-endian
    payload[1] = 0x08;
    payload[2] = (uint8_t)(index & 0xFF);
    payload[3] = (uint8_t)((index >> 8) & 0xFF);
    payload[4] = 0x00; // start0, always 0
    payload[5] = 0x00;
    int8_t index_lo = (int8_t)payload[2];
    int8_t index_hi = (int8_t)payload[3];
    int8_t start_lo = (int8_t)payload[4];
    int8_t start_hi = (int8_t)payload[5];
    payload[6] = (uint8_t)(-0x0e - (index_lo + index_hi + start_lo + start_hi));

    gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, payload, out, 7);
    return true;
}

// Maps a raw (already-decrypted) ACK-shaped packet's cmd_id to Juggluco's
// emit_cmd_ack() dispatch code. type = 0xC000 + cmd_id + 1 in the original;
// since 0xC000 shares no bits with a byte, that's equivalent to just
// switching on cmd_id directly.
static gs1_dispatch_code_t ack_dispatch_for_cmd(uint8_t cmd_id, uint8_t status, uint8_t aux) {
    switch (cmd_id) {
        case 0x08: return GS1_DISPATCH_NONE; // type 0xC009 -> 9 in the original, which processchanged() treats as a no-op
        case 0x00: return GS1_DISPATCH_RETRY_AUTH; // type 0xC001 -> 4
        case 0x01:
            if (status != 1) {
                if ((aux & 0xff) != 3) return GS1_DISPATCH_RETRY_AUTH; // -> 4
            }
            return GS1_DISPATCH_ACTIVATE; // -> 6
        case 0x03: return GS1_DISPATCH_ASK_VALUES; // type 0xC004 -> 7
        case 0x07: return GS1_DISPATCH_SEND_TIME;  // type 0xC008 -> 5
        default: return GS1_DISPATCH_NONE;         // -> 8 in the original (generic ack/backoff); collapsed to NONE here
    }
}

int gs1_parse_notification(const uint8_t *raw, size_t raw_len,
                            gs1_glucose_record_t *records, int max_records,
                            gs1_dispatch_code_t *out_dispatch_code) {
    if (out_dispatch_code) *out_dispatch_code = GS1_DISPATCH_NONE;
    if (raw == NULL || raw_len == 0 || raw_len > 250) return -1;

    uint8_t pkt[250] = {0};
    gs1_rc4_xor(gs1_rc4_key, GS1_RC4_KEY_LEN, 0, raw, pkt, (uint32_t)raw_len);

    uint8_t length = pkt[0];
    uint8_t cmd_id = pkt[1];

    // Fixed-length 5-byte ACK packet (length field == 4).
    if (length == 4) {
        if (raw_len < 5) return -1;
        uint8_t status = pkt[2];
        uint8_t aux = pkt[3];
        uint8_t checksum = pkt[4];
        uint8_t expected = (uint8_t)(-(cmd_id + status + aux + 4));
        if (checksum != expected) return -1;
        if (out_dispatch_code) *out_dispatch_code = ack_dispatch_for_cmd(cmd_id, status, aux);
        return 0;
    }

    // Variable-length packet: checksum at pkt[length] must match.
    if (length == 0 || length >= 250 || raw_len < (size_t)(length + 1)) return -1;
    uint8_t sum = 0;
    for (int i = 0; i < length; i++) sum = (uint8_t)(sum + pkt[i]);
    uint8_t expected_checksum = (uint8_t)(-sum);
    if (pkt[length] != expected_checksum) return -1;

    if (cmd_id != 0x08) {
        // Other record types (activity/day/error-info/etc.) exist in the
        // real protocol but aren't implemented here — this firmware only
        // extracts glucose measurements. Recognized-but-unhandled, not an
        // error.
        return 0;
    }

    uint8_t status = pkt[2]; // record count for cmd 0x08
    if (status == 0) return 0; // valid empty response, nothing to report

    // Payload starts at pkt[3]: glucoseRecordsStart{u16 index; u32 itime}
    // then `status` glucoseItem{u16 temp; u16 dump; u16 current; u16 extra}
    // records, 60 seconds apart, each __attribute__((packed)).
    const uint8_t *p = pkt + 3;
    uint16_t start_index;
    uint32_t itime;
    memcpy(&start_index, p, 2);
    memcpy(&itime, p + 2, 4);
    p += 6;

    int count = status;
    if (count > max_records) count = max_records;

    for (int i = 0; i < count; i++) {
        uint16_t current;
        memcpy(&current, p + 4, 2); // glucoseItem: temp(2) dump(2) current(2) extra(2)
        records[i].index = (uint16_t)(start_index + i);
        records[i].itime = itime + (uint32_t)(i * 60);
        records[i].glucose_mg_dl = current / 10.0;
        p += 8; // sizeof(glucoseItem)
    }

    return count;
}
