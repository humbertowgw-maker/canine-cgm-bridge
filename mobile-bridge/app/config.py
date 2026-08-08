import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configuration.loader import load_presets  # noqa: E402

SERVICE_DIR = Path(__file__).resolve().parents[1]

CLOUD_BACKEND_URL = os.environ.get("CLOUD_BACKEND_URL", "http://localhost:8000")
PET_PROFILE_STORE_PATH = Path(
    os.environ.get("PET_PROFILE_STORE_PATH", str(SERVICE_DIR / "pet_profiles.json"))
)

PRESETS = load_presets()
