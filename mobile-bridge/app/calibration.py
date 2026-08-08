import logging

from app import forwarder
from app.config import PRESETS
from app.models import CalibrationCoefficients, CalibrationSubmission

logger = logging.getLogger(__name__)

_DEFAULTS = PRESETS["calibration_defaults"]

# Local live-estimate cache, keyed by dog_id. cloud-backend is the regression
# source of truth (see app/calibration_engine.py there); this cache only lets
# mobile-bridge keep computing a live estimate if cloud-backend is briefly
# unreachable, mirroring how xDrip+ keeps working offline.
_cache: dict[int, CalibrationCoefficients] = {}


def apply_calibration(raw_value: float, slope: float, intercept: float) -> float:
    return raw_value * slope + intercept


def get_cached_coefficients(dog_id: int) -> CalibrationCoefficients:
    if dog_id in _cache:
        return _cache[dog_id]
    return CalibrationCoefficients(
        dog_id=dog_id,
        slope=_DEFAULTS["slope"],
        intercept=_DEFAULTS["intercept"],
        is_trusted=False,
        point_count=0,
    )


def update_cache(coefficients: CalibrationCoefficients) -> None:
    _cache[coefficients.dog_id] = coefficients


def clear_cache() -> None:
    _cache.clear()


async def refresh_cache_from_cloud(dog_id: int) -> CalibrationCoefficients:
    """Fetch the latest coefficients from cloud-backend and cache them locally.
    Falls back to whatever is already cached (or the bootstrap default) if
    cloud-backend is unreachable."""
    remote = await forwarder.fetch_current_calibration(dog_id)
    if remote is None:
        return get_cached_coefficients(dog_id)

    coefficients = CalibrationCoefficients(
        dog_id=dog_id,
        slope=remote["slope"],
        intercept=remote["intercept"],
        is_trusted=remote["is_trusted"],
        point_count=remote["point_count"],
    )
    update_cache(coefficients)
    return coefficients


async def submit_calibration_point(submission: CalibrationSubmission) -> CalibrationCoefficients:
    """Forwards a reference calibration point to cloud-backend (which owns the
    regression) and updates the local cache with the coefficients it computes."""
    remote = await forwarder.forward_calibration_event(
        submission.dog_id,
        {
            "reference_bg_mg_dl": submission.reference_bg_mg_dl,
            "raw_value": submission.raw_value,
            "timestamp": submission.timestamp.isoformat(),
        },
    )
    if remote is None:
        logger.error(
            "Calibration submission for dog_id=%s could not reach cloud-backend; "
            "local cache left unchanged",
            submission.dog_id,
        )
        return get_cached_coefficients(submission.dog_id)

    coefficients = CalibrationCoefficients(
        dog_id=submission.dog_id,
        slope=remote["slope"],
        intercept=remote["intercept"],
        is_trusted=remote["is_trusted"],
        point_count=remote["point_count"],
    )
    update_cache(coefficients)
    return coefficients
