import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import canine_analytics, crud, schemas
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["readings"])


@router.post("/readings", response_model=schemas.ReadingResponse, status_code=201)
def create_reading(reading_in: schemas.ReadingCreate, db: Session = Depends(get_db)):
    dog = crud.get_dog(db, reading_in.dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")

    coefficient = crud.get_active_calibration(db, reading_in.dog_id)
    if coefficient is None:
        raise HTTPException(
            status_code=409, detail="Dog has no active calibration coefficient"
        )

    estimated_glucose = reading_in.raw_value * coefficient.slope + coefficient.intercept

    reading = crud.create_reading(
        db,
        dog_id=reading_in.dog_id,
        timestamp=reading_in.timestamp,
        raw_value=reading_in.raw_value,
        temperature_f=reading_in.temperature_f,
        estimated_glucose_mg_dl=estimated_glucose,
        mobile_estimated_glucose_mg_dl=reading_in.mobile_estimated_glucose_mg_dl,
        calibration_coefficient_id=coefficient.id,
        source=reading_in.source,
    )

    velocity = canine_analytics.get_window_velocity(db, reading_in.dog_id, reading)
    alert = canine_analytics.check_hypo_drop(db, reading_in.dog_id, reading, velocity=velocity)

    velocity_str = f"{velocity:+.2f}" if velocity is not None else "n/a"
    logger.info(
        "Dog BG: %.1f mg/dL (Δ %s mg/dL/min) [dog_id=%s]",
        reading.estimated_glucose_mg_dl,
        velocity_str,
        reading.dog_id,
    )

    return schemas.ReadingResponse(reading=reading, alert=alert)


@router.get("/readings/{dog_id}", response_model=list[schemas.ReadingOut])
def list_readings(
    dog_id: int,
    since: datetime | None = None,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
):
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    return crud.get_readings(db, dog_id, since=since, limit=limit)
