from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.dose_guidance import compute_dose_guidance

router = APIRouter(prefix="/dogs/{dog_id}", tags=["dose-guidance"])

VALID_FREQUENCIES = {"once_daily", "twice_daily"}

# Signals with no actionable content — nothing to gate behind a comprehension
# check, since there's no formula-derived guidance being shown yet.
UNGATED_SIGNALS = {"no_baseline_dose", "insufficient_data"}


@router.post(
    "/prescribed-dose", response_model=schemas.PrescribedDoseOut, status_code=201
)
def set_prescribed_dose(
    dog_id: int, dose_in: schemas.PrescribedDoseCreate, db: Session = Depends(get_db)
):
    """Records the vet's ACTUAL current prescription for this dog. This is an
    owner-entered fact, never something this app computes — it's the required
    baseline for /dose-guidance below."""
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    if dose_in.frequency not in VALID_FREQUENCIES:
        raise HTTPException(
            status_code=422, detail=f"frequency must be one of {sorted(VALID_FREQUENCIES)}"
        )

    return crud.create_prescribed_dose(
        db,
        dog_id=dog_id,
        dose_iu=dose_in.dose_iu,
        frequency=dose_in.frequency,
        insulin_type=dose_in.insulin_type,
        prescribing_note=dose_in.prescribing_note,
    )


@router.get("/prescribed-dose/current", response_model=schemas.PrescribedDoseOut)
def get_current_prescribed_dose(dog_id: int, db: Session = Depends(get_db)):
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    dose = crud.get_active_prescribed_dose(db, dog_id)
    if dose is None:
        raise HTTPException(status_code=404, detail="No prescribed dose on file for this dog")
    return dose


@router.get("/prescribed-dose/history", response_model=list[schemas.PrescribedDoseOut])
def get_prescribed_dose_history(dog_id: int, db: Session = Depends(get_db)):
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    return crud.get_prescribed_dose_history(db, dog_id)


@router.get("/dose-guidance", response_model=schemas.DoseGuidanceOut)
def get_dose_guidance(
    dog_id: int, window_hours: int = Query(default=12, ge=1, le=48), db: Session = Depends(get_db)
):
    """Formula-reference guidance — see app/dose_guidance.py's module docstring
    for why this deliberately never returns a suggested dose number."""
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")

    guidance = compute_dose_guidance(db, dog_id, window_hours=window_hours)

    if guidance.signal in UNGATED_SIGNALS:
        requires_fresh_ack = False
    else:
        latest_ack = crud.get_latest_dose_guidance_ack(db, dog_id)
        requires_fresh_ack = latest_ack is None or latest_ack.signal != guidance.signal

    return schemas.DoseGuidanceOut(
        dog_id=guidance.dog_id,
        signal=guidance.signal,
        message=guidance.message,
        current_dose_iu=guidance.current_dose_iu,
        current_frequency=guidance.current_frequency,
        window_hours=guidance.window_hours,
        nadir_mg_dl=guidance.nadir_mg_dl,
        nadir_timestamp=guidance.nadir_timestamp,
        formula_citation=guidance.formula_citation,
        somogyi_caveat=guidance.somogyi_caveat,
        requires_fresh_acknowledgment=requires_fresh_ack,
    )


@router.post(
    "/dose-guidance-ack", response_model=schemas.DoseGuidanceAckOut, status_code=201
)
def acknowledge_dose_guidance(
    dog_id: int, ack_in: schemas.DoseGuidanceAckCreate, db: Session = Depends(get_db)
):
    """Records that a human actively passed the comprehension check for a
    specific signal — an audit trail, not just a UI checkbox state. Re-running
    /dose-guidance afterward will report requires_fresh_acknowledgment=False
    for this exact signal until it changes to something else."""
    dog = crud.get_dog(db, dog_id)
    if dog is None:
        raise HTTPException(status_code=404, detail="Dog not found")
    return crud.create_dose_guidance_ack(db, dog_id=dog_id, signal=ack_in.signal)
