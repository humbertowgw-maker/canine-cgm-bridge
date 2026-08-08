import logging
from datetime import datetime, timedelta, timezone

from app import canine_analytics, crud, models


def _make_dog_with_calibration(db_session) -> tuple[models.Dog, models.CalibrationCoefficient]:
    dog = models.Dog(
        name="Rex",
        breed="Labrador",
        weight_kg=30.0,
        target_range_low_mg_dl=80.0,
        target_range_high_mg_dl=180.0,
        feeding_schedule=["07:00", "17:00"],
    )
    db_session.add(dog)
    db_session.commit()
    db_session.refresh(dog)

    coeff = crud.create_calibration_coefficient(
        db_session,
        dog_id=dog.id,
        slope=1.0,
        intercept=0.0,
        r_squared=0.0,
        point_count=0,
        is_active=True,
        is_trusted=False,
    )
    return dog, coeff


def _add_reading(
    db_session, dog, coeff, timestamp: datetime, estimated_glucose_mg_dl: float
) -> models.GlucoseReading:
    return crud.create_reading(
        db_session,
        dog_id=dog.id,
        timestamp=timestamp,
        raw_value=estimated_glucose_mg_dl,  # irrelevant for these tests
        temperature_f=101.5,
        estimated_glucose_mg_dl=estimated_glucose_mg_dl,
        mobile_estimated_glucose_mg_dl=None,
        calibration_coefficient_id=coeff.id,
        source="simulator",
    )


def test_compute_velocity_returns_none_with_fewer_than_two_readings(db_session):
    dog, coeff = _make_dog_with_calibration(db_session)
    base = datetime.now(timezone.utc)
    reading = _add_reading(db_session, dog, coeff, base, 200.0)
    assert canine_analytics.compute_velocity([reading]) is None
    assert canine_analytics.compute_velocity([]) is None


def test_compute_velocity_computes_rate_of_change(db_session):
    dog, coeff = _make_dog_with_calibration(db_session)
    base = datetime.now(timezone.utc)
    r1 = _add_reading(db_session, dog, coeff, base, 200.0)
    r2 = _add_reading(db_session, dog, coeff, base + timedelta(minutes=10), 180.0)

    velocity = canine_analytics.compute_velocity([r1, r2])
    assert velocity == -2.0  # (180 - 200) / 10 minutes


def test_check_hypo_drop_no_alert_with_only_one_reading(db_session):
    dog, coeff = _make_dog_with_calibration(db_session)
    base = datetime.now(timezone.utc)
    reading = _add_reading(db_session, dog, coeff, base, 200.0)

    alert = canine_analytics.check_hypo_drop(db_session, dog.id, reading)
    assert alert is None
    assert crud.get_alerts(db_session, dog.id) == []


def test_check_hypo_drop_no_alert_when_stable(db_session):
    dog, coeff = _make_dog_with_calibration(db_session)
    base = datetime.now(timezone.utc)
    _add_reading(db_session, dog, coeff, base, 200.0)
    r2 = _add_reading(db_session, dog, coeff, base + timedelta(minutes=10), 198.0)

    alert = canine_analytics.check_hypo_drop(db_session, dog.id, r2)
    assert alert is None
    assert crud.get_alerts(db_session, dog.id) == []


def test_check_hypo_drop_fires_warning_on_steep_drop(db_session, caplog):
    dog, coeff = _make_dog_with_calibration(db_session)
    base = datetime.now(timezone.utc)
    _add_reading(db_session, dog, coeff, base, 200.0)
    # -3 mg/dL/min over 10 minutes: below warning (-2.0) but above critical (-4.0)
    r2 = _add_reading(db_session, dog, coeff, base + timedelta(minutes=10), 170.0)

    with caplog.at_level(logging.WARNING):
        alert = canine_analytics.check_hypo_drop(db_session, dog.id, r2)

    assert alert is not None
    assert alert.severity == "warning"
    assert alert.is_hypo_drop_flag is True
    assert alert.velocity_mg_dl_per_min == -3.0
    assert any("Hypoglycemia risk" in msg for msg in caplog.messages)

    stored = crud.get_alerts(db_session, dog.id)
    assert len(stored) == 1
    assert stored[0].id == alert.id


def test_check_hypo_drop_fires_critical_on_very_steep_drop(db_session, caplog):
    dog, coeff = _make_dog_with_calibration(db_session)
    base = datetime.now(timezone.utc)
    _add_reading(db_session, dog, coeff, base, 220.0)
    # -6 mg/dL/min over 10 minutes: at/below critical (-4.0)
    r2 = _add_reading(db_session, dog, coeff, base + timedelta(minutes=10), 160.0)

    with caplog.at_level(logging.WARNING):
        alert = canine_analytics.check_hypo_drop(db_session, dog.id, r2)

    assert alert is not None
    assert alert.severity == "critical"
    assert alert.velocity_mg_dl_per_min == -6.0
