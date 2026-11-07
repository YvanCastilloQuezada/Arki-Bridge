"""Tests F3: doble camino de authorize() (estático + ARKI Identity).
Mockea verify_arki_token() para no depender de SICL Web corriendo."""
import json
import pytest
from fastapi import HTTPException

import app as bridge_app


# --- 1. Token estático sigue funcionando (compat total) ---

def test_static_token_still_works():
    out = bridge_app.authorize("Bearer test-bridge-token-32-chars-minimum")
    assert out["subject"] == "bridge-static"
    assert out["client_id"] == "bridge-local"
    assert out["scopes"] == ["*"]


# --- 2. Token ARKI válido (mock introspección) ---

def test_arki_token_valid(monkeypatch):
    def fake_verify(token):
        assert token == "a" * 43
        return {"subject": "u-1", "client_id": "bridge-local", "scopes": ["git:read"]}
    monkeypatch.setattr(bridge_app, "verify_arki_token", fake_verify)
    out = bridge_app.authorize(f"Bearer {'a' * 43}")
    assert out == {"subject": "u-1", "client_id": "bridge-local", "scopes": ["git:read"]}


# --- 3. Token ARKI inválido (mock -> None) ---

def test_arki_token_revoked(monkeypatch):
    monkeypatch.setattr(bridge_app, "verify_arki_token", lambda _t: None)
    with pytest.raises(HTTPException) as exc:
        bridge_app.authorize(f"Bearer {'a' * 43}")
    assert exc.value.status_code == 401


# --- 4. Token formato inválido no llega a verify_arki_token ---

def test_arki_token_wrong_format_no_http(monkeypatch):
    """Formato inválido en verify_arki_token: no hay request HTTP.
    El guard está dentro de verify_arki_token (no en authorize)."""
    import urllib.request
    called = {"n": 0}
    original = urllib.request.urlopen
    def fake(*a, **k):
        called["n"] += 1
        return original(*a, **k)
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    # verify_arki_token con formatos inválidos retorna None sin abrir conexión
    assert bridge_app.verify_arki_token("short") is None
    assert bridge_app.verify_arki_token("a" * 42) is None  # 42 chars
    assert bridge_app.verify_arki_token("a" * 44) is None  # 44 chars
    assert called["n"] == 0


# --- 5. Sin IDENTITY_INTERNAL_KEY configurado (Bridge vive solo de estático) ---

def test_identity_key_missing_falls_back_to_static(monkeypatch):
    monkeypatch.setattr(bridge_app, "IDENTITY_INTERNAL_KEY", "")
    with pytest.raises(HTTPException) as exc:
        bridge_app.authorize(f"Bearer {'a' * 43}")
    assert exc.value.status_code == 401
    # el estático sigue OK
    out = bridge_app.authorize("Bearer test-bridge-token-32-chars-minimum")
    assert out["subject"] == "bridge-static"


# --- 6. Sin token -> 401 ---

def test_no_token():
    with pytest.raises(HTTPException) as exc:
        bridge_app.authorize(None)
    assert exc.value.status_code == 401


# --- 7. verify_arki_token con formato inválido devuelve None sin request HTTP ---

def test_verify_arki_token_format_guard(monkeypatch):
    # Aunque no haya key, formato inválido debe devolver None
    monkeypatch.setattr(bridge_app, "IDENTITY_INTERNAL_KEY", "k")
    assert bridge_app.verify_arki_token("short") is None
    assert bridge_app.verify_arki_token("") is None
    assert bridge_app.verify_arki_token(None) is None


# --- 8. verify_arki_token con key ausente devuelve None ---

def test_verify_arki_token_no_key(monkeypatch):
    monkeypatch.setattr(bridge_app, "IDENTITY_INTERNAL_KEY", "")
    assert bridge_app.verify_arki_token("a" * 43) is None
