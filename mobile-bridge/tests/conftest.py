import os
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

CLOUD_BACKEND_DIR = Path(__file__).resolve().parents[2] / "cloud-backend"
TEST_CGM_SHARED_SECRET = "test-secret-for-integration-tests"


@pytest.fixture(autouse=True)
def isolate_pet_profile_store(tmp_path, monkeypatch):
    from app import config, pet_profile

    store_path = tmp_path / "pet_profiles.json"
    monkeypatch.setattr(config, "PET_PROFILE_STORE_PATH", store_path)
    monkeypatch.setattr(pet_profile, "PET_PROFILE_STORE_PATH", store_path)
    yield store_path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def live_cloud_backend(tmp_path, monkeypatch):
    """Spawns a real cloud-backend uvicorn process against a throwaway SQLite
    file, so end-to-end tests exercise the real HTTP boundary rather than
    calling Python functions directly."""
    from app import forwarder

    monkeypatch.setattr(forwarder, "CGM_SHARED_SECRET", TEST_CGM_SHARED_SECRET)
    port = _free_port()
    db_path = tmp_path / "test_cloud.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "CGM_SHARED_SECRET": TEST_CGM_SHARED_SECRET}

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=str(CLOUD_BACKEND_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                r = httpx.get(f"{base_url}/health", timeout=0.5)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            proc.terminate()
            raise RuntimeError("cloud-backend did not start in time")
        yield base_url
    finally:
        proc.terminate()
        proc.wait(timeout=5)
