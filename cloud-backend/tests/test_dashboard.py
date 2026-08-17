import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.deps import require_api_key
from app.main import app


@pytest.fixture()
def client(db_engine):
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


def test_dashboard_serves_html(client):
    resp = client.get("/dashboard/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]

    body = resp.text
    assert "<title>Canine CGM Bridge" in body
    assert "/readings/" in body
    assert "/dogs/" in body
    assert "/calibration/current" in body
    assert "/alerts" in body


def test_dashboard_redirects_without_trailing_slash(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code in (307, 308)
