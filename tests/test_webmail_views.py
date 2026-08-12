from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from apps.domains.models import Domain
from apps.tenants.models import Tenant


User = get_user_model()


class FakeMailClient:
    def __init__(self):
        self.sent = None
        self.last_search = None
        self.seen_updates = []
        self.answered_updates = []
        self.uploads = []
        self.downloads = []

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
            },
            {
                "id": "identity-2",
                "name": "Sales",
                "email": "sales@example.test",
                "textSignature": "",
            },
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
                    "from": [{"name": "Support", "email": "support@example.net"}],
                    "to": [{"name": "Alice", "email": "alice@example.test"}],
                    "receivedAt": "2026-08-12T10:00:00Z",
                    "hasAttachment": True,
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
            "threadId": "thread-1",
            "messageId": ["message-1@example.net"],
            "references": ["root-message@example.net"],
            "subject": "Potentially unsafe message",
            "from": [{"name": "Sender", "email": "sender@example.net"}],
            "replyTo": [{"name": "Reply Desk", "email": "reply@example.net"}],
            "to": [
                {"name": "Alice", "email": "alice@example.test"},
                {"name": "Teammate", "email": "teammate@example.net"},
            ],
            "cc": [
                {"name": "Sales", "email": "sales@example.test"},
                {"name": "Observer", "email": "observer@example.org"},
            ],
            "receivedAt": "2026-08-12T10:00:00Z",
            "sentAt": "2026-08-12T09:59:00Z",
            "keywords": {},
            "textBody": [{"partId": "1"}],
            "bodyValues": {
                "1": {
                    "value": "Hello <script>alert('xss')</script> <b>not raw html</b>"
                }
            },
            "attachments": [
                {
                    "blobId": "original-blob",
                    "name": "invoice.pdf",
                    "type": "application/pdf",
                    "size": 1234,
                }
            ],
            "hasAttachment": True,
            "preview": "Hello",
        }

    def set_seen(self, email_id, *, seen):
        self.seen_updates.append((email_id, seen))

    def set_answered(self, email_id, *, answered=True):
        self.answered_updates.append((email_id, answered))

    def upload_blob(self, *, data, filename, content_type=None):
        self.uploads.append((data, filename, content_type))
        return {
            "blobId": f"uploaded-{len(self.uploads)}",
            "name": filename,
            "type": content_type or "application/octet-stream",
            "size": len(data),
        }

    def download_blob(self, *, blob_id, filename, content_type=None):
        self.downloads.append((blob_id, filename, content_type))
        return b"attachment-bytes", content_type or "application/octet-stream"

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
def test_message_plain_text_is_escaped_and_actions_are_available(authenticated_client):
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
    assert "Reply all" in html
    assert "Forward" in html
    assert "Download" in html


@pytest.mark.django_db
def test_attachment_download_is_resolved_from_message_metadata(authenticated_client):
    mail = FakeMailClient()
    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.get("/mail/messages/email-1/attachments/0/")

    assert response.status_code == 200
    assert response.content == b"attachment-bytes"
    assert response["Content-Type"] == "application/pdf"
    assert "attachment" in response["Content-Disposition"]
    assert "invoice.pdf" in response["Content-Disposition"]
    assert response["X-Content-Type-Options"] == "nosniff"
    assert mail.downloads == [("original-blob", "invoice.pdf", "application/pdf")]


@pytest.mark.django_db
def test_attachment_index_cannot_select_arbitrary_blob(authenticated_client):
    mail = FakeMailClient()
    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.get("/mail/messages/email-1/attachments/99/")

    assert response.status_code == 404
    assert mail.downloads == []


@pytest.mark.django_db
def test_mark_unread_updates_jmap_and_returns_to_inbox(authenticated_client):
    mail = FakeMailClient()
    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.post("/mail/messages/email-1/unread/")

    assert response.status_code == 302
    assert response.url == "/mail/inbox/"
    assert mail.seen_updates == [("email-1", False)]


@pytest.mark.django_db
def test_reply_prefills_reply_to_subject_and_quote(authenticated_client):
    mail = FakeMailClient()
    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.get("/mail/messages/email-1/reply/")

    assert response.status_code == 200
    form = response.context["form"]
    assert form.initial["identity_id"] == "identity-1"
    assert form.initial["to"] == "reply@example.net"
    assert form.initial["subject"] == "Re: Potentially unsafe message"
    assert "Reply Desk <reply@example.net> wrote:" in form.initial["body"]
    assert "> Hello <script>" in form.initial["body"]


