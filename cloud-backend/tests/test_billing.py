import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import user_auth
from app.database import get_db
from app.deps import require_api_key
from app.main import app
from app.routers import billing as billing_router


@pytest.fixture()
def client(db_engine, monkeypatch):
    # JWT_SECRET is read once at import time in app/config.py, so setenv()
    # after import wouldn't reach it — patch the name user_auth actually uses.
    monkeypatch.setattr(user_auth, "JWT_SECRET", "test-secret")
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_api_key] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def signup(client, email="trader@example.com", password="correcthorsebattery"):
    resp = client.post("/auth/signup", json={"email": email, "password": password})
    assert resp.status_code == 201
    return resp.json()["token"]


def test_signup_creates_free_subscription_and_a_usable_token(client):
    token = signup(client, email="Trader@Example.com")

    me = client.get("/auth/me", headers={"authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "trader@example.com"
    assert body["subscription_status"] == "none"


def test_signup_rejects_duplicate_email_and_short_password(client):
    signup(client, email="dup@example.com")
    dup = client.post("/auth/signup", json={"email": "dup@example.com", "password": "anotherlongpw"})
    assert dup.status_code == 409

    short = client.post("/auth/signup", json={"email": "new@example.com", "password": "short"})
    assert short.status_code == 422  # pydantic min_length


def test_login_accepts_right_password_rejects_wrong(client):
    signup(client, email="login@example.com", password="correcthorsebattery")

    ok = client.post("/auth/login", json={"email": "login@example.com", "password": "correcthorsebattery"})
    assert ok.status_code == 200

    wrong = client.post("/auth/login", json={"email": "login@example.com", "password": "wrongpassword"})
    assert wrong.status_code == 401


def test_me_rejects_missing_or_invalid_token(client):
    missing = client.get("/auth/me")
    assert missing.status_code == 401

    invalid = client.get("/auth/me", headers={"authorization": "Bearer not-a-real-token"})
    assert invalid.status_code == 401


def test_checkout_requires_auth_and_passes_user_through(client, monkeypatch):
    token = signup(client)

    captured = {}

    def fake_create_checkout_session(user_id, email, customer_id, return_url):
        captured["user_id"] = user_id
        captured["email"] = email
        return SimpleNamespace(url="https://checkout.stripe.com/test-session")

    monkeypatch.setattr(billing_router.billing_service, "create_checkout_session", fake_create_checkout_session)

    unauth = client.post("/billing/checkout", json={"return_url": "https://app.example.com"})
    assert unauth.status_code == 401

    resp = client.post(
        "/billing/checkout",
        json={"return_url": "https://app.example.com"},
        headers={"authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://checkout.stripe.com/test-session"
    assert captured["email"] == "trader@example.com"


def test_webhook_rejects_bad_signature(client, monkeypatch):
    def fail(*a, **k):
        raise ValueError("bad signature")

    monkeypatch.setattr(billing_router.billing_service, "verify_webhook_event", fail)

    resp = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "bogus"})
    assert resp.status_code == 400


def test_webhook_activates_subscription_on_checkout_completed(client, monkeypatch):
    token = signup(client)
    me = client.get("/auth/me", headers={"authorization": f"Bearer {token}"}).json()

    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_123", "subscription": "sub_123", "client_reference_id": str(me["id"])}},
    }
    monkeypatch.setattr(billing_router.billing_service, "verify_webhook_event", lambda *a, **k: event)

    resp = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "valid"})
    assert resp.status_code == 200

    status = client.get("/billing/status", headers={"authorization": f"Bearer {token}"})
    assert status.json()["status"] == "active"


def test_webhook_reverts_subscription_on_deleted(client, monkeypatch):
    token = signup(client)
    me = client.get("/auth/me", headers={"authorization": f"Bearer {token}"}).json()

    activate_event = {
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_456", "subscription": "sub_456", "client_reference_id": str(me["id"])}},
    }
    monkeypatch.setattr(billing_router.billing_service, "verify_webhook_event", lambda *a, **k: activate_event)
    client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "valid"})

    delete_event = {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_456", "status": "canceled"}}}
    monkeypatch.setattr(billing_router.billing_service, "verify_webhook_event", lambda *a, **k: delete_event)
    resp = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "valid"})
    assert resp.status_code == 200

    status = client.get("/billing/status", headers={"authorization": f"Bearer {token}"})
    assert status.json()["status"] == "canceled"
