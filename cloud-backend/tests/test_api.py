import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app


@pytest.fixture()
def client(db_engine):
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_dog_uses_preset_defaults_when_omitted(client):
    resp = client.post(
        "/dogs",
        json={"name": "Biscuit", "breed": "Beagle", "weight_kg": 12.5, "feeding_schedule": None},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Biscuit"
    assert body["target_range_low_mg_dl"] == 80.0
    assert body["target_range_high_mg_dl"] == 180.0
    assert body["feeding_schedule"] == ["07:00", "17:00"]

    coeff_resp = client.get(f"/dogs/{body['id']}/calibration/current")
    assert coeff_resp.status_code == 200
    coeff = coeff_resp.json()
    assert coeff["is_active"] is True
    assert coeff["is_trusted"] is False
    assert coeff["point_count"] == 0
    assert coeff["slope"] == 1.0
    assert coeff["intercept"] == 0.0


def test_get_dog_404_for_missing_dog(client):
    resp = client.get("/dogs/9999")
    assert resp.status_code == 404


def test_readings_404_for_missing_dog(client):
    resp = client.get("/readings/9999")
    assert resp.status_code == 404


def test_full_flow_calibration_reading_and_alert(client):
    # 1. Create a dog
    dog_resp = client.post(
        "/dogs",
        json={
            "name": "Rex",
            "breed": "Labrador",
            "weight_kg": 30.0,
            "feeding_schedule": ["07:00", "17:00"],
        },
    )
    assert dog_resp.status_code == 201
    dog_id = dog_resp.json()["id"]

    # 2. Submit enough calibration events to trust the fit (true slope=9.5, intercept=15.0)
    true_slope, true_intercept = 9.5, 15.0
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    reference_values = [120.0, 160.0, 200.0, 240.0, 280.0]
    for i, ref_bg in enumerate(reference_values):
        raw = (ref_bg - true_intercept) / true_slope
        cal_resp = client.post(
            f"/dogs/{dog_id}/calibration",
            json={
                "reference_bg_mg_dl": ref_bg,
                "raw_value": raw,
                "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
            },
        )
        assert cal_resp.status_code == 201

    current = client.get(f"/dogs/{dog_id}/calibration/current").json()
    assert current["is_trusted"] is True
    assert abs(current["slope"] - true_slope) < 0.5
    assert abs(current["intercept"] - true_intercept) < 5.0

    history = client.get(f"/dogs/{dog_id}/calibration/history").json()
    assert len(history) >= 2  # bootstrap row + at least one recalculated row

    # 3. Post a reading using the now-trusted calibration; estimate should be sane
    reading_time = base_time + timedelta(hours=1)
    raw_at_220 = (220.0 - true_intercept) / true_slope
    reading_resp = client.post(
        "/readings",
        json={
            "dog_id": dog_id,
            "timestamp": reading_time.isoformat(),
            "raw_value": raw_at_220,
            "temperature_f": 101.5,
            "source": "simulator",
        },
    )
    assert reading_resp.status_code == 201
    body = reading_resp.json()
    assert abs(body["reading"]["estimated_glucose_mg_dl"] - 220.0) < 10.0
    assert body["alert"] is None  # first reading, no prior point to diff against

    # 4. Post a second reading 10 minutes later showing a steep drop -> alert should fire
    raw_at_160 = (160.0 - true_intercept) / true_slope
    drop_resp = client.post(
        "/readings",
        json={
            "dog_id": dog_id,
            "timestamp": (reading_time + timedelta(minutes=10)).isoformat(),
            "raw_value": raw_at_160,
            "temperature_f": 101.5,
            "source": "simulator",
        },
    )
    assert drop_resp.status_code == 201
    drop_body = drop_resp.json()
    assert drop_body["alert"] is not None
    assert drop_body["alert"]["is_hypo_drop_flag"] is True
    assert drop_body["alert"]["velocity_mg_dl_per_min"] < 0

    # 5. Readings list should have both readings
    readings_list = client.get(f"/readings/{dog_id}").json()
    assert len(readings_list) == 2

    # 6. Alerts list should have the one alert
    alerts_list = client.get(f"/dogs/{dog_id}/alerts").json()
    assert len(alerts_list) == 1

    # 7. Velocity/latest should reflect the same drop
    velocity_resp = client.get(f"/dogs/{dog_id}/velocity/latest").json()
    assert velocity_resp["velocity_mg_dl_per_min"] < 0
