# Dexcom BLE protocol — findings from xDrip+ source (2026-08-18)

Researched directly from `NightscoutFoundation/xDrip` (shallow-cloned, HEAD as of
2026-08-18) to ground Step 3 of the hardware-bridge plan in real, citable source
rather than fabricated packet formats. Every claim below is attributed to a
specific file so it can be independently re-checked against a fresh clone.

## Bottom line — the original plan needs revising

**xDrip+ has a complete, working, reverse-engineered raw-BLE protocol for the
Dexcom G5 and G6 only.** For G7 and Stelo, xDrip+ does **not** open its own
authenticated BLE connection to the transmitter. Instead it reads glucose
values out of Android notifications posted by Dexcom's own official app
(`com.dexcom.stelo`, `com.dexcom.g7`), via a `NotificationListenerService`.
That is a fundamentally different integration model than "ESP32 as BLE
central" — it requires Dexcom's own app to already be installed, paired, and
running on a device that can receive its notifications. An ESP32 cannot do
this; it isn't running Android and can't observe another app's notifications.

This directly contradicts this repo's `hardware-bridge/README.md`, which
currently states Stelo "broadcast[s] BLE natively... same class of BLE
central connection" as G6/G7. That statement is not supported by xDrip+'s
source. It should be corrected once you've decided how to proceed (see
"Options" at the bottom).

## 1. BLE service/characteristic UUIDs (G5/G6 — confirmed working)

Source: `app/src/main/java/com/eveningoutpost/dexdrip/g5model/BluetoothServices.java`

| Name | UUID |
|---|---|
| CGMService | `F8083532-849E-531C-C594-30F1F86A4EA5` |
| Communication (characteristic) | `F8083533-849E-531C-C594-30F1F86A4EA5` |
| Control (characteristic) | `F8083534-849E-531C-C594-30F1F86A4EA5` |
| Authentication (characteristic) | `F8083535-849E-531C-C594-30F1F86A4EA5` |
| ProbablyBackfill (characteristic) | `F8083536-849E-531C-C594-30F1F86A4EA5` |
| ExtraData (characteristic) | `F8083538-849E-531C-C594-30F1F86A4EA5` |
| Advertisement service | `0000FEBC-0000-1000-8000-00805F9B34FB` |
| DeviceInfo service (standard) | `0000180A-0000-1000-8000-00805F9B34FB` |
| CCCD (standard) | `00002902-0000-1000-8000-00805F9B34FB` |

These are the UUIDs a G5/G6 transmitter actually exposes. **Not independently
confirmed to be the same UUIDs a Stelo or G7 transmitter exposes** — xDrip+
never connects to those over BLE itself, so its source contains no evidence
either way for those two devices.

## 2. Pairing/auth handshake (G5/G6 — confirmed working)

Source: `g5model/AuthRequestTxMessage.java`, `AuthChallengeRxMessage.java`,
`AuthChallengeTxMessage.java`, `AuthStatusRxMessage.java`,
`Ob1G5StateMachine.java` (functions `calculateChallengeHash`, `getCryptKey`,
lines ~1990-2054).

Sequence, opcodes in parens:
1. Central connects, writes to the **Authentication** characteristic an
   `AuthRequestTxMessage` (opcode `0x01`): a random 16-byte single-use token
   + a 1-byte "slot".
2. Transmitter replies with `AuthChallengeRxMessage` (opcode `0x03`, ≥17
   bytes): bytes 1-9 are `tokenHash`, bytes 9-17 are an 8-byte `challenge`.
3. Central computes `calculateChallengeHash(challenge, key)`:
   - `key` = derived from the 6-character transmitter ID printed on the
     sensor: `"00" + transmitterId + "00" + transmitterId` as UTF-8 bytes
     (`getCryptKey()`, line 2043) — a 16-byte AES key, **not a nonce or
     random secret**. This is the crux of the whole scheme: knowing the
     transmitter ID printed on the device is sufficient to authenticate.
   - Plaintext block = `challenge` (8 bytes) repeated twice = 16 bytes.
   - Cipher: `AES/ECB/PKCS7Padding`, encrypt mode, take first 8 bytes of the
     16-byte output as the response hash.
4. Central writes `AuthChallengeTxMessage` (opcode `0x04`) containing that
   8-byte hash back to the Authentication characteristic.
5. Transmitter replies `AuthStatusRxMessage` (opcode `0x05`, ≥3 bytes):
   byte 1 = `authenticated` (1/0), byte 2 = `bonded` (1/0). If not bonded,
   xDrip+ issues a standard Android BLE bond request next
   (`BondRequestTxMessage.java` exists but is thin — mostly delegates to the
   OS bonding APIs, which an ESP32 would need to reimplement at the GATT/SMP
   level, not just app level).

This full sequence is real, documented (via xDrip+'s own reverse-engineering,
which the code itself calls out — see §5), and reusable for G5/G6.
**Not verified for G7 or Stelo** for the reason in the bottom-line section.

## 3. Glucose reading packet format (G5/G6 — confirmed working)

Source: `g5model/GlucoseRxMessage.java` (opcode `0x31`), little-endian:

