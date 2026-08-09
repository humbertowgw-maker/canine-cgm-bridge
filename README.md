# Canine CGM Bridge

A canine-specific Continuous Glucose Monitor systems-integration bridge, architecturally
modeled on open-source human CGM tooling (xDrip+'s mobile ingestion/parsing role,
Nightscout's cloud REST API role) but implemented from scratch in Python. The software
(this README's Quick Start) runs entirely on simulated data at $0 cost. A physical
prototype is in progress in `hardware-bridge/` — see that directory's own README — reusing
an already-FDA-approved, OTC human CGM sensor (Dexcom Stelo, built on the same G7 sensor
platform used off-label on dogs by vets) rather than engineering any new biosensor
hardware. Stelo broadcasts BLE natively, so no separate NFC/BLE bridge hardware is needed
either.

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

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r cloud-backend/requirements.txt -r mobile-bridge/requirements.txt

# Terminal 1
cd cloud-backend && uvicorn app.main:app --reload --port 8000

# Terminal 2
cd mobile-bridge && CLOUD_BACKEND_URL=http://localhost:8000 uvicorn app.main:app --reload --port 9000

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
thresholds, no human UI screens, no auth/multi-tenancy, no cloud deployment/TLS, and no
actual Kotlin/Android or Node/Mongo code. Pure Python for the software side, architecturally
inspired only. Real alert delivery is a browser-notification stub, not push/webhook/SMS.

## Running tests

```bash
cd cloud-backend && pytest
cd ../mobile-bridge && pytest
```
