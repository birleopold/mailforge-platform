from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from integrations.stalwart.mail_jmap import JMAP_CORE, JMAP_MAIL
from mailforge.thread_views import _thread_email_ids, _thread_emails


User = get_user_model()


class ScriptedThreadClient:
    def __init__(self, *, email_ids=None):
        self.email_ids = email_ids or ["e-old", "e-new"]
        self.calls = []

    def session(self):
        return {
            "accounts": {"account-1": {"name": "Mailbox"}},
            "primaryAccounts": {JMAP_MAIL: "account-1"},
        }

    def primary_mail_account_id(self):
        return "account-1"

    def call(self, method_calls, *, using=None):
        self.calls.append((method_calls, tuple(using or ())))
        method, arguments, call_id = method_calls[0]
        assert tuple(using or ()) == (JMAP_CORE, JMAP_MAIL)
        if method == "Thread/get":
            assert arguments["ids"] == ["thread-1"]
            return [
                [
                    "Thread/get",
                    {
                        "list": [
                            {"id": "thread-1", "emailIds": list(self.email_ids)}
                        ]
                    },
                    call_id,
                ]
            ]
        if method == "Email/get":
            emails = []
            for email_id in reversed(arguments["ids"]):
                emails.append(
                    {
                        "id": email_id,
                        "threadId": "thread-1",
                        "receivedAt": "2026-08-13T08:00:00Z",
                        "from": [{"name": "Sender", "email": "sender@example.net"}],
                        "to": [{"email": "user@example.com"}],
                        "subject": "Thread subject",
                        "keywords": {"$seen": True},
                        "bodyValues": {
                            "html": {
                                "value": (
                                    f"<p>{email_id}</p>"
                                    '<img src="https://tracker.example/pixel">'
                                    '<script>alert("x")</script>'
                                )
                            },
                            "text": {"value": f"plain {email_id}"},
                        },
                        "htmlBody": [{"partId": "html"}],
                        "textBody": [{"partId": "text"}],
                        "attachments": [],
                        "hasAttachment": False,
                    }
                )
            return [["Email/get", {"list": emails}, call_id]]
        raise AssertionError(method)


def test_thread_get_uses_server_email_id_order():
    client = ScriptedThreadClient(email_ids=["first", "second", "third"])

    ids = _thread_email_ids(client, account_id="account-1", thread_id="thread-1")

    assert ids == ["first", "second", "third"]


def test_thread_email_fetch_restores_thread_order_and_batches_at_fifty():
    email_ids = [f"e-{index:03d}" for index in range(120)]
    client = ScriptedThreadClient(email_ids=email_ids)

    emails = _thread_emails(client, account_id="account-1", email_ids=email_ids)

    assert [email["id"] for email in emails] == email_ids
    email_get_calls = [
        method_calls
        for method_calls, _ in client.calls
        if method_calls[0][0] == "Email/get"
    ]
    assert len(email_get_calls) == 3
    assert len(email_get_calls[0][0][1]["ids"]) == 50
    assert len(email_get_calls[1][0][1]["ids"]) == 50
    assert len(email_get_calls[2][0][1]["ids"]) == 20


def test_thread_email_fetch_caps_rendering_at_two_hundred_messages():
    email_ids = [f"e-{index:03d}" for index in range(250)]
    client = ScriptedThreadClient(email_ids=email_ids)

    emails = _thread_emails(client, account_id="account-1", email_ids=email_ids)

    assert len(emails) == 200
    assert emails[0]["id"] == "e-000"
    assert emails[-1]["id"] == "e-199"


@pytest.mark.django_db
def test_conversation_view_renders_messages_in_jmap_order_and_sanitizes_html(client):
    user = User.objects.create_user(
        username="thread-user",
        email="user@example.com",
        password="thread-password-123",
    )
    client.force_login(user)
    jmap = ScriptedThreadClient(email_ids=["e-old", "e-new"])

    with patch("mailforge.thread_views._mail_client", return_value=jmap):
        response = client.get(reverse("webmail-thread", kwargs={"thread_id": "thread-1"}))

    assert response.status_code == 200
    content = response.content.decode()
    assert content.index("e-old") < content.index("e-new")
    assert "2 messages in this JMAP thread" in content
    assert "Remote images blocked for privacy" in content
    assert "tracker.example" not in content
    assert "<script" not in content
    assert reverse("webmail-reply", kwargs={"source_id": "e-old"}) in content
    assert reverse("webmail-message", kwargs={"email_id": "e-new"}) in content
