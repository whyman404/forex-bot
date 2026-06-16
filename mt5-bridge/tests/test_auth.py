"""Auth tests — bearer token must be present + match in constant-time."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mt5_bridge.auth import make_token_dependency


def _make_app(token: str) -> TestClient:
    from fastapi import Depends

    from mt5_bridge.config import BridgeConfig

    cfg = BridgeConfig(bind="127.0.0.1:0", token=token)
    dep = make_token_dependency(cfg)
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(dep)])
    def _p():
        return {"ok": True}

    return TestClient(app)


def test_missing_authorization_header_401():
    client = _make_app("a" * 48)
    r = client.get("/protected")
    assert r.status_code == 401
    assert "missing Authorization header" in r.json()["detail"]


def test_wrong_scheme_401():
    client = _make_app("a" * 48)
    r = client.get("/protected", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


def test_wrong_token_401():
    client = _make_app("a" * 48)
    r = client.get("/protected", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_correct_token_200():
    tok = "a" * 48
    client = _make_app(tok)
    r = client.get("/protected", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


def test_constant_time_compare_handles_length_mismatch():
    """A wrong token of different length should still 401 (no crash)."""
    client = _make_app("a" * 48)
    r = client.get("/protected", headers={"Authorization": "Bearer x"})
    assert r.status_code == 401
