import json

import httpx

from integrations.stalwart.mail_jmap import JMAP_MAIL, MailJMAPClient


def test_discovers_session_with_user_bearer_token():
    seen = {}

    def handler(request):
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "apiUrl": "https://mail.example.test/jmap",
                "accounts": {"u1": {"name": "alice@example.test"}},
                "primaryAccounts": {JMAP_MAIL: "u1"},
            },
        )

    client = MailJMAPClient(
        access_token="user-token",
        base_url="https://mail.example.test",
        transport=httpx.MockTransport(handler),
    )

    assert client.primary_mail_account_id() == "u1"
    assert seen["authorization"] == "Bearer user-token"


def test_lists_mailboxes_and_recent_email():
    calls = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "apiUrl": "https://mail.example.test/jmap",
                    "accounts": {"u1": {"name": "alice@example.test"}},
                    "primaryAccounts": {JMAP_MAIL: "u1"},
                },
            )

        payload = json.loads(request.content)
        method = payload["methodCalls"][0][0]
        calls.append(method)
        if method == "Mailbox/query":
            data = {"accountId": "u1", "queryState": "m1", "ids": ["inbox"]}
        elif method == "Mailbox/get":
            data = {
                "accountId": "u1",
                "state": "m2",
                "list": [
                    {
                        "id": "inbox",
                        "name": "Inbox",
                        "role": "inbox",
                        "sortOrder": 10,
                        "totalEmails": 3,
                        "unreadEmails": 1,
                    }
                ],
            }
        elif method == "Email/query":
            data = {
                "accountId": "u1",
                "queryState": "e1",
                "ids": ["email-1"],
                "position": 0,
                "total": 1,
            }
        elif method == "Email/get":
            data = {
                "accountId": "u1",
                "state": "e2",
                "list": [
                    {
                        "id": "email-1",
                        "threadId": "thread-1",
                        "subject": "Welcome",
                        "preview": "Hello from MailForge",
                        "receivedAt": "2026-08-12T10:00:00Z",
                        "from": [{"name": "Support", "email": "support@example.test"}],
                        "to": [{"name": "Alice", "email": "alice@example.test"}],
                        "mailboxIds": {"inbox": True},
                        "keywords": {"$seen": True},
                        "size": 1234,
                        "hasAttachment": False,
                    }
                ],
            }
        else:
            raise AssertionError(f"Unexpected JMAP method: {method}")

        return httpx.Response(200, json={"methodResponses": [[method, data, "c1"]]})

    client = MailJMAPClient(
        access_token="user-token",
        base_url="https://mail.example.test",
        transport=httpx.MockTransport(handler),
    )

    mailboxes = client.list_mailboxes()
    messages = client.list_emails(mailbox_id="inbox")

    assert mailboxes[0]["role"] == "inbox"
    assert mailboxes[0]["unreadEmails"] == 1
    assert messages["emails"][0]["subject"] == "Welcome"
    assert messages["total"] == 1
    assert calls == ["Mailbox/query", "Mailbox/get", "Email/query", "Email/get"]
