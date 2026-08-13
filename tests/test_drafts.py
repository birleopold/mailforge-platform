from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.domains.models import Domain
from apps.tenants.models import Tenant
from integrations.stalwart.mail_jmap import JMAP_CORE, JMAP_MAIL, JMAP_SUBMISSION
from mailforge.drafts import (
    DraftError,
    discard_draft,
    get_saved_draft,
    save_draft,
    submit_saved_draft,
)


User = get_user_model()


class FakeDraftClient:
    def __init__(self):
        self.calls = []
        self.uploads = []
        self.answered = []
        self.drafts = {
            "draft-existing": {
                "id": "draft-existing",
                "mailboxIds": {"drafts": True},
                "keywords": {"$draft": True, "$seen": True},
                "from": [{"name": "User", "email": "user@example.com"}],
                "to": [{"email": "friend@example.net"}],
                "cc": [],
                "bcc": [],
                "subject": "Existing draft",
                "bodyValues": {"text": {"value": "Existing body"}},
                "textBody": [{"partId": "text"}],
                "htmlBody": [],
                "attachments": [
                    {
                        "blobId": "blob-old",
                        "type": "application/pdf",
                        "name": "old.pdf",
                        "size": 120,
                    }
                ],
                "inReplyTo": ["msg-parent@example.net"],
                "references": ["msg-root@example.net", "msg-parent@example.net"],
            }
        }

    def session(self):
        return {
            "accounts": {"account-1": {"name": "Mailbox"}},
            "primaryAccounts": {JMAP_MAIL: "account-1"},
        }

    def primary_mail_account_id(self):
        return "account-1"

    def list_mailboxes(self, account_id):
        assert account_id == "account-1"
        return [
            {"id": "drafts", "name": "Drafts", "role": "drafts"},
            {"id": "sent", "name": "Sent", "role": "sent"},
            {"id": "inbox", "name": "Inbox", "role": "inbox"},
        ]

    def list_identities(self):
        return [
            {
                "id": "identity-1",
                "name": "User",
                "email": "user@example.com",
                "textSignature": "Regards,\nUser",
                "mayDelete": False,
            }
        ]

    def get_email(self, account_id, email_id):
        assert account_id == "account-1"
        if email_id in self.drafts:
            return self.drafts[email_id]
        raise RuntimeError("missing email")

    def upload(self, content, *, content_type, name):
        self.uploads.append((content, content_type, name))
        return {
            "blobId": f"blob-{len(self.uploads)}",
            "type": content_type,
            "name": name,
            "size": len(content),
        }

    def mark_answered(self, account_id, email_id):
        self.answered.append((account_id, email_id))

    def call(self, method_calls, *, using=None):
        self.calls.append((method_calls, tuple(using or ())))
        method, arguments, call_id = method_calls[0]
        if method == "Email/set" and "create" in arguments:
            payload = arguments["create"]["mailforge-draft"]
            self.drafts["draft-new"] = {
                "id": "draft-new",
                **payload,
                "textBody": [{"partId": "body"}],
                "htmlBody": [],
                "bodyValues": payload["bodyValues"],
            }
            return [
                [
                    "Email/set",
                    {"created": {"mailforge-draft": {"id": "draft-new"}}},
                    call_id,
                ]
            ]
        if method == "Email/set" and "update" in arguments:
            email_id, payload = next(iter(arguments["update"].items()))
            existing = dict(self.drafts[email_id])
            existing.update(payload)
            existing["textBody"] = [{"partId": "body"}]
            self.drafts[email_id] = existing
            return [["Email/set", {"updated": {email_id: None}}, call_id]]
        if method == "Email/set" and "destroy" in arguments:
            email_id = arguments["destroy"][0]
            self.drafts.pop(email_id, None)
            return [["Email/set", {"destroyed": [email_id]}, call_id]]
        if method == "EmailSubmission/set":
            return [
                [
                    "EmailSubmission/set",
                    {"created": {"submission": {"id": "submission-1"}}},
                    call_id,
                ]
            ]
        raise AssertionError(method)


def _last_call(client, method):
    for method_calls, using in reversed(client.calls):
        if method_calls[0][0] == method:
            return method_calls[0], using
    raise AssertionError(f"No {method} call")


def make_ready_domain():
    tenant = Tenant.objects.create(name="Draft Tenant", slug="draft-tenant")
    return Domain.objects.create(
        tenant=tenant,
        name="example.com",
        status=Domain.Status.ACTIVE,
        verified_at=timezone.now(),
        backend_identifier="domain-1",
        sending_enabled=True,
    )


