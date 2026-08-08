import logging

from sqlalchemy.orm import Session

from app import crud, models
from app.config import PRESETS

logger = logging.getLogger(__name__)

_CFG = PRESETS["analytics"]
VELOCITY_WINDOW_MINUTES: int = _CFG["velocity_window_minutes"]
HYPO_DROP_WARNING_MG_DL_PER_MIN: float = _CFG["hypo_drop_warning_mg_dl_per_min"]
HYPO_DROP_CRITICAL_MG_DL_PER_MIN: float = _CFG["hypo_drop_critical_mg_dl_per_min"]


def compute_velocity(readings: list[models.GlucoseReading]) -> float | None:
    """readings must be chronologically ordered (oldest first). Returns the rate of
    change in mg/dL per minute between the oldest and newest reading in the list,
    or None if there are fewer than 2 readings or they share the same timestamp
    (nothing to diff against)."""
    if len(readings) < 2:
        return None

    oldest, newest = readings[0], readings[-1]
    elapsed_minutes = (newest.timestamp - oldest.timestamp).total_seconds() / 60.0
    if elapsed_minutes <= 0:
        return None

    return (newest.estimated_glucose_mg_dl - oldest.estimated_glucose_mg_dl) / elapsed_minutes


def dispatch_alert(alert: models.VelocityAlert) -> None:
    """Stub alert-delivery hook. Currently just logs; a future iteration could push
    a notification or call a webhook here."""
    log_fn = logger.critical if alert.severity == "critical" else logger.warning
    log_fn(
        "Hypoglycemia risk for dog_id=%s: velocity=%.2f mg/dL/min (severity=%s)",
        alert.dog_id,
        alert.velocity_mg_dl_per_min,
        alert.severity,
    )


def get_window_velocity(
    db: Session, dog_id: int, current_reading: models.GlucoseReading
) -> float | None:
    """Velocity (mg/dL/min) over the configured lookback window ending at the
    current reading's (simulated) timestamp. None if there isn't enough history."""
    window_readings = crud.get_recent_readings_for_velocity(
        db, dog_id, window_minutes=VELOCITY_WINDOW_MINUTES, before=current_reading.timestamp
    )
    return compute_velocity(window_readings)


def check_hypo_drop(
    db: Session,
    dog_id: int,
    current_reading: models.GlucoseReading,
    velocity: float | None = None,
) -> models.VelocityAlert | None:
    """Called after a new GlucoseReading is written. Uses `velocity` if the caller
    already computed it (via get_window_velocity, to avoid a duplicate query),
    otherwise computes it. Returns None (no-op) if there isn't enough history, or if
    the drop doesn't cross the warning threshold. Otherwise persists a VelocityAlert
    and dispatches it."""
    if velocity is None:
        velocity = get_window_velocity(db, dog_id, current_reading)
    if velocity is None:
        return None

    if velocity > HYPO_DROP_WARNING_MG_DL_PER_MIN:
        return None  # not dropping fast enough to warrant an alert

    severity = "critical" if velocity <= HYPO_DROP_CRITICAL_MG_DL_PER_MIN else "warning"

    alert = crud.create_velocity_alert(
        db,
        dog_id=dog_id,
        glucose_reading_id=current_reading.id,
        timestamp=current_reading.timestamp,
        velocity_mg_dl_per_min=velocity,
        is_hypo_drop_flag=True,
        severity=severity,
    )
    dispatch_alert(alert)
    return alert
