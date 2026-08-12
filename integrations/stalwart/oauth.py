from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx


class StalwartOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class PKCEFlow:
    state: str
    verifier: str
    challenge: str


def create_pkce_flow() -> PKCEFlow:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PKCEFlow(
        state=secrets.token_urlsafe(32),
        verifier=verifier,
        challenge=challenge,
    )


class StalwartOAuthClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        client_id: str,
        client_secret: str = "",
        verify: bool | None = None,
        timeout: float = 15.0,
        transport=None,
    ):
        if not client_id:
            raise StalwartOAuthError("OAuth client id is required.")
        self.base_url = (base_url or os.environ["STALWART_BASE_URL"]).rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        if verify is None:
            verify = os.environ.get("STALWART_VERIFY_TLS", "1") == "1"
        self.verify = verify
        self.timeout = timeout
        self.transport = transport
        self._metadata: dict[str, Any] | None = None

    def _client(self):
        return httpx.Client(
            base_url=self.base_url,
            verify=self.verify,
            timeout=self.timeout,
            transport=self.transport,
        )

    def metadata(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._metadata is not None and not refresh:
            return self._metadata
        try:
            with self._client() as client:
                response = client.get("/.well-known/oauth-authorization-server")
                response.raise_for_status()
                metadata = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StalwartOAuthError("Unable to discover Stalwart OAuth endpoints.") from exc

        if not metadata.get("authorization_endpoint") or not metadata.get("token_endpoint"):
            raise StalwartOAuthError("Stalwart OAuth metadata is incomplete.")
        self._metadata = metadata
        return metadata

    def authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        scope: str = "",
    ) -> str:
        metadata = self.metadata()
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if scope.strip():
            params["scope"] = scope.strip()
        return f"{metadata['authorization_endpoint']}?{urlencode(params)}"

    def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        metadata = self.metadata()
        auth = None
        methods = metadata.get("token_endpoint_auth_methods_supported", [])
        if self.client_secret and (not methods or "client_secret_basic" in methods):
            auth = (self.client_id, self.client_secret)
        else:
            data["client_id"] = self.client_id
            if self.client_secret:
                data["client_secret"] = self.client_secret

        try:
            with self._client() as client:
                response = client.post(metadata["token_endpoint"], data=data, auth=auth)
                response.raise_for_status()
                token = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StalwartOAuthError("Stalwart OAuth token exchange failed.") from exc

        if not token.get("access_token"):
            raise StalwartOAuthError("Stalwart did not return an access token.")
        return token

    def exchange_code(self, *, code: str, redirect_uri: str, code_verifier: str) -> dict[str, Any]:
        return self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            }
        )

    def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        return self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        )
