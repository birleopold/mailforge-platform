from __future__ import annotations

from dataclasses import dataclass

from integrations.stalwart.mail_jmap import JMAP_CORE, JMAP_MAIL, MailJMAPError


class MessageActionError(RuntimeError):
    pass


@dataclass(frozen=True)
class MailboxTarget:
    id: str
    name: str
    role: str | None


def mailbox_targets(client, *, account_id: str) -> list[MailboxTarget]:
    return [
        MailboxTarget(
            id=str(mailbox["id"]),
            name=str(mailbox.get("name") or mailbox["id"]),
            role=mailbox.get("role"),
        )
        for mailbox in client.list_mailboxes(account_id)
        if mailbox.get("id")
    ]


def _mailbox_for_role(mailboxes: list[MailboxTarget], role: str) -> MailboxTarget | None:
    return next((mailbox for mailbox in mailboxes if mailbox.role == role), None)


def _mailbox_for_id(mailboxes: list[MailboxTarget], mailbox_id: str) -> MailboxTarget | None:
    return next((mailbox for mailbox in mailboxes if mailbox.id == mailbox_id), None)


def _email_set(client, *, account_id: str, update=None, destroy=None):
    arguments = {"accountId": account_id}
    if update:
        arguments["update"] = update
    if destroy:
        arguments["destroy"] = destroy
    responses = client.call(
        [["Email/set", arguments, "message-action"]],
        using=(JMAP_CORE, JMAP_MAIL),
    )
    data = responses[0][1]
    if update:
        for email_id in update:
            error = (data.get("notUpdated") or {}).get(email_id)
            if error:
                raise MessageActionError(f"Message update failed: {error}")
    if destroy:
        for email_id in destroy:
            error = (data.get("notDestroyed") or {}).get(email_id)
            if error:
                raise MessageActionError(f"Message deletion failed: {error}")
            if email_id not in set(data.get("destroyed") or []):
                raise MessageActionError("The mail server did not confirm permanent deletion.")
    return data


def move_message(client, *, account_id: str, email_id: str, mailbox_id: str) -> MailboxTarget:
    mailboxes = mailbox_targets(client, account_id=account_id)
    target = _mailbox_for_id(mailboxes, str(mailbox_id))
    if target is None:
        raise MessageActionError("The selected mailbox is not available in this mail account.")
    _email_set(
        client,
        account_id=account_id,
        update={str(email_id): {"mailboxIds": {target.id: True}}},
    )
    return target


def archive_message(client, *, account_id: str, email_id: str) -> MailboxTarget:
    mailboxes = mailbox_targets(client, account_id=account_id)
    target = _mailbox_for_role(mailboxes, "archive")
    if target is None:
        raise MessageActionError("This mail account does not have an Archive mailbox.")
    _email_set(
        client,
        account_id=account_id,
        update={str(email_id): {"mailboxIds": {target.id: True}}},
    )
    return target


def trash_message(client, *, account_id: str, email_id: str) -> MailboxTarget:
    mailboxes = mailbox_targets(client, account_id=account_id)
    target = _mailbox_for_role(mailboxes, "trash")
    if target is None:
        raise MessageActionError("This mail account does not have a Trash mailbox.")
    _email_set(
        client,
        account_id=account_id,
        update={str(email_id): {"mailboxIds": {target.id: True}}},
    )
    return target


def spam_message(client, *, account_id: str, email_id: str) -> MailboxTarget | None:
    mailboxes = mailbox_targets(client, account_id=account_id)
    junk = _mailbox_for_role(mailboxes, "junk")
    patch = {
        "keywords/$junk": True,
        "keywords/$notjunk": None,
    }
    if junk is not None:
        patch["mailboxIds"] = {junk.id: True}
    _email_set(
        client,
        account_id=account_id,
        update={str(email_id): patch},
    )
    return junk


def permanently_delete_message(client, *, account_id: str, email_id: str) -> None:
    try:
        email = client.get_email(account_id, str(email_id))
    except MailJMAPError as exc:
        raise MessageActionError("The message could not be read before deletion.") from exc

    trash = _mailbox_for_role(mailbox_targets(client, account_id=account_id), "trash")
    if trash is None:
        raise MessageActionError("This mail account does not have a Trash mailbox.")
    if trash.id not in (email.get("mailboxIds") or {}):
        raise MessageActionError("Move the message to Trash before permanently deleting it.")

    _email_set(
        client,
        account_id=account_id,
        destroy=[str(email_id)],
    )
