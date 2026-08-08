from functools import lru_cache
from pathlib import Path

import yaml

PRESETS_PATH = Path(__file__).resolve().parent / "vet_presets.yaml"

_REQUIRED_KEYS = (
    "calibration_defaults",
    "calibration_engine",
    "target_range",
    "feeding_schedule_default",
    "analytics",
)


@lru_cache(maxsize=1)
def load_presets() -> dict:
    with open(PRESETS_PATH) as f:
        presets = yaml.safe_load(f)

    missing = [key for key in _REQUIRED_KEYS if key not in presets]
    if missing:
        raise ValueError(f"vet_presets.yaml is missing required keys: {missing}")

    return presets
