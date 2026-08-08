import random
from datetime import datetime, timedelta, timezone

from app import calibration_engine, crud, models


def _make_dog(db_session) -> models.Dog:
    dog = models.Dog(
        name="Biscuit",
        breed="Beagle",
        weight_kg=12.5,
        target_range_low_mg_dl=80.0,
        target_range_high_mg_dl=180.0,
        feeding_schedule=["07:00", "17:00"],
    )
    db_session.add(dog)
    db_session.commit()
    db_session.refresh(dog)
    return dog


def test_get_default_coefficients_matches_presets():
    slope, intercept = calibration_engine.get_default_coefficients()
    assert slope == 1.0
    assert intercept == 0.0


def test_bootstrap_calibration_creates_untrusted_active_row(db_session):
    dog = _make_dog(db_session)
    coeff = calibration_engine.bootstrap_calibration(db_session, dog.id)

    assert coeff.dog_id == dog.id
    assert coeff.is_active is True
    assert coeff.is_trusted is False
    assert coeff.point_count == 0
    assert coeff.slope == 1.0
    assert coeff.intercept == 0.0


def test_compute_regression_degenerate_points_returns_none():
    # All raw values identical -> no line can be fit.
    points = [(10.0, 100.0), (10.0, 110.0), (10.0, 90.0)]
    assert calibration_engine.compute_regression(points) is None


def test_recalculate_calibration_below_min_points_leaves_active_row_unchanged(db_session):
    dog = _make_dog(db_session)
    bootstrap = calibration_engine.bootstrap_calibration(db_session, dog.id)

    crud.create_calibration_event(
        db_session,
        dog_id=dog.id,
        reference_bg_mg_dl=180.0,
        raw_value=17.4,
        timestamp=datetime.now(timezone.utc),
    )

    result = calibration_engine.recalculate_calibration(db_session, dog.id)

    assert result.id == bootstrap.id
    assert result.is_active is True
    assert result.point_count == 0


def test_recalculate_calibration_converges_to_true_slope_and_intercept(db_session):
    dog = _make_dog(db_session)
    bootstrap = calibration_engine.bootstrap_calibration(db_session, dog.id)

    true_slope, true_intercept = 9.5, 15.0
    rng = random.Random(42)
    base_time = datetime.now(timezone.utc)

    reference_values = [120.0, 160.0, 200.0, 240.0, 280.0, 320.0]
    for i, ref_bg in enumerate(reference_values):
        raw = (ref_bg - true_intercept) / true_slope + rng.uniform(-0.05, 0.05)
        crud.create_calibration_event(
            db_session,
            dog_id=dog.id,
            reference_bg_mg_dl=ref_bg,
            raw_value=raw,
            timestamp=base_time + timedelta(minutes=i),
        )
        result = calibration_engine.recalculate_calibration(db_session, dog.id)

    assert result.point_count == len(reference_values)
    assert result.is_trusted is True
    assert result.is_active is True
    assert abs(result.slope - true_slope) < 0.5
    assert abs(result.intercept - true_intercept) < 5.0

    # bootstrap row must have been deactivated once a real fit replaced it
    db_session.refresh(bootstrap)
    assert bootstrap.is_active is False

    active = crud.get_active_calibration(db_session, dog.id)
    assert active.id == result.id
