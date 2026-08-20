# stelo-healthkit-sync

A small SwiftUI iOS companion app that reads Stelo's glucose samples out of Apple
HealthKit and forwards them to `cloud-backend`'s `POST /readings/device`, tagged
`source="stelo_healthkit_delayed"`.

## Why this exists, and what it's *not*

This is Tier 3 of the canine-cgm-bridge tier ladder, and it's deliberately scoped down
from the original plan. The original idea was real-time continuous monitoring off a
Dexcom Stelo sensor. Real research (see `hardware-bridge/DEXCOM_BLE_PROTOCOL_RESEARCH.md`
and Dexcom's own site) ruled that out on two independent fronts:

- **Stelo's BLE protocol isn't independently connectable.** Unlike G6, no app other than
  Dexcom's own has a working BLE central connection to it — confirmed by reading xDrip+'s
  actual open-source implementation, which has this fully solved for G5/G6 but not G7/Stelo.
- **Stelo's own app has no live notification or widget** showing the current glucose
  value — there's nothing to read passively either.

What Stelo *does* do, officially and reliably: sync glucose data to Apple Health (and
Google Health Connect on Android) via a real, sanctioned, documented API. The catch,
stated plainly on Dexcom's own FAQ page and not buried here: **"Stelo sends your glucose
data to health apps with a 3-hour delay."** That's fine for trend/historical logging. It
is **not** fine for the hypoglycemia-drop early-warning alerting that's the actual point
of most of this project — a reading that's 3 hours old can't catch an acute drop before
it's already resolved one way or the other.

So: this app is real-time-alerting-**incapable**, by design, and that's stated here
loudly rather than left for someone to discover the hard way. If you need real-time
alerting, that's Tier 2 (an ordinary Bluetooth glucometer, see `hardware-bridge/`) or a
future Tier 4 (a sensor with a real open BLE protocol — Sibionics GS1 is the current
lead candidate, see the project's other research).

## What it does

1. Requests read-only HealthKit authorization for blood glucose (`HKQuantityType(.bloodGlucose)`).
2. Uses `HKAnchoredObjectQuery` to fetch new samples since the last sync, so re-launching
   or re-running never double-posts a sample.
3. For each new sample, POSTs to cloud-backend with the sample's **real HealthKit
   timestamp** (`sample.startDate`), not the time of sync — the whole point of this tier
   is being honest about how old the data is, so silently stamping it "now" would defeat
   that.
4. The dashboard (`cloud-backend/static/index.html`) marks every reading from this source
   with a visible "DELAYED" badge and a hollow-ring chart marker, and the "Latest BG" stat
   tile skips delayed readings when picking what counts as current — see `isDelayedSource()`
   in that file.

## Setup

```bash
cd stelo-healthkit-sync
xcodegen generate   # regenerate SteloHealthKitSync.xcodeproj after editing project.yml
open SteloHealthKitSync.xcodeproj
```

Signing uses Apple Developer Team `9RYL8ZRC3U` (same team as this portfolio's other apps),
automatic signing style. In the running app, fill in cloud-backend's base URL (use
`127.0.0.1`, not `localhost` — see the networking note below), your `X-API-Key`
(`CGM_SHARED_SECRET`), and the target dog ID, then tap **Request HealthKit Authorization**
once and **Sync Now** whenever you want to pull the latest.

### The `localhost` vs `127.0.0.1` gotcha

The iOS Simulator resolves `"localhost"` to the IPv6 loopback (`::1`) first. `uvicorn`
(cloud-backend's server) only binds IPv4 by default, so a `localhost` URL produces a
silent, confusing "Connection refused" that has nothing to do with app logic. Use
`http://127.0.0.1:PORT` for local dev — this is the app's actual default (`SyncConfig.swift`).

## Verification performed this session

- **`xcodebuild build`** — real, clean build for `iOS Simulator, iPhone 17 Pro Max`. Exit 0.
- **`xcodebuild test`**, `testDeviceReadingPostPreservesOriginalTimestampAndSource` —
  real, unconditional, passing test. Posts a reading with a timestamp 3 hours in the past
  through the app's actual `APIClient`, then queries a locally-running cloud-backend over
  real HTTP and confirms: the value landed, the `source` tag is
  `stelo_healthkit_delayed`, and — critically — the *original* 3-hours-ago timestamp was
  preserved exactly (not overwritten with sync time). Independently re-confirmed via a
  raw `curl` against `GET /readings/1` showing the stored record.
- **`xcodebuild test`**, `testFullHealthKitRoundTrip` — this one **honestly skips**, and
  that's a real, documented limitation, not a gap papered over: `HKHealthStore.requestAuthorization()`
  blocks on a real system consent sheet ("Turn On All" / "Allow") that `xcodebuild test`
  cannot dismiss non-interactively. `xcrun simctl privacy grant health ...` was tried and
  confirmed unsupported on this machine/Xcode version (`Operation not permitted` —
  HealthKit is deliberately excluded from the privacy-grant mechanism that camera/
  location/photos support). The test checks `HKHealthStore.authorizationStatus(for:)`
  first and skips with a clear message rather than hanging or faking a pass. **To actually
  run it**: launch the app once in Simulator.app, tap "Turn On All" on the real permission
  sheet, then re-run the test — the grant persists in the simulator's HealthKit store
  across future non-interactive runs.
- **31/31 cloud-backend pytest suite** still passing after the dashboard changes (no
  backend Python logic changed — the delayed/live distinction is implemented entirely in
  the frontend, since `source` was already present on every reading the API returns; no
  new backend query logic was needed). Extended the existing dashboard-serves-HTML test
  with two new assertions (`isDelayedSource`, `delayed-badge` present in served HTML)
  rather than adding a whole new test, since it's checking an existing test's existing
  contract (what the dashboard serves), not new backend behavior.
- **No real Stelo sensor or real HealthKit-synced Stelo data was available** — every
  verification above uses a synthetic value posted directly through the app's own code
  path, the same honesty standard `hardware-bridge`'s Step 2 (WiFi + fake telemetry,
  proven before any sensor existed) already established for this project.

## What wasn't verified

- The full HealthKit authorization → read → post round trip, for the reason above. It's
  one manual tap away from being verifiable; that tap hasn't been done in this environment.
- Whether Stelo's *actual* HealthKit-written samples look exactly like the synthetic ones
  used here (unit, precision, any Dexcom-specific metadata) — no real Stelo has synced to
  this Apple ID yet.
