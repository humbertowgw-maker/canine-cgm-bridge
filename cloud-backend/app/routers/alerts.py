from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import canine_analytics, crud, schemas
from app.database import get_db

router = APIRouter(prefix="/dogs/{dog_id}", tags=["alerts"])


@router.get("/alerts", response_model=list[schemas.VelocityAlertOut])
def list_alerts(
    dog_id: int,
    since: datetime | None = None,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
):
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    return crud.get_alerts(db, dog_id, since=since, limit=limit)


@router.get("/velocity/latest", response_model=schemas.VelocityOut)
def get_latest_velocity(dog_id: int, db: Session = Depends(get_db)):
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")

    latest_readings = crud.get_readings(db, dog_id, limit=1)
    if not latest_readings:
        return schemas.VelocityOut(
            dog_id=dog_id, velocity_mg_dl_per_min=None, as_of=None, message="No readings yet"
        )

    latest = latest_readings[0]
    velocity = canine_analytics.get_window_velocity(db, dog_id, latest)
    message = None if velocity is not None else "Not enough history in the lookback window"
    return schemas.VelocityOut(
        dog_id=dog_id, velocity_mg_dl_per_min=velocity, as_of=latest.timestamp, message=message
    )
