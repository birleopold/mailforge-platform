import os
import httpx
from integrations.base import MailBackend

class MailcowClient(MailBackend):
    def __init__(self, base_url=None, api_key=None, verify=None):
        self.base_url = (base_url or os.environ["MAILCOW_BASE_URL"]).rstrip("/")
        self.api_key = api_key or os.environ["MAILCOW_API_KEY"]
        if verify is None:
            verify = os.environ.get("MAILCOW_VERIFY_TLS", "1") == "1"
        self.verify = verify

    @property
    def headers(self):
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _post(self, path, payload):
        with httpx.Client(
            base_url=self.base_url,
            headers=self.headers,
            verify=self.verify,
            timeout=15.0,
        ) as client:
            response = client.post(path, json=payload)
            response.raise_for_status()
            return response.json() if response.content else None

    def create_domain(self, *, domain, max_mailboxes, quota_mb):
        # Endpoint/payload should be validated against the deployed mailcow version
        # before production use.
        return self._post(
            "/api/v1/add/domain",
            {
                "domain": domain,
                "max_num_mboxes_for_domain": max_mailboxes,
                "quota": quota_mb,
                "active": "1",
            },
        )

    def create_mailbox(self, *, email, password, quota_mb, display_name=""):
        local_part, domain = email.rsplit("@", 1)
        return self._post(
            "/api/v1/add/mailbox",
            {
                "local_part": local_part,
                "domain": domain,
                "name": display_name,
                "password": password,
                "password2": password,
                "quota": quota_mb,
                "active": "1",
            },
        )

    def suspend_mailbox(self, *, email):
        raise NotImplementedError("Implement after validating the target mailcow API version.")

    def create_alias(self, *, address, destinations):
        raise NotImplementedError("Implement after validating the target mailcow API version.")
