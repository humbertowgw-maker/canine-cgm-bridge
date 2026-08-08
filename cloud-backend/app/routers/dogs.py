from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import calibration_engine, crud, schemas
from app.config import PRESETS
from app.database import get_db

router = APIRouter(prefix="/dogs", tags=["dogs"])


@router.post("", response_model=schemas.DogOut, status_code=201)
def create_dog(dog_in: schemas.DogCreate, db: Session = Depends(get_db)):
    dog = crud.create_dog(db, dog_in, PRESETS)
    calibration_engine.bootstrap_calibration(db, dog.id)
    return dog


@router.get("/{dog_id}", response_model=schemas.DogOut)
def get_dog(dog_id: int, db: Session = Depends(get_db)):
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    return dog


@router.put("/{dog_id}", response_model=schemas.DogOut)
def update_dog(dog_id: int, dog_update: schemas.DogUpdate, db: Session = Depends(get_db)):
    dog = crud.update_dog(db, dog_id, dog_update)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    return dog
