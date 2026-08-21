"""Seeds a demo dog with a synthetic 24h glucose history so a fresh public
deployment (e.g. the Railway demo instance) has something to look at instead
of an empty chart. Mirrors the curve shape simulator/simulate_dog_sensor.py
generates (meal spikes, an insulin trough, one deliberate rapid hypo-drop so
the alert marker is visible), but writes readings directly via crud instead
of going through mobile-bridge/calibration, since the demo only needs a final
mg/dL value per point, not a simulated raw sensor.

Only runs when DEMO_SEED=true and no dogs exist yet -- never touches a real
deployment with real data in it.
"""

import math
import os
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import calibration_engine, canine_analytics, crud, schemas
from app.config import PRESETS

DEMO_SEED = os.environ.get("DEMO_SEED", "").lower() == "true"

DURATION_HOURS = 24
INTERVAL_MINUTES = 5
BASELINE_MG_DL = 220.0
FEEDING_TIMES_MIN = [7 * 60, 17 * 60]
MEAL_SPIKE_AMPLITUDE = 110.0
MEAL_SPIKE_SIGMA_MIN = 45.0
INSULIN_TROUGH_DELAY_MIN = 240.0
INSULIN_TROUGH_AMPLITUDE = 130.0
INSULIN_TROUGH_SIGMA_MIN = 90.0
NOISE_SIGMA = 5.0
CLIP_RANGE = (40.0, 450.0)

# A deliberate rapid drop near the end of the window so the dashboard's
# hypo-drop alert marker has something to show in the demo, not just a
# quiet curve.
HYPO_DROP_START_MIN = DURATION_HOURS * 60 - 40
HYPO_DROP_MG_PER_MIN = -4.0


def _true_glucose(t_min: float) -> float:
    value = BASELINE_MG_DL
    for feed_min in FEEDING_TIMES_MIN:
        offset = t_min - feed_min
        value += MEAL_SPIKE_AMPLITUDE * math.exp(-(offset**2) / (2 * MEAL_SPIKE_SIGMA_MIN**2))
        trough_offset = offset - INSULIN_TROUGH_DELAY_MIN
        value -= INSULIN_TROUGH_AMPLITUDE * math.exp(
            -(trough_offset**2) / (2 * INSULIN_TROUGH_SIGMA_MIN**2)
        )
    if t_min >= HYPO_DROP_START_MIN:
        value += HYPO_DROP_MG_PER_MIN * (t_min - HYPO_DROP_START_MIN)
    value += random.gauss(0, NOISE_SIGMA)
    return max(CLIP_RANGE[0], min(CLIP_RANGE[1], value))


def seed_demo_data(db: Session) -> None:
    if not DEMO_SEED or crud.list_dogs(db):
        return

    dog_in = schemas.DogCreate(
        name="Bella",
        breed="Beagle",
        weight_kg=12.5,
        feeding_schedule=["07:00", "17:00"],
    )
    dog = crud.create_dog(db, dog_in, PRESETS)
    calibration_engine.bootstrap_calibration(db, dog.id)

    num_points = int(DURATION_HOURS * 60 / INTERVAL_MINUTES)
    start = datetime.now(timezone.utc) - timedelta(hours=DURATION_HOURS)

    for i in range(num_points):
        t_min = i * INTERVAL_MINUTES
        timestamp = start + timedelta(minutes=t_min)
        glucose = _true_glucose(t_min)

        reading = crud.create_reading(
            db,
            dog_id=dog.id,
            timestamp=timestamp,
            estimated_glucose_mg_dl=glucose,
            source="demo_synthetic",
        )
        velocity = canine_analytics.get_window_velocity(db, dog.id, reading)
        canine_analytics.check_hypo_drop(db, dog.id, reading, velocity=velocity)
