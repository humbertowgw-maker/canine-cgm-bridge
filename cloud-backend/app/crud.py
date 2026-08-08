from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas


# ---- Dogs ----


def create_dog(db: Session, dog_in: schemas.DogCreate, presets: dict) -> models.Dog:
    target_range = presets["target_range"]
    feeding_default = presets["feeding_schedule_default"]

    dog = models.Dog(
        name=dog_in.name,
        breed=dog_in.breed,
        weight_kg=dog_in.weight_kg,
        target_range_low_mg_dl=dog_in.target_range_low_mg_dl
        if dog_in.target_range_low_mg_dl is not None
        else target_range["low_mg_dl"],
        target_range_high_mg_dl=dog_in.target_range_high_mg_dl
        if dog_in.target_range_high_mg_dl is not None
        else target_range["high_mg_dl"],
        feeding_schedule=dog_in.feeding_schedule
        if dog_in.feeding_schedule is not None
        else list(feeding_default),
    )
    db.add(dog)
    db.commit()
    db.refresh(dog)
    return dog


def get_dog(db: Session, dog_id: int) -> models.Dog | None:
    return db.get(models.Dog, dog_id)


def update_dog(db: Session, dog_id: int, dog_update: schemas.DogUpdate) -> models.Dog | None:
    dog = get_dog(db, dog_id)
    if dog is None:
        return None
    for field, value in dog_update.model_dump(exclude_unset=True).items():
        setattr(dog, field, value)
    db.commit()
    db.refresh(dog)
    return dog


# ---- Calibration coefficients ----


def get_active_calibration(db: Session, dog_id: int) -> models.CalibrationCoefficient | None:
    stmt = (
        select(models.CalibrationCoefficient)
        .where(
            models.CalibrationCoefficient.dog_id == dog_id,
            models.CalibrationCoefficient.is_active.is_(True),
        )
        .order_by(models.CalibrationCoefficient.computed_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def deactivate_current_calibration(db: Session, dog_id: int) -> None:
    stmt = select(models.CalibrationCoefficient).where(
        models.CalibrationCoefficient.dog_id == dog_id,
        models.CalibrationCoefficient.is_active.is_(True),
    )
    for row in db.execute(stmt).scalars():
        row.is_active = False
    db.commit()


def create_calibration_coefficient(
    db: Session,
    dog_id: int,
    slope: float,
    intercept: float,
    r_squared: float,
    point_count: int,
    is_active: bool,
    is_trusted: bool,
) -> models.CalibrationCoefficient:
    row = models.CalibrationCoefficient(
        dog_id=dog_id,
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        point_count=point_count,
        is_active=is_active,
        is_trusted=is_trusted,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_calibration_history(
    db: Session, dog_id: int, limit: int = 50
) -> list[models.CalibrationCoefficient]:
    stmt = (
        select(models.CalibrationCoefficient)
        .where(models.CalibrationCoefficient.dog_id == dog_id)
        .order_by(models.CalibrationCoefficient.computed_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


# ---- Calibration events ----


def create_calibration_event(
    db: Session, dog_id: int, reference_bg_mg_dl: float, raw_value: float, timestamp: datetime
) -> models.CalibrationEvent:
    event = models.CalibrationEvent(
        dog_id=dog_id,
        reference_bg_mg_dl=reference_bg_mg_dl,
        raw_value=raw_value,
        timestamp=timestamp,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_recent_calibration_events(
    db: Session, dog_id: int, limit: int
) -> list[models.CalibrationEvent]:
    """Most recent `limit` events for the dog, in chronological (oldest-first) order."""
    stmt = (
        select(models.CalibrationEvent)
        .where(models.CalibrationEvent.dog_id == dog_id)
        .order_by(models.CalibrationEvent.timestamp.desc())
        .limit(limit)
    )
    events = list(db.execute(stmt).scalars())
    events.reverse()
    return events


# ---- Glucose readings ----


def create_reading(
    db: Session,
    dog_id: int,
    timestamp: datetime,
    raw_value: float,
    temperature_f: float,
    estimated_glucose_mg_dl: float,
    mobile_estimated_glucose_mg_dl: float | None,
    calibration_coefficient_id: int,
    source: str,
) -> models.GlucoseReading:
    reading = models.GlucoseReading(
        dog_id=dog_id,
        timestamp=timestamp,
        raw_value=raw_value,
        temperature_f=temperature_f,
        estimated_glucose_mg_dl=estimated_glucose_mg_dl,
        mobile_estimated_glucose_mg_dl=mobile_estimated_glucose_mg_dl,
        calibration_coefficient_id=calibration_coefficient_id,
        source=source,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def get_readings(
    db: Session, dog_id: int, since: datetime | None = None, limit: int = 100
) -> list[models.GlucoseReading]:
    stmt = select(models.GlucoseReading).where(models.GlucoseReading.dog_id == dog_id)
    if since is not None:
        stmt = stmt.where(models.GlucoseReading.timestamp >= since)
    stmt = stmt.order_by(models.GlucoseReading.timestamp.desc()).limit(limit)
    return list(db.execute(stmt).scalars())


def get_recent_readings_for_velocity(
    db: Session, dog_id: int, window_minutes: int, before: datetime
) -> list[models.GlucoseReading]:
    """Readings for the dog within `window_minutes` before `before` (inclusive),
    in chronological (oldest-first) order, used for velocity computation."""
    from datetime import timedelta

    since = before - timedelta(minutes=window_minutes)
    stmt = (
        select(models.GlucoseReading)
        .where(
            models.GlucoseReading.dog_id == dog_id,
            models.GlucoseReading.timestamp >= since,
            models.GlucoseReading.timestamp <= before,
        )
        .order_by(models.GlucoseReading.timestamp.asc())
    )
    return list(db.execute(stmt).scalars())


# ---- Velocity alerts ----


def create_velocity_alert(
    db: Session,
    dog_id: int,
    glucose_reading_id: int,
    timestamp: datetime,
    velocity_mg_dl_per_min: float,
    is_hypo_drop_flag: bool,
    severity: str,
) -> models.VelocityAlert:
    alert = models.VelocityAlert(
        dog_id=dog_id,
        glucose_reading_id=glucose_reading_id,
        timestamp=timestamp,
        velocity_mg_dl_per_min=velocity_mg_dl_per_min,
        is_hypo_drop_flag=is_hypo_drop_flag,
        severity=severity,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def get_alerts(
    db: Session, dog_id: int, since: datetime | None = None, limit: int = 100
) -> list[models.VelocityAlert]:
    stmt = select(models.VelocityAlert).where(models.VelocityAlert.dog_id == dog_id)
    if since is not None:
        stmt = stmt.where(models.VelocityAlert.timestamp >= since)
    stmt = stmt.order_by(models.VelocityAlert.timestamp.desc()).limit(limit)
    return list(db.execute(stmt).scalars())


def get_latest_alert(db: Session, dog_id: int) -> models.VelocityAlert | None:
    stmt = (
        select(models.VelocityAlert)
        .where(models.VelocityAlert.dog_id == dog_id)
        .order_by(models.VelocityAlert.timestamp.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()
