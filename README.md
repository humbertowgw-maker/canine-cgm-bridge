# Canine CGM Bridge

A canine-specific Continuous Glucose Monitor systems-integration bridge, architecturally
modeled on open-source human CGM tooling (xDrip+'s mobile ingestion/parsing role,
Nightscout's cloud REST API role) but implemented from scratch in Python. All data in
this project is simulated — there is no physical BLE hardware or sensor involved, and
running it costs $0.

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
thresholds, no human UI screens, no real BLE/hardware drivers, no auth/multi-tenancy, no
real alert delivery (push/webhook — only a logging stub), no cloud deployment/TLS, and no
actual Kotlin/Android or Node/Mongo code. Pure Python, architecturally inspired only.

## Running tests

```bash
cd cloud-backend && pytest
cd ../mobile-bridge && pytest
```
