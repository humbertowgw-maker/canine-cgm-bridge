"""Insulin dose guidance — a formula *reference*, not a recommendation.

This module deliberately never outputs a suggested dose number. It reasons
from a vet-entered baseline (PrescribedDose) and the dog's actual recent
glucose nadir, and returns one of a small fixed set of qualitative signals
plus the cited published logic behind that signal — never a computed "give
X IU" figure. Two design decisions matter enough to write down here:

1. The app never originates a dose. Without an active PrescribedDose (a vet's
   actual current prescription, entered by the owner) there is no baseline to
   reason from at all, so guidance is refused outright (signal =
   "no_baseline_dose") rather than inventing a starting point.

2. The threshold logic is DELIBERATELY ASYMMETRIC, because the underlying
   veterinary sources are asymmetric. Multiple independent sources (Merck's
   Vetsulin dosing page, ADW Diabetes) give concrete numeric thresholds for
   when a dose should be *reduced* (nadir < 80 mg/dL = hard signal; < 100 =
   consider). None of the sources researched gave any standard percentage or
   formula for *raising* a dose from elevated readings — raising a dose is
   exactly the move that can trigger Somogyi rebound if the real problem was
   already-too-high insulin, not too little. So "elevated" gets the
   "elevated_no_formula" signal, with no numeric suggestion at all — that
   silence is intentional, not a gap to be filled in with a guessed number.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import crud, models

DEFAULT_WINDOW_HOURS = 12

# Sourced thresholds — see README/dashboard citation for the underlying
# veterinary references (Merck/Vetsulin canine dosing page, ADW Diabetes
# glucose-curve interpretation guide, both independently stating the same
# ~80 / ~100-150 mg/dL bands).
NADIR_HARD_REDUCE_THRESHOLD_MG_DL = 80.0
NADIR_CONSIDER_REDUCE_THRESHOLD_MG_DL = 100.0
NADIR_TARGET_CEILING_MG_DL = 150.0

FORMULA_CITATIONS = {
    "reduce_indicated": (
        "Nadir below 80 mg/dL is a hard signal to reduce the dose, regardless of "
        "the rest of the curve (Merck/Vetsulin dosing guidance; ADW Diabetes "
        "glucose-curve interpretation guide)."
    ),
    "reduce_consider": (
        "Nadir between 80–100 mg/dL: Merck's own Vetsulin dosing guidance "
        'states this "may warrant a decrease in the dose" — softer than the '
        "hard <80 mg/dL threshold, worth flagging to your vet rather than acting on alone."
    ),
    "in_target": (
        "Nadir within the commonly cited 100–150 mg/dL target band — no dose "
        "change indicated by the nadir alone."
    ),
    "elevated_no_formula": (
        "Nadir above 150 mg/dL. Unlike the reduce-dose case, none of the veterinary "
        "sources reviewed for this app give a standard formula or percentage for "
        "raising a dose from an elevated reading — this app will not guess one. "
        "An elevated reading can also mean the dose is already too high and rebounding "
        "(see the Somogyi note below); raising the dose in that case makes it worse. "
        "This needs your vet's actual assessment."
    ),
    "no_baseline_dose": (
        "No current prescribed dose is on file for this dog. This app never "
        "originates a starting dose — enter your vet's actual current "
        "prescription first."
    ),
    "insufficient_data": (
        "Not enough glucose readings in the lookback window to determine a nadir."
    ),
}

SOMOGYI_CAVEAT = (
    "A high reading is not always a signal to raise the dose. Somogyi rebound — "
    "an already-too-high insulin dose driving glucose down too far, triggering a "
    "hormonal rebound that can spike glucose to 400–800 mg/dL — can persist for "
    "up to 3 days after a single hypoglycemic episode. Reacting to a rebound reading "
    "by raising the dose further can make the underlying problem worse, not better."
)


@dataclass
class DoseGuidance:
    dog_id: int
    signal: str
    message: str
    current_dose_iu: float | None
    current_frequency: str | None
    window_hours: int
    nadir_mg_dl: float | None
    nadir_timestamp: datetime | None
    formula_citation: str
    somogyi_caveat: str


def compute_dose_guidance(
    db: Session, dog_id: int, window_hours: int = DEFAULT_WINDOW_HOURS
) -> DoseGuidance:
    prescribed = crud.get_active_prescribed_dose(db, dog_id)
    if prescribed is None:
        return DoseGuidance(
            dog_id=dog_id,
            signal="no_baseline_dose",
            message=FORMULA_CITATIONS["no_baseline_dose"],
            current_dose_iu=None,
            current_frequency=None,
            window_hours=window_hours,
            nadir_mg_dl=None,
            nadir_timestamp=None,
            formula_citation=FORMULA_CITATIONS["no_baseline_dose"],
            somogyi_caveat=SOMOGYI_CAVEAT,
        )

    # Naive UTC, matching how timestamps are stored elsewhere in this codebase
    # (see canine_analytics.get_window_velocity) — deliberately not tz-aware,
    # since mixing aware/naive here would silently break the SQLite `since`
    # comparison rather than raise, and that's a worse failure mode than a
    # deprecation warning.
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=window_hours)
    readings = crud.get_readings(db, dog_id, since=since, limit=1000)

    if not readings:
        return DoseGuidance(
            dog_id=dog_id,
            signal="insufficient_data",
            message=FORMULA_CITATIONS["insufficient_data"],
            current_dose_iu=prescribed.dose_iu,
            current_frequency=prescribed.frequency,
            window_hours=window_hours,
            nadir_mg_dl=None,
            nadir_timestamp=None,
            formula_citation=FORMULA_CITATIONS["insufficient_data"],
            somogyi_caveat=SOMOGYI_CAVEAT,
        )

    nadir_reading = min(readings, key=lambda r: r.estimated_glucose_mg_dl)
    nadir = nadir_reading.estimated_glucose_mg_dl

    if nadir < NADIR_HARD_REDUCE_THRESHOLD_MG_DL:
        signal = "reduce_indicated"
    elif nadir < NADIR_CONSIDER_REDUCE_THRESHOLD_MG_DL:
        signal = "reduce_consider"
    elif nadir <= NADIR_TARGET_CEILING_MG_DL:
        signal = "in_target"
    else:
        signal = "elevated_no_formula"

    return DoseGuidance(
        dog_id=dog_id,
        signal=signal,
        message=FORMULA_CITATIONS[signal],
        current_dose_iu=prescribed.dose_iu,
        current_frequency=prescribed.frequency,
        window_hours=window_hours,
        nadir_mg_dl=nadir,
        nadir_timestamp=nadir_reading.timestamp,
        formula_citation=FORMULA_CITATIONS[signal],
        somogyi_caveat=SOMOGYI_CAVEAT,
    )
