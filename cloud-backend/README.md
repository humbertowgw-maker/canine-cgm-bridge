# cloud-backend

FastAPI + SQLite service that is the source of truth for dogs, glucose readings,
canine calibration coefficients, and hypoglycemia-velocity alerts. Must always be
launched with this directory as the working directory (`uvicorn app.main:app`) —
`cloud-backend` is not a valid Python package name because of the hyphen.

Run: `uvicorn app.main:app --reload --port 8000`

Simulator: `python simulator/simulate_dog_sensor.py --help`
