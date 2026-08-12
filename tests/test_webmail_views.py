from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client


User = get_user_model()


class FakeMailClient:
    def session(self):
        return {
            "accounts": {"u1": {"name": "alice@example.test"}},
            "primaryAccounts": {"urn:ietf:params:jmap:mail": "u1"},
        }

    def primary_mail_account_id(self):
        return "u1"

    def list_mailboxes(self):
        return [
            {
                "id": "inbox",
                "name": "Inbox",
                "role": "inbox",
                "unreadEmails": 1,
            }
        ]

    def list_emails(self, *, mailbox_id=None, limit=50, position=0):
        assert mailbox_id in {None, "inbox"}
        return {
            "emails": [
                {
                    "id": "email-1",
                    "threadId": "thread-1",
                    "subject": "Welcome to MailForge",
                    "preview": "Your first secure message",
                    "keywords": {},
                    "from": [{"name": "Support", "email": "support@example.test"}],
                    "to": [{"name": "Alice", "email": "alice@example.test"}],
                    "receivedAt": "2026-08-12T10:00:00Z",
                    "hasAttachment": False,
                }
            ],
            "total": 1,
            "position": position,
            "queryState": "state-1",
        }

    def get_email(self, email_id):
        assert email_id == "email-1"
        return {
            "id": "email-1",
            "subject": "Potentially unsafe message",
            "from": [{"name": "Sender", "email": "sender@example.test"}],
            "to": [{"name": "Alice", "email": "alice@example.test"}],
            "receivedAt": "2026-08-12T10:00:00Z",
            "textBody": [{"partId": "1"}],
            "bodyValues": {
                "1": {
                    "value": "Hello <script>alert('xss')</script> <b>not raw html</b>"
                }
            },
            "attachments": [],
            "hasAttachment": False,
            "preview": "Hello",
        }


@pytest.fixture
def authenticated_client(db):
    user = User.objects.create_user(username="webmail-user", password="safe-test-password")
    client = Client()
    client.force_login(user)
    return client


def test_webmail_requires_django_login():
    response = Client().get("/mail/")

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")


@pytest.mark.django_db
def test_webmail_home_shows_secure_connect_without_mail_token(authenticated_client):
    response = authenticated_client.get("/mail/")

    assert response.status_code == 200
    assert b"Connect mailbox" in response.content
    assert b"password" in response.content.lower()


@pytest.mark.django_db
def test_inbox_renders_user_scoped_jmap_messages(authenticated_client):
    with patch("mailforge.webmail_views._mail_client", return_value=FakeMailClient()):
        response = authenticated_client.get("/mail/inbox/?mailbox=inbox")

    assert response.status_code == 200
    assert b"alice@example.test" in response.content
    assert b"Welcome to MailForge" in response.content
    assert b"Your first secure message" in response.content
    assert b"Inbox" in response.content


@pytest.mark.django_db
def test_message_plain_text_is_html_escaped(authenticated_client):
    with patch("mailforge.webmail_views._mail_client", return_value=FakeMailClient()):
        response = authenticated_client.get("/mail/messages/email-1/")

    assert response.status_code == 200
    html = response.content.decode()
    assert "<script>alert('xss')</script>" not in html
    assert "&lt;script&gt;alert" in html
    assert "<b>not raw html</b>" not in html
    assert "&lt;b&gt;not raw html&lt;/b&gt;" in html