def test_new_draft_is_created_in_drafts_with_draft_keyword_and_no_automatic_signature():
    client = FakeDraftClient()

    result = save_draft(
        client,
        account_id="account-1",
        identity_id="identity-1",
        to=[],
        subject="Partial",
        body="Work in progress",
    )

    assert result.created is True
    assert result.draft_id == "draft-new"
    call, using = _last_call(client, "Email/set")
    payload = call[1]["create"]["mailforge-draft"]
    assert using == (JMAP_CORE, JMAP_MAIL)
    assert payload["mailboxIds"] == {"drafts": True}
    assert payload["keywords"] == {"$draft": True, "$seen": True}
    assert payload["to"] == []
    assert payload["bodyValues"]["body"]["value"] == "Work in progress"
    assert "Regards" not in payload["bodyValues"]["body"]["value"]


def test_updating_draft_reuses_same_email_and_preserves_existing_attachments_and_thread_headers():
    client = FakeDraftClient()

    result = save_draft(
        client,
        account_id="account-1",
        identity_id="identity-1",
        to=[{"email": "changed@example.net"}],
        subject="Changed",
        body="Changed body",
        draft_id="draft-existing",
        attachments=[
            {
                "blobId": "blob-new",
                "type": "text/plain",
                "name": "new.txt",
                "size": 20,
            }
        ],
    )

    assert result.created is False
    assert result.draft_id == "draft-existing"
    call, _ = _last_call(client, "Email/set")
    update = call[1]["update"]["draft-existing"]
    assert {item["blobId"] for item in update["attachments"]} == {"blob-old", "blob-new"}
    assert update["inReplyTo"] == ["msg-parent@example.net"]
    assert update["references"] == ["msg-root@example.net", "msg-parent@example.net"]


def test_signature_is_added_once_when_final_draft_is_prepared_for_submission():
    client = FakeDraftClient()

    first = save_draft(
        client,
        account_id="account-1",
        identity_id="identity-1",
        to=[{"email": "friend@example.net"}],
        subject="Ready",
        body="Hello",
        draft_id="draft-existing",
        apply_signature=True,
    )
    assert first.draft_id == "draft-existing"
    body = client.drafts["draft-existing"]["bodyValues"]["body"]["value"]
    assert body == "Hello\n\nRegards,\nUser"

    save_draft(
        client,
        account_id="account-1",
        identity_id="identity-1",
        to=[{"email": "friend@example.net"}],
        subject="Ready",
        body=body,
        draft_id="draft-existing",
        apply_signature=True,
    )
    body_again = client.drafts["draft-existing"]["bodyValues"]["body"]["value"]
    assert body_again.count("Regards,") == 1


def test_submit_saved_draft_uses_existing_email_and_moves_success_to_sent():
    client = FakeDraftClient()

    created = submit_saved_draft(
        client,
        account_id="account-1",
        draft_id="draft-existing",
        identity_id="identity-1",
    )

    assert created["id"] == "submission-1"
    call, using = _last_call(client, "EmailSubmission/set")
    assert using == (JMAP_CORE, JMAP_MAIL, JMAP_SUBMISSION)
    assert call[1]["create"]["submission"] == {
        "identityId": "identity-1",
        "emailId": "draft-existing",
    }
    assert call[1]["onSuccessUpdateEmail"] == {
        "#submission": {
            "mailboxIds/sent": True,
            "keywords/$draft": None,
        }
    }


def test_non_draft_message_is_not_editable_or_discardable():
    client = FakeDraftClient()
    client.drafts["not-draft"] = {
        "id": "not-draft",
        "mailboxIds": {"inbox": True},
        "keywords": {"$seen": True},
    }

    with pytest.raises(DraftError):
        get_saved_draft(client, account_id="account-1", draft_id="not-draft")
    with pytest.raises(DraftError):
        discard_draft(client, account_id="account-1", draft_id="not-draft")


def test_discard_draft_destroys_only_valid_draft():
    client = FakeDraftClient()

    discard_draft(client, account_id="account-1", draft_id="draft-existing")

    call, using = _last_call(client, "Email/set")
    assert using == (JMAP_CORE, JMAP_MAIL)
    assert call[1] == {"accountId": "account-1", "destroy": ["draft-existing"]}


