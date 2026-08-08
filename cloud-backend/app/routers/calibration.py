from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import calibration_engine, crud, schemas
from app.database import get_db

router = APIRouter(prefix="/dogs/{dog_id}/calibration", tags=["calibration"])


@router.post("", response_model=schemas.CalibrationCoefficientOut, status_code=201)
def submit_calibration_event(
    dog_id: int, event_in: schemas.CalibrationEventCreate, db: Session = Depends(get_db)
):
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")

    crud.create_calibration_event(
        db,
        dog_id=dog_id,
        reference_bg_mg_dl=event_in.reference_bg_mg_dl,
        raw_value=event_in.raw_value,
        timestamp=event_in.timestamp,
    )

    return calibration_engine.recalculate_calibration(db, dog_id)


@router.get("/current", response_model=schemas.CalibrationCoefficientOut)
def get_current_calibration(dog_id: int, db: Session = Depends(get_db)):
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")

    coefficient = crud.get_active_calibration(db, dog_id)
    if coefficient is None:
        raise HTTPException(status_code=404, detail="No active calibration for this dog")
    return coefficient


@router.get("/history", response_model=list[schemas.CalibrationCoefficientOut])
def get_calibration_history(dog_id: int, db: Session = Depends(get_db)):
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    return crud.get_calibration_history(db, dog_id)
