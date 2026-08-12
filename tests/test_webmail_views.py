from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.domains.models import Domain
from apps.tenants.models import Tenant


User = get_user_model()


class FakeMailClient:
    def __init__(self):
        self.sent = None
        self.last_search = None
        self.seen_updates = []

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

    def list_identities(self):
        return [
            {
                "id": "identity-1",
                "name": "Alice",
                "email": "alice@example.test",
                "textSignature": "",
            }
        ]

    def list_emails(
        self,
        *,
        mailbox_id=None,
        search_text=None,
        limit=50,
        position=0,
    ):
        assert mailbox_id in {None, "inbox"}
        self.last_search = search_text
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
            "keywords": {},
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

    def set_seen(self, email_id, *, seen):
        self.seen_updates.append((email_id, seen))

    def send_plaintext(self, **kwargs):
        self.sent = kwargs
        return {"emailId": "email-2", "submissionId": "submission-1"}


@pytest.fixture
def authenticated_client(db):
    user = User.objects.create_user(username="webmail-user", password="safe-test-password")
    client = Client()
    client.force_login(user)
    return client


def create_mail_domain(*, ready):
    tenant = Tenant.objects.create(name="Mail Tenant", slug="mail-tenant")
    return Domain.objects.create(
        tenant=tenant,
        name="example.test",
        status=Domain.Status.ACTIVE if ready else Domain.Status.DNS_CONFIGURATION,
        sending_enabled=ready,
        backend_identifier="domain-1",
    )


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
    assert b"Compose" in response.content


@pytest.mark.django_db
def test_inbox_search_is_forwarded_to_jmap(authenticated_client):
    mail = FakeMailClient()
    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.get("/mail/inbox/?mailbox=inbox&q=Quarterly%20report")

    assert response.status_code == 200
    assert mail.last_search == "Quarterly report"
    assert b"Search results" in response.content
    assert b"Quarterly report" in response.content


@pytest.mark.django_db
def test_message_plain_text_is_html_escaped_and_open_marks_seen(authenticated_client):
    mail = FakeMailClient()
    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.get("/mail/messages/email-1/")

    assert response.status_code == 200
    assert mail.seen_updates == [("email-1", True)]
    html = response.content.decode()
    assert "<script>alert('xss')</script>" not in html
    assert "&lt;script&gt;alert" in html
    assert "<b>not raw html</b>" not in html
    assert "&lt;b&gt;not raw html&lt;/b&gt;" in html
    assert "Mark unread" in html


@pytest.mark.django_db
def test_mark_unread_updates_jmap_and_returns_to_inbox(authenticated_client):
    mail = FakeMailClient()
    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.post("/mail/messages/email-1/unread/")

    assert response.status_code == 302
    assert response.url == "/mail/inbox/"
    assert mail.seen_updates == [("email-1", False)]


@pytest.mark.django_db
def test_compose_sends_only_when_identity_domain_is_ready(authenticated_client):
    create_mail_domain(ready=True)
    mail = FakeMailClient()

    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.post(
            "/mail/compose/",
            {
                "identity_id": "identity-1",
                "to": "Bob@Example.NET, bob@example.net",
                "cc": "",
                "bcc": "audit@example.org",
                "subject": "Hello",
                "body": "Secure body",
            },
        )

    assert response.status_code == 302
    assert response.url == "/mail/inbox/"
    assert mail.sent["identity_id"] == "identity-1"
    assert mail.sent["to"] == [{"email": "bob@example.net"}]
    assert mail.sent["bcc"] == [{"email": "audit@example.org"}]
    assert mail.sent["subject"] == "Hello"


@pytest.mark.django_db
def test_compose_blocks_domain_that_failed_readiness_gate(authenticated_client):
    create_mail_domain(ready=False)
    mail = FakeMailClient()

    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.post(
            "/mail/compose/",
            {
                "identity_id": "identity-1",
                "to": "bob@example.net",
                "cc": "",
                "bcc": "",
                "subject": "Blocked",
                "body": "This should not leave MailForge.",
            },
        )

    assert response.status_code == 200
    assert mail.sent is None
    assert b"Sending is disabled for this domain" in response.content
