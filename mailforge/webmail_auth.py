from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


FLOW_SESSION_KEY = "mailforge_webmail_oauth_flow"
TOKEN_SESSION_KEY = "mailforge_webmail_oauth_token"


class WebmailSessionError(RuntimeError):
    pass


def _fernet() -> Fernet:
    material = f"mailforge-webmail\0{settings.SECRET_KEY}".encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def _encrypt(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return _fernet().encrypt(raw).decode()


def _decrypt(value: str) -> dict[str, Any]:
    try:
        raw = _fernet().decrypt(value.encode())
        payload = json.loads(raw)
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise WebmailSessionError("Stored webmail session data is invalid.") from exc
    if not isinstance(payload, dict):
        raise WebmailSessionError("Stored webmail session data is invalid.")
    return payload


def store_oauth_flow(request, *, state: str, verifier: str, redirect_uri: str) -> None:
    request.session[FLOW_SESSION_KEY] = _encrypt(
        {
            "state": state,
            "verifier": verifier,
            "redirect_uri": redirect_uri,
            "created_at": int(time.time()),
        }
    )


def pop_oauth_flow(request) -> dict[str, Any]:
    encrypted = request.session.pop(FLOW_SESSION_KEY, None)
    if not encrypted:
        raise WebmailSessionError("The webmail sign-in session has expired.")
    payload = _decrypt(encrypted)
    if int(time.time()) - int(payload.get("created_at", 0)) > 600:
        raise WebmailSessionError("The webmail sign-in session has expired.")
    return payload


def store_oauth_token(request, token: dict[str, Any]) -> None:
    expires_in = max(0, int(token.get("expires_in", 0) or 0))
    payload = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token", ""),
        "token_type": token.get("token_type", "Bearer"),
        "scope": token.get("scope", ""),
        "expires_at": int(time.time()) + expires_in if expires_in else 0,
    }
    request.session[TOKEN_SESSION_KEY] = _encrypt(payload)


def get_oauth_token(request) -> dict[str, Any] | None:
    encrypted = request.session.get(TOKEN_SESSION_KEY)
    if not encrypted:
        return None
    return _decrypt(encrypted)


def token_needs_refresh(token: dict[str, Any], *, leeway_seconds: int = 60) -> bool:
    expires_at = int(token.get("expires_at", 0) or 0)
    return bool(expires_at and expires_at <= int(time.time()) + leeway_seconds)


def clear_oauth_token(request) -> None:
    request.session.pop(TOKEN_SESSION_KEY, None)
    request.session.pop(FLOW_SESSION_KEY, None)