| Bytes | Field |
|---|---|
| 0 | opcode (`0x31`) |
| 1 | `status_raw` → battery/status via `TransmitterStatus.getBatteryLevel()` |
| 2-5 | `sequence` (int32) |
| 6-9 | `timestamp` (int32, transmitter's internal clock, seconds) |
| 10-11 | glucose (int16): low 12 bits = `glucose` (mg/dL); bit `0xF000` set = `glucoseIsDisplayOnly` |
| 12 | `state` — parsed via `CalibrationState.parse()` |
| 13 | `trend` (raw; `EGlucoseRxMessage.getTrend()` divides by 10, `127` = invalid/NaN) |
| — | last 2 bytes = CRC (checked via `checkCRC(packet)`, `FastCRC16.java`) |

`glucose` values ≤13 are treated as sentinel/error codes, not real readings
(`if (glucose > 13) {...} else { filtered = unfiltered = glucose; }` — i.e.
error codes pass through as tiny "glucose" values; calling code is expected
to check `state`/`CalibrationState` before trusting the number).

There's also `EGlucoseRxMessage` (opcode `0x4f`, the "extended" glucose
message with a `predicted_glucose` field, marked `// needs mask??? //
remaining bits??` in xDrip+'s own comment — i.e. even the G5/G6-era authors
weren't fully certain of that one field).

## 4. Stelo / G7-specific findings — this is the important part

- `services/UiBasedCollector.java` — `class UiBasedCollector extends
  NotificationListenerService`. Its `coOptedPackages` /
  `coOptedPackagesAll` sets (lines ~83-129) explicitly list
  `"com.dexcom.stelo"`, `"com.dexcom.g7"`, `"com.dexcom.dexcomone"`,
  `"com.dexcom.d1plus"` alongside several *other vendors'* apps (Medtronic
  Guardian, Senseonics Eversense, Microtech Aidex...). This is a generic
  "read glucose numbers out of any of these apps' Android notifications"
  mechanism, not Dexcom-specific and not BLE-specific.
- `utils/DexCollectionType.java` — the enum of collection mechanisms has
  `DexcomG5` and `DexcomG6` as first-class raw-BLE types (in the
  `usesDexcomRaw`/`usesBluetooth` sets), but **no `DexcomG7` or
  `DexcomStelo` entry at all**. The only entry that maps to those devices is
  `UiBased`, which is in the `isPassive` set — meaning xDrip+ doesn't
  actively drive a connection for it, it just listens passively.
- `cgm/dex/g7/EGlucoseRxMessage.java` (opcode `0x4e`) and
  `cgm/dex/g7/BackfillControlRx.java` do exist and parse a G7-flavored
  packet format (similar shape to G5/G6's, plus a `clock`/`age`/`sequence`
  scheme) — but the code that calls them,
  `cgm/dex/ClassifierAction.java`, hardcodes `TXID = "UIUIUI"` as a
  placeholder transmitter ID (line ~31) and is invoked with bytes handed to
  it externally (`ClassifierAction.action(type, data)`), not from xDrip+
  opening its own GATT session. This confirms the G7 packet parser exists,
  but the *transport* feeding it bytes is the passive/UI-based path, not an
  independently-authenticated BLE central connection with a real
  per-transmitter ID and key the way G5/G6 works.

**Net effect: xDrip+'s source contains a real G7 packet-format parser, but
no evidence of a working, independent raw-BLE auth handshake for G7 or
Stelo the way it has for G5/G6.** Whether Stelo *can* be talked to directly
over BLE with a G5/G6-style handshake (same UUIDs, transmitter-ID-derived
AES key) is an open question this source doesn't answer — it may be that
Dexcom changed the crypto for newer transmitters (plausible, since it would
close the exact hole this handshake describes), or it may just be that no
one has publicly reverse-engineered and merged it into xDrip+ yet.

## 5. Caveats xDrip+ itself states

- The G5/G6 protocol is presented throughout as reverse-engineered, not
  Dexcom-documented. `GlucoseRxMessage.java`'s own doc comment: "initial
  packet structure cribbed from Loopkit" (i.e. even xDrip+ sourced this from
  another reverse-engineering project, Loop/LoopKit, not from Dexcom).
- `EGlucoseRxMessage.java` (both the g5model and g7 versions) contain
  explicit uncertainty comments on the `predicted_glucose` field: `// needs
  mask??? // remaining bits??` — the authors flag this field as not fully
  understood even for the format they do actively use.
- `SensorRxMessage.java`'s docstring only credits an author/date, no protocol
  documentation reference — consistent with reverse-engineering, not a spec.

## Options going forward

1. **Stick with Stelo, drop the "direct BLE" assumption.** Realistic path
   given this research: run the *official* Dexcom Stelo Android app on a
   cheap/spare Android phone (not the ESP32), and have that phone forward
   readings to `mobile-bridge` — e.g. via xDrip+'s own `UiBased`
   notification-reading mechanism repurposed, or a small companion Android
   app that mimics it. The ESP32 is no longer the BLE central at all in this
   model; its role would shrink or disappear.
2. **Switch back to a G5/G6 transmitter** (used/expired ones show up cheap
   secondhand since they're often discarded after the 10-day sensor session
   even though the transmitter itself is reusable for months) purely as a
   *protocol testbed* to prove out the ESP32 BLE-central firmware end-to-end
   using the fully-documented handshake above, while separately deciding
   what to do for the real Stelo integration.
3. **Do original reverse-engineering on a real Stelo** once you have one in
   hand — BLE-sniff it (e.g. Android's built-in HCI snoop log while running
   the official app) and see whether it actually does use the same
   UUIDs/handshake as G5/G6 under the hood, just not yet wired up in xDrip+.
   This is real, uncertain work with no guaranteed outcome — flagging it as
   effort/risk, not a promise it'll pan out.

No firmware code was written as part of this research — this is reference
material only, per the explicit scope of this pass.
