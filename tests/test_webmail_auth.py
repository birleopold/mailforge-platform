from types import SimpleNamespace

from django.test import override_settings

from mailforge.webmail_auth import (
    FLOW_SESSION_KEY,
    TOKEN_SESSION_KEY,
    clear_oauth_token,
    get_oauth_token,
    pop_oauth_flow,
    store_oauth_flow,
    store_oauth_token,
)


@override_settings(SECRET_KEY="test-secret-key")
def test_webmail_tokens_are_encrypted_in_session():
    request = SimpleNamespace(session={})
    token = {
        "access_token": "access-secret-value",
        "refresh_token": "refresh-secret-value",
        "token_type": "Bearer",
        "expires_in": 3600,
    }

    store_oauth_token(request, token)

    stored = request.session[TOKEN_SESSION_KEY]
    assert "access-secret-value" not in stored
    assert "refresh-secret-value" not in stored
    recovered = get_oauth_token(request)
    assert recovered["access_token"] == "access-secret-value"
    assert recovered["refresh_token"] == "refresh-secret-value"
    assert recovered["expires_at"] > 0


@override_settings(SECRET_KEY="test-secret-key")
def test_oauth_flow_is_one_time_session_data():
    request = SimpleNamespace(session={})
    store_oauth_flow(
        request,
        state="state-secret",
        verifier="pkce-secret",
        redirect_uri="https://app.example.test/mail/oauth/callback/",
    )

    stored = request.session[FLOW_SESSION_KEY]
    assert "state-secret" not in stored
    assert "pkce-secret" not in stored

    flow = pop_oauth_flow(request)
    assert flow["state"] == "state-secret"
    assert flow["verifier"] == "pkce-secret"
    assert FLOW_SESSION_KEY not in request.session


@override_settings(SECRET_KEY="test-secret-key")
def test_clear_removes_webmail_oauth_state_and_token():
    request = SimpleNamespace(session={})
    store_oauth_flow(
        request,
        state="state",
        verifier="verifier",
        redirect_uri="https://app.example.test/mail/oauth/callback/",
    )
    store_oauth_token(request, {"access_token": "access"})

    clear_oauth_token(request)

    assert FLOW_SESSION_KEY not in request.session
    assert TOKEN_SESSION_KEY not in request.session
