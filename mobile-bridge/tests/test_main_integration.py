import httpx
import pytest

from app import calibration, forwarder
from app.main import app as mobile_app


@pytest.mark.asyncio
async def test_frame_flows_end_to_end_through_live_cloud_backend(
    live_cloud_backend, monkeypatch
):
    monkeypatch.setattr(forwarder, "CLOUD_BACKEND_URL", live_cloud_backend)
    calibration.clear_cache()

    transport = httpx.ASGITransport(app=mobile_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mobile-bridge.test"
    ) as client:
        profile_resp = await client.post(
            "/profile",
            json={
                "name": "Biscuit",
                "breed": "Beagle",
                "weight_kg": 12.5,
                "feeding_schedule": ["07:00", "17:00"],
            },
        )
        assert profile_resp.status_code == 201
        dog_id = profile_resp.json()["dog_id"]

        frame_resp = await client.post(
            "/telemetry/frame",
            json={
                "dog_id": dog_id,
                "timestamp": "2026-01-01T07:00:00+00:00",
                "raw_value": 21.6,
                "temperature_f": 101.5,
            },
        )
        assert frame_resp.status_code == 200
        body = frame_resp.json()
        assert body["status"] == "ok"
        assert "reading_id" in body

    async with httpx.AsyncClient(base_url=live_cloud_backend) as cloud_client:
        readings_resp = await cloud_client.get(f"/readings/{dog_id}")
        assert readings_resp.status_code == 200
        assert len(readings_resp.json()) == 1
