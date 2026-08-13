from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from integrations.stalwart.mail_jmap import JMAP_CORE, JMAP_MAIL
from mailforge.message_actions import (
    MessageActionError,
    archive_message,
    move_message,
    permanently_delete_message,
    spam_message,
    trash_message,
)


User = get_user_model()


class FakeMessageActionClient:
    def __init__(self, *, in_trash=False, include_junk=True, not_updated=None, not_destroyed=None):
        self.in_trash = in_trash
        self.include_junk = include_junk
        self.not_updated = not_updated
        self.not_destroyed = not_destroyed
        self.calls = []

    def session(self):
        return {
            "accounts": {"account-1": {"name": "Mailbox"}},
            "primaryAccounts": {JMAP_MAIL: "account-1"},
        }

    def primary_mail_account_id(self):
        return "account-1"

    def list_mailboxes(self, account_id):
        assert account_id == "account-1"
        mailboxes = [
            {"id": "inbox", "name": "Inbox", "role": "inbox"},
            {"id": "archive", "name": "Archive", "role": "archive"},
            {"id": "trash", "name": "Trash", "role": "trash"},
            {"id": "projects", "name": "Projects", "role": None},
        ]
        if self.include_junk:
            mailboxes.append({"id": "junk", "name": "Junk", "role": "junk"})
        return mailboxes

    def get_email(self, account_id, email_id):
        assert account_id == "account-1"
        return {
            "id": email_id,
            "subject": "Action subject",
            "mailboxIds": {"trash": True} if self.in_trash else {"inbox": True},
        }

    def call(self, method_calls, *, using=None):
        self.calls.append((method_calls, tuple(using or ())))
        method, arguments, call_id = method_calls[0]
        assert method == "Email/set"
        assert tuple(using or ()) == (JMAP_CORE, JMAP_MAIL)
        if "destroy" in arguments:
            email_id = arguments["destroy"][0]
            data = {"destroyed": [] if self.not_destroyed else [email_id]}
            if self.not_destroyed:
                data["notDestroyed"] = {email_id: self.not_destroyed}
        else:
            email_id = next(iter(arguments["update"]))
            data = {"updated": {email_id: None}}
            if self.not_updated:
                data["notUpdated"] = {email_id: self.not_updated}
        return [["Email/set", data, call_id]]


def _last_email_set_arguments(client):
    method_calls, using = client.calls[-1]
    assert using == (JMAP_CORE, JMAP_MAIL)
    return method_calls[0][1]


def test_move_message_replaces_mailbox_membership_with_valid_target():
    client = FakeMessageActionClient()

    target = move_message(
        client,
        account_id="account-1",
        email_id="email-1",
        mailbox_id="projects",
    )

    assert target.id == "projects"
    assert _last_email_set_arguments(client) == {
        "accountId": "account-1",
        "update": {"email-1": {"mailboxIds": {"projects": True}}},
    }


def test_move_message_rejects_unknown_mailbox_before_email_set():
    client = FakeMessageActionClient()

    with pytest.raises(MessageActionError):
        move_message(
            client,
            account_id="account-1",
            email_id="email-1",
            mailbox_id="attacker-controlled-id",
        )

    assert client.calls == []


def test_archive_and_trash_resolve_mailboxes_by_jmap_role():
    client = FakeMessageActionClient()

    archive_message(client, account_id="account-1", email_id="email-1")
    archive_args = _last_email_set_arguments(client)
    trash_message(client, account_id="account-1", email_id="email-2")
    trash_args = _last_email_set_arguments(client)

    assert archive_args["update"] == {"email-1": {"mailboxIds": {"archive": True}}}
    assert trash_args["update"] == {"email-2": {"mailboxIds": {"trash": True}}}


