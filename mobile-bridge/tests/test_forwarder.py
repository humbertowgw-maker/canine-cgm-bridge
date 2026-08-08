import httpx
import pytest

from app import forwarder


def _mock_client_factory(handler):
    def _build_client() -> httpx.AsyncClient:
        transport = httpx.MockTransport(handler)
        return httpx.AsyncClient(transport=transport, base_url="http://cloud-backend.test")

    return _build_client


@pytest.mark.asyncio
async def test_request_with_retry_returns_json_on_success(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(201, json={"id": 1, "ok": True})

    monkeypatch.setattr(forwarder, "CLOUD_BACKEND_URL", "http://cloud-backend.test")
    monkeypatch.setattr(forwarder, "_build_client", _mock_client_factory(handler))

    result = await forwarder._request_with_retry("POST", "/dogs", {"name": "Rex"})
    assert result == {"id": 1, "ok": True}


@pytest.mark.asyncio
async def test_request_with_retry_succeeds_after_transient_failures(monkeypatch):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(forwarder, "CLOUD_BACKEND_URL", "http://cloud-backend.test")
    monkeypatch.setattr(forwarder, "RETRY_DELAYS_SECONDS", [0.001, 0.001, 0.001])
    monkeypatch.setattr(forwarder, "_build_client", _mock_client_factory(handler))

    result = await forwarder._request_with_retry("POST", "/readings", {})
    assert result == {"ok": True}
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_request_with_retry_drops_after_exhausting_retries(monkeypatch, caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    monkeypatch.setattr(forwarder, "CLOUD_BACKEND_URL", "http://cloud-backend.test")
    monkeypatch.setattr(forwarder, "RETRY_DELAYS_SECONDS", [0.001, 0.001, 0.001])
    monkeypatch.setattr(forwarder, "_build_client", _mock_client_factory(handler))

    import logging

    with caplog.at_level(logging.ERROR):
        result = await forwarder._request_with_retry("POST", "/readings", {})

    assert result is None
    assert any("Giving up" in msg for msg in caplog.messages)
