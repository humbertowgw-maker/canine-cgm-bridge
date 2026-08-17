import asyncio
import logging

import httpx

from app.config import CGM_SHARED_SECRET, CLOUD_BACKEND_URL

logger = logging.getLogger(__name__)

RETRY_DELAYS_SECONDS = [0.5, 1.0, 2.0]


def _build_client() -> httpx.AsyncClient:
    """Isolated so tests can monkeypatch it to inject an httpx.MockTransport."""
    return httpx.AsyncClient(timeout=5.0)


async def _request_with_retry(method: str, path: str, json: dict | None = None) -> dict | None:
    """Retries up to len(RETRY_DELAYS_SECONDS)+1 times with backoff, then logs an
    ERROR and drops the request (returns None). No persistent queue/replay — this
    is a local $0 demo, not a reliability system."""
    url = f"{CLOUD_BACKEND_URL}{path}"
    async with _build_client() as client:
        for attempt, delay in enumerate([0.0, *RETRY_DELAYS_SECONDS]):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await client.request(
                    method, url, json=json, headers={"X-API-Key": CGM_SHARED_SECRET or ""}
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                logger.warning("Attempt %d %s %s failed: %s", attempt + 1, method, url, exc)

    logger.error(
        "Giving up %s %s after %d attempts; dropping payload",
        method,
        url,
        len(RETRY_DELAYS_SECONDS) + 1,
    )
    return None


async def forward_profile(profile_in: dict) -> dict | None:
    return await _request_with_retry("POST", "/dogs", profile_in)


async def forward_profile_update(dog_id: int, update_in: dict) -> dict | None:
    return await _request_with_retry("PUT", f"/dogs/{dog_id}", update_in)


async def forward_reading(reading: dict) -> dict | None:
    return await _request_with_retry("POST", "/readings", reading)


async def forward_calibration_event(dog_id: int, event: dict) -> dict | None:
    return await _request_with_retry("POST", f"/dogs/{dog_id}/calibration", event)


async def fetch_current_calibration(dog_id: int) -> dict | None:
    return await _request_with_retry("GET", f"/dogs/{dog_id}/calibration/current")
