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

PRESETS = load_presets()
