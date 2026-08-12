from __future__ import annotations

import os
from typing import Any

import httpx

from integrations.base import MailBackend


JMAP_CORE = "urn:ietf:params:jmap:core"
STALWART_JMAP = "urn:stalwart:jmap"


class StalwartAPIError(RuntimeError):
    pass


class StalwartClient(MailBackend):
    """Small JMAP management client for a native Stalwart installation."""

    def __init__(self, base_url=None, token=None, verify=None, *, timeout: float = 15.0):
        self.base_url = (base_url or os.environ["STALWART_BASE_URL"]).rstrip("/")
        self.token = token or os.environ["STALWART_API_TOKEN"]
        if verify is None:
            verify = os.environ.get("STALWART_VERIFY_TLS", "1") == "1"
        self.verify = verify
        self.timeout = timeout

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _call(self, method: str, arguments: dict[str, Any], call_id: str = "c1"):
        payload = {
            "using": [JMAP_CORE, STALWART_JMAP],
            "methodCalls": [[method, arguments, call_id]],
        }
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers=self.headers,
                verify=self.verify,
                timeout=self.timeout,
            ) as client:
                response = client.post("/api", json=payload)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StalwartAPIError(f"Stalwart request failed: {exc}") from exc

        responses = body.get("methodResponses", [])
        if not responses:
            raise StalwartAPIError("Stalwart returned no JMAP method response.")

        response_method, data, _ = responses[0]
        if response_method == "error" or response_method.endswith("/error"):
            raise StalwartAPIError(str(data))
        return data

    def create_domain(self, *, domain, max_mailboxes, quota_mb):
        del max_mailboxes, quota_mb  # MailForge enforces v1 tenant limits in its own DB.
        data = self._call(
            "x:Domain/set",
            {
                "create": {
                    "mailforge": {
                        "name": domain,
                        "aliases": {},
                        "certificateManagement": {"@type": "Manual"},
                        "dkimManagement": {"@type": "Automatic"},
                        "dnsManagement": {"@type": "Manual"},
                        "subAddressing": {"@type": "Enabled"},
                    }
                }
            },
        )
        created = data.get("created", {}).get("mailforge")
        if not created or "id" not in created:
            raise StalwartAPIError(f"Domain was not created: {data}")
        return created

    def get_domain_id(self, domain: str) -> str:
        data = self._call("x:Domain/query", {"filter": {"name": domain}, "limit": 2})
        ids = data.get("ids", [])
        if len(ids) != 1:
            raise StalwartAPIError(f"Expected one Stalwart domain for {domain!r}, found {len(ids)}.")
        return ids[0]

    def create_mailbox(self, *, email, password, quota_mb, display_name=""):
        local_part, domain = email.rsplit("@", 1)
        domain_id = self.get_domain_id(domain)
        data = self._call(
            "x:Account/set",
            {
                "create": {
                    "mailforge": {
                        "@type": "User",
                        "name": local_part,
                        "domainId": domain_id,
                        "description": display_name or email,
                        "credentials": {
                            "0": {"@type": "Password", "secret": password}
                        },
                        "memberGroupIds": {},
                        "roles": {"@type": "User"},
                        "permissions": {"@type": "Inherit"},
                        "quotas": {"maxDiskQuota": quota_mb * 1024 * 1024},
                        "aliases": {},
                        "encryptionAtRest": {"@type": "Disabled"},
                    }
                }
            },
        )
        created = data.get("created", {}).get("mailforge")
        if not created or "id" not in created:
            raise StalwartAPIError(f"Mailbox was not created: {data}")
        return created

    def suspend_mailbox(self, *, email):
        raise NotImplementedError("Mailbox suspension is part of the lifecycle-management milestone.")

    def create_alias(self, *, address, destinations):
        local_part, domain = address.rsplit("@", 1)
        domain_id = self.get_domain_id(domain)
        data = self._call(
            "x:MailingList/set",
            {
                "create": {
                    "mailforge": {
                        "name": local_part,
                        "domainId": domain_id,
                        "description": f"MailForge forwarder for {address}",
                        "recipients": list(destinations),
                        "aliases": {},
                    }
                }
            },
        )
        created = data.get("created", {}).get("mailforge")
        if not created or "id" not in created:
            raise StalwartAPIError(f"Alias was not created: {data}")
        return created