def test_spam_sets_junk_keywords_and_moves_to_junk_when_available():
    client = FakeMessageActionClient(include_junk=True)

    target = spam_message(client, account_id="account-1", email_id="email-1")

    assert target is not None and target.id == "junk"
    assert _last_email_set_arguments(client)["update"] == {
        "email-1": {
            "keywords/$junk": True,
            "keywords/$notjunk": None,
            "mailboxIds": {"junk": True},
        }
    }


def test_spam_can_set_keyword_without_junk_mailbox():
    client = FakeMessageActionClient(include_junk=False)

    target = spam_message(client, account_id="account-1", email_id="email-1")

    assert target is None
    assert _last_email_set_arguments(client)["update"] == {
        "email-1": {
            "keywords/$junk": True,
            "keywords/$notjunk": None,
        }
    }


def test_permanent_delete_is_rejected_until_message_is_in_trash():
    client = FakeMessageActionClient(in_trash=False)

    with pytest.raises(MessageActionError):
        permanently_delete_message(client, account_id="account-1", email_id="email-1")

    assert client.calls == []


def test_permanent_delete_destroys_message_only_after_trash_check():
    client = FakeMessageActionClient(in_trash=True)

    permanently_delete_message(client, account_id="account-1", email_id="email-1")

    assert _last_email_set_arguments(client) == {
        "accountId": "account-1",
        "destroy": ["email-1"],
    }


def test_email_set_errors_are_raised_to_caller():
    client = FakeMessageActionClient(not_updated={"type": "forbidden"})
    with pytest.raises(MessageActionError):
        archive_message(client, account_id="account-1", email_id="email-1")

    client = FakeMessageActionClient(
        in_trash=True,
        not_destroyed={"type": "forbidden"},
    )
    with pytest.raises(MessageActionError):
        permanently_delete_message(client, account_id="account-1", email_id="email-1")


@pytest.mark.django_db
def test_message_actions_screen_lists_mailboxes_and_hides_permanent_delete_outside_trash(client):
    user = User.objects.create_user(
        username="message-actions-user",
        email="user@example.com",
        password="message-actions-password-123",
    )
    client.force_login(user)
    jmap = FakeMessageActionClient(in_trash=False)

    with patch("mailforge.message_action_views._mail_client", return_value=jmap):
        response = client.get(
            reverse("webmail-message-actions", kwargs={"email_id": "email-1"})
        )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Projects" in content
    assert "Move message" in content
    assert "Move to Trash" in content
    assert "Move the message to Trash before permanent deletion is allowed" in content
    assert ">Permanently delete<" not in content


@pytest.mark.django_db
def test_message_actions_screen_allows_permanent_delete_when_already_in_trash(client):
    user = User.objects.create_user(
        username="trash-actions-user",
        email="trash@example.com",
        password="trash-actions-password-123",
    )
    client.force_login(user)
    jmap = FakeMessageActionClient(in_trash=True)

    with patch("mailforge.message_action_views._mail_client", return_value=jmap):
        response = client.get(
            reverse("webmail-message-actions", kwargs={"email_id": "email-1"})
        )

    assert response.status_code == 200
    assert b"Permanently delete" in response.content


@pytest.mark.django_db
def test_permanent_delete_post_requires_confirmation_before_jmap_destroy(client):
    user = User.objects.create_user(
        username="delete-confirm-user",
        email="delete@example.com",
        password="delete-confirm-password-123",
    )
    client.force_login(user)
    jmap = FakeMessageActionClient(in_trash=True)

    with patch("mailforge.message_action_views._mail_client", return_value=jmap):
        response = client.post(
            reverse("webmail-delete-message", kwargs={"email_id": "email-1"}),
            {},
        )

    assert response.status_code == 302
    assert jmap.calls == []


@pytest.mark.django_db
def test_archive_route_is_post_only(client):
    user = User.objects.create_user(
        username="post-only-user",
        email="post-only@example.com",
        password="post-only-password-123",
    )
    client.force_login(user)

    response = client.get(
        reverse("webmail-archive-message", kwargs={"email_id": "email-1"})
    )

    assert response.status_code == 405
