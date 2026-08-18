from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/dogs/{dog_id}", tags=["feedings"])


@router.post("/feedings", response_model=schemas.FeedingEventOut, status_code=201)
def create_feeding(dog_id: int, feeding_in: schemas.FeedingEventCreate, db: Session = Depends(get_db)):
    if feeding_in.dog_id != dog_id:
        raise HTTPException(status_code=400, detail="dog_id in body must match dog_id in path")
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    return crud.create_feeding_event(db, dog_id=dog_id, timestamp=feeding_in.timestamp, note=feeding_in.note)


@router.get("/feedings", response_model=list[schemas.FeedingEventOut])
def list_feedings(
    dog_id: int,
    since: datetime | None = None,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
):
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    return crud.get_feeding_events(db, dog_id, since=since, limit=limit)
