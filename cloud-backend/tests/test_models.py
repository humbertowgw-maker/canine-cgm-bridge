from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app import models


def test_insert_and_query_with_fk_integrity(db_session):
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

    coeff = models.CalibrationCoefficient(
        dog_id=dog.id,
        slope=1.0,
        intercept=0.0,
        r_squared=0.0,
        point_count=0,
        is_active=True,
        is_trusted=False,
    )
    db_session.add(coeff)
    db_session.commit()
    db_session.refresh(coeff)

    reading = models.GlucoseReading(
        dog_id=dog.id,
        timestamp=datetime.now(timezone.utc),
        raw_value=21.6,
        temperature_f=101.5,
        estimated_glucose_mg_dl=21.6,
        mobile_estimated_glucose_mg_dl=None,
        calibration_coefficient_id=coeff.id,
        source="simulator",
    )
    db_session.add(reading)
    db_session.commit()
    db_session.refresh(reading)

    assert reading.id is not None
    assert reading.dog_id == dog.id
    assert reading.calibration_coefficient_id == coeff.id
    assert reading.dog.name == "Rex"
    assert reading.calibration_coefficient.slope == 1.0
    assert dog.readings[0].id == reading.id
    assert dog.calibration_coefficients[0].id == coeff.id


def test_foreign_key_violation_is_rejected(db_session):
    reading = models.GlucoseReading(
        dog_id=9999,  # no such dog
        timestamp=datetime.now(timezone.utc),
        raw_value=21.6,
        temperature_f=101.5,
        estimated_glucose_mg_dl=21.6,
        calibration_coefficient_id=9999,  # no such coefficient
        source="simulator",
    )
    db_session.add(reading)
    with pytest.raises(IntegrityError):
        db_session.commit()
