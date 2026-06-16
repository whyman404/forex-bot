"""Smoke tests for /live/* endpoints — verify routes register and 404s work."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from fastapi import FastAPI

    from live.server_endpoints import register_live_routes

    app = FastAPI()
    register_live_routes(app)
    return app


def test_live_list_empty(app):
    with TestClient(app) as c:
        r = c.get("/live")
        assert r.status_code == 200
        assert r.json() == {"engines": []}


def test_live_status_404_when_unknown(app):
    with TestClient(app) as c:
        r = c.get("/live/does-not-exist/status")
        assert r.status_code == 404


def test_live_health_returns_not_found(app):
    with TestClient(app) as c:
        r = c.get("/live/does-not-exist/health")
        assert r.status_code == 200
        body = r.json()
        assert body["found"] is False


def test_live_stop_unknown_404(app):
    with TestClient(app) as c:
        r = c.post("/live/stop", json={"strategy_instance_id": "missing"})
        assert r.status_code == 404


def test_live_kill_unknown_404(app):
    with TestClient(app) as c:
        r = c.post("/live/kill", json={"strategy_instance_id": "missing"})
        assert r.status_code == 404
