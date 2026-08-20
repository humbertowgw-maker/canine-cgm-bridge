import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configuration.loader import load_presets  # noqa: E402

SERVICE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = SERVICE_DIR / "canine_cgm.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE_PATH}")

# Shared secret required on every dogs/readings/calibration/alerts route via
# the X-API-Key header (see app/deps.py). Unset in local dev by default —
# this is a demo project with no real hardware/patient data flowing yet, but
# the API shouldn't be wide open once it is.
CGM_SHARED_SECRET = os.environ.get("CGM_SHARED_SECRET")

# Local vision model (Ollama) for the photo-capture reading extraction feature —
# deliberately local-first, not a paid cloud vision API: no per-call cost, no key
# to manage, and it already runs on this machine's Ollama install.
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")

PRESETS = load_presets()
