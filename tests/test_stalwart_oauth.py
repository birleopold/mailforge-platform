import json
from urllib.parse import parse_qs, urlparse

import httpx

from integrations.stalwart.oauth import StalwartOAuthClient, create_pkce_flow


def test_pkce_authorization_and_code_exchange():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "authorization_endpoint": "https://mail.example.test/auth/authorize",
                    "token_endpoint": "https://mail.example.test/auth/token",
                    "token_endpoint_auth_methods_supported": ["client_secret_basic"],
                },
            )
        assert request.url.path == "/auth/token"
        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["authorization_code"]
        assert form["code"] == ["code-1"]
        assert form["code_verifier"] == [flow.verifier]
        assert request.headers["Authorization"].startswith("Basic ")
        return httpx.Response(
            200,
            json={"access_token": "access-1", "token_type": "Bearer", "expires_in": 3600},
        )

    flow = create_pkce_flow()
    client = StalwartOAuthClient(
        base_url="https://mail.example.test",
        client_id="mailforge-webmail",
        client_secret="client-secret",
        transport=httpx.MockTransport(handler),
    )

    url = client.authorization_url(
        redirect_uri="https://app.example.test/mail/oauth/callback/",
        state=flow.state,
        code_challenge=flow.challenge,
    )
    query = parse_qs(urlparse(url).query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["mailforge-webmail"]
    assert query["state"] == [flow.state]
    assert query["code_challenge"] == [flow.challenge]
    assert query["code_challenge_method"] == ["S256"]

    token = client.exchange_code(
        code="code-1",
        redirect_uri="https://app.example.test/mail/oauth/callback/",
        code_verifier=flow.verifier,
    )

    assert token["access_token"] == "access-1"
    assert len(requests) == 2


def test_public_client_posts_client_id_without_secret():
    captured = {}

    def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "authorization_endpoint": "https://mail.example.test/auth/authorize",
                    "token_endpoint": "https://mail.example.test/auth/token",
                    "token_endpoint_auth_methods_supported": ["none"],
                },
            )
        captured.update(parse_qs(request.content.decode()))
        return httpx.Response(200, json={"access_token": "access-2"})

    client = StalwartOAuthClient(
        base_url="https://mail.example.test",
        client_id="public-webmail",
        transport=httpx.MockTransport(handler),
    )
    client.exchange_code(
        code="code-2",
        redirect_uri="https://app.example.test/mail/oauth/callback/",
        code_verifier="verifier",
    )

    assert captured["client_id"] == ["public-webmail"]
    assert "client_secret" not in captured
