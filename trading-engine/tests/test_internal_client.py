"""HMAC sign + verify round-trip tests."""
from __future__ import annotations

import time

from live.internal_client import InternalClient, verify_signature


def test_sign_then_verify_succeeds():
    c = InternalClient(base_url="http://example", secret="topsecret")
    body = b'{"a":1}'
    headers = c._sign("POST", "/internal/signals", body)
    ok = verify_signature(
        method="POST",
        path="/internal/signals",
        body=body,
        ts=headers["X-Internal-Ts"],
        nonce=headers["X-Internal-Nonce"],
        presented_sig=headers["X-Internal-Sig"],
        secret="topsecret",
    )
    assert ok is True


def test_wrong_secret_fails():
    c = InternalClient(base_url="http://example", secret="topsecret")
    body = b'{"a":1}'
    headers = c._sign("POST", "/internal/signals", body)
    ok = verify_signature(
        method="POST",
        path="/internal/signals",
        body=body,
        ts=headers["X-Internal-Ts"],
        nonce=headers["X-Internal-Nonce"],
        presented_sig=headers["X-Internal-Sig"],
        secret="WRONG",
    )
    assert ok is False


def test_body_tamper_fails():
    c = InternalClient(base_url="http://example", secret="topsecret")
    body = b'{"a":1}'
    headers = c._sign("POST", "/internal/signals", body)
    ok = verify_signature(
        method="POST",
        path="/internal/signals",
        body=b'{"a":2}',  # tampered
        ts=headers["X-Internal-Ts"],
        nonce=headers["X-Internal-Nonce"],
        presented_sig=headers["X-Internal-Sig"],
        secret="topsecret",
    )
    assert ok is False


def test_replay_outside_skew_window_fails():
    c = InternalClient(base_url="http://example", secret="topsecret")
    body = b"{}"
    headers = c._sign("POST", "/internal/signals", body)
    # Force the timestamp very old.
    headers["X-Internal-Ts"] = str(int(time.time()) - 999_999)
    # Re-sign with the old timestamp so signature matches the canonical
    # — verify must still reject because of skew.
    import hashlib
    import hmac as _hmac

    canonical = (
        f"POST\n/internal/signals\n{headers['X-Internal-Ts']}\n"
        f"{headers['X-Internal-Nonce']}\n{hashlib.sha256(body).hexdigest()}"
    ).encode()
    sig = _hmac.new(b"topsecret", canonical, hashlib.sha256).hexdigest()
    ok = verify_signature(
        method="POST",
        path="/internal/signals",
        body=body,
        ts=headers["X-Internal-Ts"],
        nonce=headers["X-Internal-Nonce"],
        presented_sig=sig,
        secret="topsecret",
    )
    assert ok is False
