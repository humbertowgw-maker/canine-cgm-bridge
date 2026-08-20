#pragma once

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Sibionics GS1 BLE protocol — reverse-engineered from Juggluco
// (github.com/j-kaltes/Juggluco, GPL-3.0), specifically the from-scratch
// reimplementation in Common/src/main/cpp/sibionics/interpret_data.cpp and
// handleData.cpp (dated 2026-05-06 in that repo, the newer of two Sibionics
// code paths there — the older one in start.cpp/process.cpp depends on
// dlopen()'d proprietary .so algorithm libraries and is NOT usable outside
// Android; everything below avoids that path entirely).
//
// GATT: service 0000ff30-...-34fb, notify characteristic 0000ff31-...-34fb,
// write characteristic 0000ff32-...-34fb (SiGattCallback.java in Juggluco).
//
// Every command/response packet (except the fixed reset bytes) is XORed
// with standard RC4 (KSA+PRGA, no drop) using a single fixed 16-byte key —
// not derived per-device, unlike Dexcom G5/G6's transmitter-ID-keyed AES.
// This key is embedded directly in Juggluco's source (interpret_data.cpp).
#define GS1_RC4_KEY_LEN 16
extern const uint8_t gs1_rc4_key[GS1_RC4_KEY_LEN];

// Standard RC4: KSA then PRGA, XORing `in` into `out`. `skip_count` is
// always 0 for every call this protocol makes (no RC4-drop variant used).
void gs1_rc4_xor(const uint8_t *key, uint32_t key_len, int skip_count,
                  const uint8_t *in, uint8_t *out, uint32_t len);

// The auth packet's trailing 16 bytes are one of several fixed strings,
// selected by an app-package-specific index Juggluco calls "sisubtype".
// NOT CONFIRMED which index a real Sibionics GS1 sensor expects — Juggluco's
// own source marks one of these six entries "// Guess", and none of the
// six package-name comments explicitly says "GS1". This is flagged, not
// guessed past: default to index 5 (closest name match, "gstoc" ~ the
// Sibionics-branded rather than OEM-rebrand app) but treat this as the
// first thing to try, not a confirmed value, when real hardware exists.
#define GS1_KEY_TABLE_SIZE 6
extern const char *const gs1_key_table[GS1_KEY_TABLE_SIZE];
#define GS1_DEFAULT_KEY_INDEX 5

// Builds the 26-byte authentication packet (already RC4-encrypted, ready to
// write to the 0xff32 characteristic). `device_addr_reversed` must be the
// 6-byte BLE MAC address in Juggluco's reversed byte order (deviceArray():
// last octet of "AA:BB:CC:DD:EE:FF" first). `key_index` selects which of
// gs1_key_table's 6 fixed strings to embed — see GS1_DEFAULT_KEY_INDEX note.
// `out` must be >= 26 bytes. Returns true on success.
bool gs1_build_auth_packet(const uint8_t device_addr_reversed[6], int key_index,
                            uint8_t *out, size_t out_cap);

// Builds the 7-byte time-sync packet (RC4-encrypted). `out` must be >= 7 bytes.
bool gs1_build_time_packet(uint32_t unix_time, uint8_t *out, size_t out_cap);

// Builds the 11-byte activation packet (RC4-encrypted). `out` must be >= 11 bytes.
bool gs1_build_activation_packet(uint32_t unix_time, uint8_t *out, size_t out_cap);

// Builds the 7-byte "ask values starting at index" packet (RC4-encrypted).
// `out` must be >= 7 bytes.
bool gs1_build_ask_values_packet(uint16_t index, uint8_t *out, size_t out_cap);

// The 4-byte reset command. NOT RC4-encrypted — sent as-is (Juggluco's
// getSIResetBytes() returns this fixed constant unencrypted).
extern const uint8_t gs1_reset_bytes[4];

// One decoded glucose record.
typedef struct {
    uint16_t index;
    uint32_t itime;         // unix time this specific record was taken
    double glucose_mg_dl;   // raw `current` field / 10.0, per Juggluco's own
                             // debug log format string (current/10.0)
} gs1_glucose_record_t;

// Decrypts and parses one notification payload from the 0xff31
// characteristic. `raw` is the as-received (still RC4-encrypted) bytes.
// On a glucose-data response (cmd_id 0x08, length > 4), fills `records`
// (caller-provided array of `max_records`) and returns the count (0 if the
// response was a valid but empty glucose-data ACK). On any other
// recognized response, returns 0 and sets *out_dispatch_code to Juggluco's
// SIprocessData-equivalent code (see gs1_dispatch_code_t) so the caller's
// state machine knows what to send next. Returns -1 on a malformed/
// checksum-invalid packet.
typedef enum {
    GS1_DISPATCH_NONE = 0,       // no action needed / plain ACK
    GS1_DISPATCH_RETRY_AUTH = 4, // re-send the auth packet
    GS1_DISPATCH_SEND_TIME = 5,  // send the time-sync packet
    GS1_DISPATCH_ACTIVATE = 6,   // send the activation packet
    GS1_DISPATCH_ASK_VALUES = 7, // send the ask-values packet
    GS1_DISPATCH_FATAL = 3,      // disconnect, something's wrong
} gs1_dispatch_code_t;

int gs1_parse_notification(const uint8_t *raw, size_t raw_len,
                            gs1_glucose_record_t *records, int max_records,
                            gs1_dispatch_code_t *out_dispatch_code);

#ifdef __cplusplus
}
#endif