@pytest.mark.django_db
def test_reply_all_excludes_own_identities_from_recipients(authenticated_client):
    mail = FakeMailClient()
    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.get("/mail/messages/email-1/reply-all/")

    assert response.status_code == 200
    form = response.context["form"]
    assert form.initial["to"] == "reply@example.net"
    assert form.initial["cc"] == "teammate@example.net, observer@example.org"
    assert "alice@example.test" not in form.initial["cc"]
    assert "sales@example.test" not in form.initial["cc"]


@pytest.mark.django_db
def test_reply_sends_thread_headers_and_marks_original_answered(authenticated_client):
    create_mail_domain(ready=True)
    mail = FakeMailClient()

    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.post(
            "/mail/messages/email-1/reply/",
            {
                "identity_id": "identity-1",
                "to": "reply@example.net",
                "cc": "",
                "bcc": "",
                "subject": "Re: Potentially unsafe message",
                "body": "Thanks.\n\n> Original",
            },
        )

    assert response.status_code == 302
    assert response.url == "/mail/inbox/"
    assert mail.sent["in_reply_to"] == ["message-1@example.net"]
    assert mail.sent["references"] == [
        "root-message@example.net",
        "message-1@example.net",
    ]
    assert mail.answered_updates == [("email-1", True)]


@pytest.mark.django_db
def test_forward_reuses_original_attachments_without_threading(authenticated_client):
    create_mail_domain(ready=True)
    mail = FakeMailClient()

    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.post(
            "/mail/messages/email-1/forward/",
            {
                "identity_id": "identity-1",
                "to": "bob@example.net",
                "cc": "",
                "bcc": "",
                "subject": "Fwd: Potentially unsafe message",
                "body": "Forwarded content",
            },
        )

    assert response.status_code == 302
    assert mail.sent["attachments"] == [
        {
            "blobId": "original-blob",
            "type": "application/pdf",
            "name": "invoice.pdf",
            "size": 1234,
        }
    ]
    assert mail.sent["in_reply_to"] == []
    assert mail.sent["references"] == []
    assert mail.answered_updates == []


@pytest.mark.django_db
def test_compose_uploads_attachment_then_sends_blob_reference(authenticated_client):
    create_mail_domain(ready=True)
    mail = FakeMailClient()
    attachment = SimpleUploadedFile("notes.txt", b"hello attachment", content_type="text/plain")

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
                "attachments": attachment,
            },
        )

    assert response.status_code == 302
    assert response.url == "/mail/inbox/"
    assert mail.uploads == [(b"hello attachment", "notes.txt", "text/plain")]
    assert mail.sent["identity_id"] == "identity-1"
    assert mail.sent["to"] == [{"email": "bob@example.net"}]
    assert mail.sent["bcc"] == [{"email": "audit@example.org"}]
    assert mail.sent["attachments"] == [
        {
            "blobId": "uploaded-1",
            "name": "notes.txt",
            "type": "text/plain",
            "size": 16,
        }
    ]


@pytest.mark.django_db
@override_settings(MAILFORGE_MAX_ATTACHMENT_MB=1, MAILFORGE_MAX_TOTAL_ATTACHMENT_MB=1)
def test_compose_rejects_oversized_attachment_before_upload(authenticated_client):
    create_mail_domain(ready=True)
    mail = FakeMailClient()
    attachment = SimpleUploadedFile(
        "too-large.bin",
        b"x" * (1024 * 1024 + 1),
        content_type="application/octet-stream",
    )

    with patch("mailforge.webmail_views._mail_client", return_value=mail):
        response = authenticated_client.post(
            "/mail/compose/",
            {
                "identity_id": "identity-1",
                "to": "bob@example.net",
                "cc": "",
                "bcc": "",
                "subject": "Blocked attachment",
                "body": "No upload should happen.",
                "attachments": attachment,
            },
        )

    assert response.status_code == 200
    assert b"exceeds the 1 MB per-file limit" in response.content
    assert mail.uploads == []
    assert mail.sent is None


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
