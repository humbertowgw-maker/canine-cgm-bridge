# Canine CGM Bridge

A canine-specific Continuous Glucose Monitor systems-integration bridge, architecturally
modeled on open-source human CGM tooling (xDrip+'s mobile ingestion/parsing role,
Nightscout's cloud REST API role) but implemented from scratch in Python. The software
(this README's Quick Start) runs entirely on simulated data at $0 cost. A physical
prototype is in progress in `hardware-bridge/` — see that directory's own README — reusing
an already-FDA-approved, OTC human CGM sensor (Dexcom Stelo, built on the same G7 sensor
platform used off-label on dogs by vets) rather than engineering any new biosensor
hardware. **Correction (2026-08-19):** Stelo does *not* broadcast BLE natively the way
G6 does — real protocol research (`hardware-bridge/DEXCOM_BLE_PROTOCOL_RESEARCH.md`)
found no independent BLE central connection exists for it. Real-time monitoring instead
uses an ordinary Bluetooth-SIG-standard glucometer (`hardware-bridge/`'s Tier 2); Stelo
itself is supported only as delayed/historical data via Apple Health
(`stelo-healthkit-sync/`) — see that component's own README for why.

## Components

- `configuration/` — shared veterinary preset parameters (calibration defaults, target
  ranges) loaded by both services.
- `mobile-bridge/` — a FastAPI service standing in for what would eventually be an
  Android ingestion app. Receives telemetry frames, parses them, keeps a local live
  glucose estimate, and forwards readings/calibration submissions to cloud-backend.
- `cloud-backend/` — the FastAPI + SQLite source of truth. Owns dogs, glucose readings,
  the canine calibration regression, and hypoglycemia-velocity analytics. Also contains
  `simulator/simulate_dog_sensor.py`, which generates a synthetic 24h diabetic-dog
  glucose curve and streams it into mobile-bridge.
- `hardware-bridge/` — ESP32/ESP-IDF firmware for the physical prototype. Posts to the
  exact same `mobile-bridge` `/telemetry/frame` endpoint and schema the simulator uses, so
  it's a drop-in real-hardware replacement for the simulator — no software changes needed
  elsewhere. See its own README for current build status.
- `stelo-healthkit-sync/` — a small iOS companion app that reads Stelo's glucose samples
  from Apple HealthKit and forwards them to `cloud-backend`'s `POST /readings/device`,
  tagged `source="stelo_healthkit_delayed"`. Real-time alerting is out of scope for this
  path (Dexcom syncs glucose to HealthKit on a fixed ~3h delay) — see its own README.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r cloud-backend/requirements.txt -r mobile-bridge/requirements.txt

# Every cloud-backend route (except /health and /dashboard) requires this
# header — cloud-backend fails closed if it's unset, so pick any value and
# use the SAME one in both terminals.
export CGM_SHARED_SECRET=local-dev-secret

# Terminal 1
cd cloud-backend && CGM_SHARED_SECRET=$CGM_SHARED_SECRET uvicorn app.main:app --reload --port 8000

# Terminal 2
cd mobile-bridge && CLOUD_BACKEND_URL=http://localhost:8000 CGM_SHARED_SECRET=$CGM_SHARED_SECRET uvicorn app.main:app --reload --port 9000

# Terminal 3 — seed a Pet Profile, then run the simulator (calibration warm-up is automatic)
curl -X POST http://localhost:9000/profile -H "Content-Type: application/json" \
  -d '{"name":"Biscuit","breed":"Beagle","weight_kg":12.5,"feeding_schedule":["07:00","17:00"]}'
cd cloud-backend
python simulator/simulate_dog_sensor.py --dog-id 1 --mobile-bridge-url http://localhost:9000 --speed-factor 60
```

Watch Terminal 1's log for `Dog BG: ... mg/dL (Δ ... mg/dL/min)` lines as readings arrive,
and `WARNING` lines when a rapid hypoglycemic drop is flagged. Or open
**http://localhost:8000/dashboard/** in a browser for a live-updating chart of the trend,
target range, and alert history instead of reading logs.

## Deliberately out of scope

No insulin dosing/bolus calculators, no human carb logging, no human 70/180 mg/dL alert
thresholds, no human UI screens, no cloud deployment/TLS, and no actual Kotlin/Android or
Node/Mongo code. Pure Python for the software side, architecturally inspired only. Real
alert delivery is a browser-notification stub, not push/webhook/SMS.

## Billing (white-label scaffolding, not live)

`cloud-backend/app/routers/user_accounts.py` and `billing.py` add a per-user account +
Stripe subscription layer (`/auth/signup`, `/auth/login`, `/auth/me`, `/billing/checkout`,
`/billing/webhook`, `/billing/status`) — separate from the `CGM_SHARED_SECRET` gate that
still covers every dogs/readings/calibration/alerts route. Not wired into any of that data,
and not live: the Stripe account behind it (Aegis Pro, $14.99/mo) has only ever been used
with test-mode keys. To exercise it locally:

```bash
export JWT_SECRET=local-dev-secret
export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_PRICE_ID_PRO=price_...
export STRIPE_WEBHOOK_SECRET=whsec_...   # only needed to verify real webhook calls
```

## Running tests

```bash
cd cloud-backend && pytest
cd ../mobile-bridge && pytest
```