@pytest.mark.django_db
def test_edit_draft_view_populates_existing_fields_and_attachments(client):
    user = User.objects.create_user(
        username="draft-edit-user",
        email="user@example.com",
        password="draft-edit-password-123",
    )
    client.force_login(user)
    jmap = FakeDraftClient()

    with patch("mailforge.draft_views._mail_client", return_value=jmap):
        response = client.get(
            reverse("webmail-edit-draft", kwargs={"draft_id": "draft-existing"})
        )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Edit draft" in content
    assert "Existing draft" in content
    assert "Existing body" in content
    assert "old.pdf" in content
    assert "Save draft" in content
    assert "drafts.js" in content


@pytest.mark.django_db
def test_manual_save_allows_recipient_less_draft(client):
    user = User.objects.create_user(
        username="draft-save-user",
        email="user@example.com",
        password="draft-save-password-123",
    )
    client.force_login(user)
    jmap = FakeDraftClient()

    with patch("mailforge.draft_views._mail_client", return_value=jmap):
        response = client.post(
            reverse("webmail-draft-save"),
            {
                "identity_id": "identity-1",
                "to": "",
                "cc": "",
                "bcc": "",
                "subject": "Partial subject",
                "body": "Partial body",
                "draft_id": "",
                "compose_mode": "",
                "source_id": "",
            },
        )

    assert response.status_code == 302
    assert response.url == reverse("webmail-edit-draft", kwargs={"draft_id": "draft-new"})


@pytest.mark.django_db
def test_autosave_returns_stable_draft_id_and_updates_same_draft(client):
    user = User.objects.create_user(
        username="draft-auto-user",
        email="user@example.com",
        password="draft-auto-password-123",
    )
    client.force_login(user)
    jmap = FakeDraftClient()

    with patch("mailforge.draft_views._mail_client", return_value=jmap):
        first = client.post(
            reverse("webmail-draft-autosave"),
            {
                "identity_id": "identity-1",
                "to": "",
                "cc": "",
                "bcc": "",
                "subject": "Autosave",
                "body": "Version one",
                "draft_id": "",
                "compose_mode": "",
                "source_id": "",
            },
        )
        second = client.post(
            reverse("webmail-draft-autosave"),
            {
                "identity_id": "identity-1",
                "to": "",
                "cc": "",
                "bcc": "",
                "subject": "Autosave",
                "body": "Version two",
                "draft_id": first.json()["draft_id"],
                "compose_mode": "",
                "source_id": "",
            },
        )

    assert first.status_code == 200
    assert first.json()["created"] is True
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["draft_id"] == "draft-new"
    assert jmap.drafts["draft-new"]["bodyValues"]["body"]["value"] == "Version two"


@pytest.mark.django_db
def test_send_draft_requires_recipient_and_does_not_submit_invalid_partial_draft(client):
    user = User.objects.create_user(
        username="draft-recipient-user",
        email="user@example.com",
        password="draft-recipient-password-123",
    )
    client.force_login(user)
    jmap = FakeDraftClient()

    with patch("mailforge.draft_views._mail_client", return_value=jmap):
        response = client.post(
            reverse("webmail-draft-send"),
            {
                "identity_id": "identity-1",
                "to": "",
                "cc": "",
                "bcc": "",
                "subject": "No recipient",
                "body": "Still a draft",
                "draft_id": "",
                "compose_mode": "",
                "source_id": "",
            },
        )

    assert response.status_code == 200
    assert b"Enter at least one recipient before sending" in response.content
    assert not any(calls[0][0] == "EmailSubmission/set" for calls, _ in jmap.calls)


@pytest.mark.django_db
def test_send_saved_draft_checks_domain_readiness_then_submits_existing_email(client):
    user = User.objects.create_user(
        username="draft-send-user",
        email="user@example.com",
        password="draft-send-password-123",
    )
    client.force_login(user)
    make_ready_domain()
    jmap = FakeDraftClient()

    with patch("mailforge.draft_views._mail_client", return_value=jmap):
        response = client.post(
            reverse("webmail-draft-send"),
            {
                "identity_id": "identity-1",
                "to": "friend@example.net",
                "cc": "",
                "bcc": "",
                "subject": "Ready to send",
                "body": "Hello",
                "draft_id": "draft-existing",
                "compose_mode": "",
                "source_id": "",
            },
        )

    assert response.status_code == 302
    assert response.url == reverse("webmail-inbox")
    submission, _ = _last_call(jmap, "EmailSubmission/set")
    assert submission[1]["create"]["submission"]["emailId"] == "draft-existing"
    assert jmap.drafts["draft-existing"]["bodyValues"]["body"]["value"].endswith(
        "Regards,\nUser"
    )
