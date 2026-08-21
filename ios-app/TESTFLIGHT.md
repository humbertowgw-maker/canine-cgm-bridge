# TestFlight submission — Aegis iOS

Same process that got PhysicalKey and Screenshot Analyzer submitted (see
`physicalkey-core/mobile/ios/TESTFLIGHT.md` for the fully detailed version). This is the
Aegis-specific quick reference.

**Status as of 2026-08-21**: app builds and runs correctly (verified in the iOS Simulator
against the live public demo backend — real chart, real data, not a mockup). App Store
Connect record has **not** been created yet — that's the one step that needs you.

## What you need to do

1. Go to [appstoreconnect.apple.com](https://appstoreconnect.apple.com), sign in.
2. **My Apps → "+" → New App.**
   - **Platform:** iOS
   - **Name:** Aegis (check uniqueness first — if taken, "Aegis CGM" or similar)
   - **Bundle ID:** `com.humbertowgw.aegis` — if not in the dropdown, register it first at
     **Apple Developer → Certificates, Identifiers & Profiles → Identifiers → "+"**
   - **SKU:** e.g. `aegis-ios-001`
3. Tell me once that's done — I'll run the archive/export/upload from
   `canine-cgm-bridge/ios-app/`:
   ```bash
   xcodebuild -project Aegis.xcodeproj -scheme Aegis -sdk iphoneos \
     -configuration Release -destination "generic/platform=iOS" \
     -archivePath build/Aegis.xcarchive -allowProvisioningUpdates archive
   ```
   then export + upload the same way PhysicalKey's did.
4. Before external testers: needs a **Privacy Policy URL** (requests HealthKit access) — I
   can draft the text, you pick where to host it (e.g. `aegis.whitegwireless.com/privacy`).

## What's in the app

- **Dashboard** — real Swift Charts trend chart, target-range band, latest BG/velocity/
  calibration tiles, pulling live from whatever backend is set in Settings.
- **Log** — manual glucose reading, feeding, calibration-point submission.
- **HealthKit** — Stelo-via-Apple-Health sync (ported from `stelo-healthkit-sync/`).
- **Settings** — backend URL + API key + dog ID, defaults to the public demo.
