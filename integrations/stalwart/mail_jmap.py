from __future__ import annotations

import os
from typing import Any

import httpx


JMAP_CORE = "urn:ietf:params:jmap:core"
JMAP_MAIL = "urn:ietf:params:jmap:mail"
JMAP_SUBMISSION = "urn:ietf:params:jmap:submission"


class MailJMAPError(RuntimeError):
    pass


class MailJMAPClient:
    """User-scoped JMAP client. It never uses the Stalwart management API key."""

    def __init__(
        self,
        *,
        access_token: str,
        base_url: str | None = None,
        verify: bool | None = None,
        timeout: float = 15.0,
        transport=None,
    ):
        if not access_token:
            raise MailJMAPError("A user access token is required.")
        self.access_token = access_token
        self.base_url = (base_url or os.environ["STALWART_BASE_URL"]).rstrip("/")
        if verify is None:
            verify = os.environ.get("STALWART_VERIFY_TLS", "1") == "1"
        self.verify = verify
        self.timeout = timeout
        self.transport = transport
        self._session: dict[str, Any] | None = None

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _client(self):
        return httpx.Client(
            base_url=self.base_url,
            headers=self.headers,
            verify=self.verify,
            timeout=self.timeout,
            transport=self.transport,
        )

    def session(self, *, refresh: bool = False) -> dict[str, Any]:
        if self._session is not None and not refresh:
            return self._session
        try:
            with self._client() as client:
                response = client.get("/.well-known/jmap")
                response.raise_for_status()
                session = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MailJMAPError("Unable to discover the JMAP session.") from exc

        if not session.get("apiUrl") or not session.get("accounts"):
            raise MailJMAPError("The JMAP session is missing required fields.")
        self._session = session
        return session

    def primary_mail_account_id(self) -> str:
        session = self.session()
        account_id = session.get("primaryAccounts", {}).get(JMAP_MAIL)
        if not account_id:
            raise MailJMAPError("This user has no primary JMAP mail account.")
        return str(account_id)

    def call(self, method_calls, *, using=None) -> list[list[Any]]:
        session = self.session()
        payload = {
            "using": list(using or (JMAP_CORE, JMAP_MAIL)),
            "methodCalls": method_calls,
        }
        try:
            with self._client() as client:
                response = client.post(session["apiUrl"], json=payload)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MailJMAPError("The JMAP request failed.") from exc

        responses = body.get("methodResponses")
        if not isinstance(responses, list):
            raise MailJMAPError("The JMAP server returned an invalid response.")
        for response_method, data, _ in responses:
            if response_method == "error" or response_method.endswith("/error"):
                error_type = data.get("type", "unknown") if isinstance(data, dict) else "unknown"
                raise MailJMAPError(f"JMAP method failed: {error_type}.")
        return responses

    @staticmethod
    def _created(data: dict[str, Any], creation_id: str, object_name: str) -> dict[str, Any]:
        item = (data.get("created") or {}).get(creation_id)
        if item:
            return item
        error = (data.get("notCreated") or {}).get(creation_id) or {}
        error_type = error.get("type", "unknown")
        description = error.get("description")
        suffix = f" ({description})" if description else ""
        raise MailJMAPError(f"{object_name} could not be created: {error_type}{suffix}.")

    def list_mailboxes(self) -> list[dict[str, Any]]:
        account_id = self.primary_mail_account_id()
        responses = self.call(
            [
                [
                    "Mailbox/query",
                    {
                        "accountId": account_id,
                        "sort": [
                            {"property": "sortOrder", "isAscending": True},
                            {"property": "name", "isAscending": True},
                        ],
                        "limit": 200,
                    },
                    "q1",
                ]
            ]
        )
        ids = responses[0][1].get("ids", [])
        if not ids:
            return []

        responses = self.call(
            [
                [
                    "Mailbox/get",
                    {
                        "accountId": account_id,
                        "ids": ids,
                        "properties": [
                            "id",
                            "name",
                            "parentId",
                            "role",
                            "sortOrder",
                            "totalEmails",
                            "unreadEmails",
                            "totalThreads",
                            "unreadThreads",
                            "myRights",
                        ],
                    },
                    "g1",
                ]
            ]
        )
        return responses[0][1].get("list", [])

    def list_identities(self) -> list[dict[str, Any]]:
        account_id = self.primary_mail_account_id()
        responses = self.call(
            [
                [
                    "Identity/get",
                    {
                        "accountId": account_id,
                        "ids": None,
                        "properties": [
                            "id",
                            "name",
                            "email",
                            "replyTo",
                            "bcc",
                            "textSignature",
                        ],
                    },
                    "i1",
                ]
            ],
            using=(JMAP_CORE, JMAP_MAIL, JMAP_SUBMISSION),
        )
        return responses[0][1].get("list", [])

    def list_emails(
        self,
        *,
        mailbox_id: str | None = None,
        limit: int = 50,
        position: int = 0,
    ) -> dict[str, Any]:
        account_id = self.primary_mail_account_id()
        limit = max(1, min(int(limit), 100))
        position = max(0, int(position))
        query: dict[str, Any] = {
            "accountId": account_id,
            "sort": [{"property": "receivedAt", "isAscending": False}],
            "position": position,
            "limit": limit,
            "calculateTotal": True,
        }
        if mailbox_id:
            query["filter"] = {"inMailbox": mailbox_id}

        responses = self.call([["Email/query", query, "q1"]])
        query_data = responses[0][1]
        ids = query_data.get("ids", [])
        if not ids:
            return {
                "emails": [],
                "total": query_data.get("total", 0),
                "position": query_data.get("position", position),
                "queryState": query_data.get("queryState"),
            }

        responses = self.call(
            [
                [
                    "Email/get",
                    {
                        "accountId": account_id,
                        "ids": ids,
                        "properties": [
                            "id",
                            "threadId",
                            "mailboxIds",
                            "keywords",
                            "size",
                            "receivedAt",
                            "from",
                            "to",
                            "cc",
                            "subject",
                            "preview",
                            "hasAttachment",
                        ],
                    },
                    "g1",
                ]
            ]
        )
        return {
            "emails": responses[0][1].get("list", []),
            "total": query_data.get("total", len(ids)),
            "position": query_data.get("position", position),
            "queryState": query_data.get("queryState"),
        }

    def get_email(self, email_id: str) -> dict[str, Any]:
        account_id = self.primary_mail_account_id()
        responses = self.call(
            [
                [
                    "Email/get",
                    {
                        "accountId": account_id,
                        "ids": [email_id],
                        "properties": [
                            "id",
                            "blobId",
                            "threadId",
                            "mailboxIds",
                            "keywords",
                            "size",
                            "receivedAt",
                            "sentAt",
                            "from",
                            "to",
                            "cc",
                            "bcc",
                            "replyTo",
                            "subject",
                            "preview",
                            "hasAttachment",
                            "bodyStructure",
                            "bodyValues",
                            "textBody",
                            "htmlBody",
                            "attachments",
                        ],
                        "fetchTextBodyValues": True,
                        "fetchHTMLBodyValues": True,
                        "maxBodyValueBytes": 1048576,
                    },
                    "g1",
                ]
            ]
        )
        items = responses[0][1].get("list", [])
        if not items:
            raise MailJMAPError("Email not found.")
        return items[0]

    def send_plaintext(
        self,
        *,
        identity_id: str,
        to: list[dict[str, str]],
        subject: str,
        body: str,
        cc: list[dict[str, str]] | None = None,
        bcc: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        account_id = self.primary_mail_account_id()
        identities = self.list_identities()
        identity = next((item for item in identities if item.get("id") == identity_id), None)
        if identity is None:
            raise MailJMAPError("The selected sending identity is not available.")
        if not to and not cc and not bcc:
            raise MailJMAPError("At least one recipient is required.")

        mailboxes = self.list_mailboxes()
        drafts_id = next((item.get("id") for item in mailboxes if item.get("role") == "drafts"), None)
        sent_id = next((item.get("id") for item in mailboxes if item.get("role") == "sent"), None)
        if not drafts_id or not sent_id:
            raise MailJMAPError("The mailbox must have Drafts and Sent folders before sending.")

        text = body
        signature = (identity.get("textSignature") or "").strip()
        if signature:
            text = f"{text.rstrip()}\n\n{signature}\n"

        draft = {
            "mailboxIds": {drafts_id: True},
            "keywords": {"$draft": True, "$seen": True},
            "from": [
                {
                    "name": identity.get("name") or None,
                    "email": identity["email"],
                }
            ],
            "to": to,
            "subject": subject,
            "bodyStructure": {"type": "text/plain", "partId": "body"},
            "bodyValues": {"body": {"value": text}},
        }
        if cc:
            draft["cc"] = cc
        if bcc:
            draft["bcc"] = bcc
        if identity.get("replyTo"):
            draft["replyTo"] = identity["replyTo"]

        responses = self.call(
            [
                [
                    "Email/set",
                    {
                        "accountId": account_id,
                        "create": {"mailforge-draft": draft},
                    },
                    "draft-create",
                ]
            ],
            using=(JMAP_CORE, JMAP_MAIL),
        )
        created_email = self._created(responses[0][1], "mailforge-draft", "Draft")
        email_id = created_email["id"]

        responses = self.call(
            [
                [
                    "EmailSubmission/set",
                    {
                        "accountId": account_id,
                        "create": {
                            "mailforge-submit": {
                                "identityId": identity_id,
                                "emailId": email_id,
                            }
                        },
                        "onSuccessUpdateEmail": {
                            "#mailforge-submit": {
                                f"mailboxIds/{drafts_id}": None,
                                f"mailboxIds/{sent_id}": True,
                                "keywords/$draft": None,
                            }
                        },
                    },
                    "submit",
                ]
            ],
            using=(JMAP_CORE, JMAP_MAIL, JMAP_SUBMISSION),
        )
        submission = self._created(
            responses[0][1],
            "mailforge-submit",
            "Email submission",
        )
        return {
            "emailId": email_id,
            "submissionId": submission["id"],
        }
