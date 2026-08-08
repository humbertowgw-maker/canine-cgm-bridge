from datetime import datetime, timezone

import pytest

from app import calibration
from app.models import CalibrationSubmission


@pytest.fixture(autouse=True)
def _clear_calibration_cache():
    calibration.clear_cache()
    yield
    calibration.clear_cache()


def test_apply_calibration_formula():
    assert calibration.apply_calibration(raw_value=10.0, slope=9.5, intercept=15.0) == 110.0


def test_get_cached_coefficients_returns_bootstrap_default_when_uncached():
    coeffs = calibration.get_cached_coefficients(dog_id=1)
    assert coeffs.slope == 1.0
    assert coeffs.intercept == 0.0
    assert coeffs.is_trusted is False
    assert coeffs.point_count == 0


def test_update_cache_then_get_returns_cached_value():
    from app.models import CalibrationCoefficients

    calibration.update_cache(
        CalibrationCoefficients(
            dog_id=1, slope=9.5, intercept=15.0, is_trusted=True, point_count=6
        )
    )
    coeffs = calibration.get_cached_coefficients(1)
    assert coeffs.slope == 9.5
    assert coeffs.intercept == 15.0
    assert coeffs.is_trusted is True


@pytest.mark.asyncio
async def test_submit_calibration_point_updates_cache_from_cloud_response(monkeypatch):
    async def fake_forward_calibration_event(dog_id, event):
        assert dog_id == 1
        return {"slope": 9.4, "intercept": 14.8, "is_trusted": True, "point_count": 4}

    monkeypatch.setattr(
        "app.forwarder.forward_calibration_event", fake_forward_calibration_event
    )

    submission = CalibrationSubmission(
        dog_id=1,
        reference_bg_mg_dl=200.0,
        raw_value=19.5,
        timestamp=datetime.now(timezone.utc),
    )
    result = await calibration.submit_calibration_point(submission)

    assert result.slope == 9.4
    assert result.intercept == 14.8
    assert result.is_trusted is True
    assert calibration.get_cached_coefficients(1).slope == 9.4


@pytest.mark.asyncio
async def test_submit_calibration_point_leaves_cache_unchanged_when_cloud_unreachable(
    monkeypatch,
):
    async def fake_forward_calibration_event(dog_id, event):
        return None

    monkeypatch.setattr(
        "app.forwarder.forward_calibration_event", fake_forward_calibration_event
    )

    submission = CalibrationSubmission(
        dog_id=2,
        reference_bg_mg_dl=200.0,
        raw_value=19.5,
        timestamp=datetime.now(timezone.utc),
    )
    result = await calibration.submit_calibration_point(submission)

    # Falls back to the (uncached) bootstrap default since cloud was unreachable
    assert result.slope == 1.0
    assert result.intercept == 0.0
