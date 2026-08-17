import httpx
from fastapi.testclient import TestClient

from app import calibration, forwarder
from app.main import app as mobile_app
from tests.conftest import TEST_CGM_SHARED_SECRET

_AUTH_HEADERS = {"X-API-Key": TEST_CGM_SHARED_SECRET}


def _seed_dog(live_cloud_backend: str, name: str) -> int:
    resp = httpx.post(
        f"{live_cloud_backend}/dogs",
        json={
            "name": name,
            "breed": "Beagle",
            "weight_kg": 12.5,
            "feeding_schedule": ["07:00", "17:00"],
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_ws_stream_processes_multiple_frames_and_writes_to_cloud_backend(
    live_cloud_backend, monkeypatch
):
    monkeypatch.setattr(forwarder, "CLOUD_BACKEND_URL", live_cloud_backend)
    calibration.clear_cache()

    dog_id = _seed_dog(live_cloud_backend, "Biscuit")

    frames = [
        {
            "dog_id": dog_id,
            "timestamp": f"2026-01-01T07:0{i}:00+00:00",
            "raw_value": 20.0 + i,
            "temperature_f": 101.5,
        }
        for i in range(5)
    ]

    with TestClient(mobile_app) as client, client.websocket_connect("/telemetry/stream") as ws:
        for frame in frames:
            ws.send_json(frame)
            ack = ws.receive_json()
            assert ack["status"] == "ok"
            assert "reading_id" in ack

    readings_resp = httpx.get(f"{live_cloud_backend}/readings/{dog_id}", headers=_AUTH_HEADERS)
    assert readings_resp.status_code == 200
    assert len(readings_resp.json()) == len(frames)


def test_ws_stream_reports_error_and_stays_open_on_bad_frame(live_cloud_backend, monkeypatch):
    monkeypatch.setattr(forwarder, "CLOUD_BACKEND_URL", live_cloud_backend)
    calibration.clear_cache()

    dog_id = _seed_dog(live_cloud_backend, "Rex")

    with TestClient(mobile_app) as client, client.websocket_connect("/telemetry/stream") as ws:
        ws.send_json({"dog_id": "not-an-int", "timestamp": "not-a-timestamp", "raw_value": 1})
        err = ws.receive_json()
        assert err["status"] == "error"

        # the socket must still be usable after a parse error
        ws.send_json(
            {
                "dog_id": dog_id,
                "timestamp": "2026-01-01T07:00:00+00:00",
                "raw_value": 21.6,
                "temperature_f": 101.5,
            }
        )
        ack = ws.receive_json()
        assert ack["status"] == "ok"

    readings_resp = httpx.get(f"{live_cloud_backend}/readings/{dog_id}", headers=_AUTH_HEADERS)
    assert len(readings_resp.json()) == 1
