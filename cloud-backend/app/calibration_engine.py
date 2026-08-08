from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app import crud, models
from app.config import PRESETS

_CFG = PRESETS["calibration_engine"]
MIN_POINTS_FOR_REGRESSION: int = _CFG["min_points_for_regression"]
MIN_POINTS_FOR_TRUSTED_FIT: int = _CFG["min_points_for_trusted_fit"]
MAX_CALIBRATION_WINDOW: int = _CFG["max_calibration_window"]


@dataclass
class RegressionResult:
    slope: float
    intercept: float
    r_squared: float
    point_count: int


def compute_regression(points: list[tuple[float, float]]) -> RegressionResult | None:
    """points = [(raw_value, reference_bg_mg_dl), ...].

    Least squares fit via numpy.polyfit. Returns None if the points are degenerate
    (e.g. all raw values identical, so no line can be fit) rather than raising.
    """
    raw = np.array([p[0] for p in points], dtype=float)
    ref = np.array([p[1] for p in points], dtype=float)

    if np.allclose(raw, raw[0]):
        return None

    slope, intercept = np.polyfit(raw, ref, 1)
    predicted = slope * raw + intercept
    ss_res = np.sum((ref - predicted) ** 2)
    ss_tot = np.sum((ref - ref.mean()) ** 2)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return RegressionResult(
        slope=float(slope),
        intercept=float(intercept),
        r_squared=float(r_squared),
        point_count=len(points),
    )


def get_default_coefficients() -> tuple[float, float]:
    defaults = PRESETS["calibration_defaults"]
    return defaults["slope"], defaults["intercept"]


def bootstrap_calibration(db: Session, dog_id: int) -> models.CalibrationCoefficient:
    """Create the initial bootstrap CalibrationCoefficient row for a newly created Dog."""
    slope, intercept = get_default_coefficients()
    return crud.create_calibration_coefficient(
        db,
        dog_id=dog_id,
        slope=slope,
        intercept=intercept,
        r_squared=0.0,
        point_count=0,
        is_active=True,
        is_trusted=False,
    )


def recalculate_calibration(db: Session, dog_id: int) -> models.CalibrationCoefficient:
    """Called after every new CalibrationEvent insert for a dog.

    Fetches the most recent MAX_CALIBRATION_WINDOW events, fits a line, deactivates
    the previously-active coefficient row, and inserts a new active row. If fewer
    than MIN_POINTS_FOR_REGRESSION events exist (or the points are degenerate), the
    active row is left unchanged and returned as-is.
    """
    events = crud.get_recent_calibration_events(db, dog_id, limit=MAX_CALIBRATION_WINDOW)

    if len(events) < MIN_POINTS_FOR_REGRESSION:
        return crud.get_active_calibration(db, dog_id)

    result = compute_regression([(e.raw_value, e.reference_bg_mg_dl) for e in events])
    if result is None:
        return crud.get_active_calibration(db, dog_id)

    crud.deactivate_current_calibration(db, dog_id)
    return crud.create_calibration_coefficient(
        db,
        dog_id=dog_id,
        slope=result.slope,
        intercept=result.intercept,
        r_squared=result.r_squared,
        point_count=result.point_count,
        is_active=True,
        is_trusted=result.point_count >= MIN_POINTS_FOR_TRUSTED_FIT,
    )
