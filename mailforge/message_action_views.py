from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from integrations.stalwart.mail_jmap import MailJMAPError
from mailforge.message_actions import (
    MessageActionError,
    archive_message,
    mailbox_targets,
    move_message,
    permanently_delete_message,
    spam_message,
    trash_message,
)
from mailforge.webmail_views import _account_context, _mail_client


def _client_and_account(request):
    client = _mail_client(request)
    if client is None:
        return None, None
    try:
        account_id, _ = _account_context(client)
    except MailJMAPError:
        return None, None
    return client, account_id


def _action_error(request, exc):
    messages.error(request, str(exc))
    return redirect("webmail-inbox")


@login_required
def webmail_message_actions(request, email_id):
    client, account_id = _client_and_account(request)
    if client is None:
        return redirect("webmail-home")
    try:
        email = client.get_email(account_id, str(email_id))
        targets = mailbox_targets(client, account_id=account_id)
    except MailJMAPError:
        raise Http404 from None

    current_ids = set((email.get("mailboxIds") or {}).keys())
    trash = next((mailbox for mailbox in targets if mailbox.role == "trash"), None)
    return render(
        request,
        "webmail/message_actions.html",
        {
            "email": email,
            "targets": targets,
            "current_ids": current_ids,
            "in_trash": bool(trash and trash.id in current_ids),
        },
    )


@login_required
@require_POST
def webmail_move_message(request, email_id):
    client, account_id = _client_and_account(request)
    if client is None:
        return redirect("webmail-home")
    mailbox_id = (request.POST.get("mailbox_id") or "").strip()
    if not mailbox_id:
        messages.error(request, "Choose a destination mailbox.")
        return redirect("webmail-message-actions", email_id=email_id)
    try:
        target = move_message(
            client,
            account_id=account_id,
            email_id=email_id,
            mailbox_id=mailbox_id,
        )
    except (MessageActionError, MailJMAPError) as exc:
        return _action_error(request, exc)
    messages.success(request, f"Message moved to {target.name}.")
    return redirect("webmail-inbox")


@login_required
@require_POST
def webmail_archive_message(request, email_id):
    client, account_id = _client_and_account(request)
    if client is None:
        return redirect("webmail-home")
    try:
        archive_message(client, account_id=account_id, email_id=email_id)
    except (MessageActionError, MailJMAPError) as exc:
        return _action_error(request, exc)
    messages.success(request, "Message archived.")
    return redirect("webmail-inbox")


@login_required
@require_POST
def webmail_trash_message(request, email_id):
    client, account_id = _client_and_account(request)
    if client is None:
        return redirect("webmail-home")
    try:
        trash_message(client, account_id=account_id, email_id=email_id)
    except (MessageActionError, MailJMAPError) as exc:
        return _action_error(request, exc)
    messages.success(request, "Message moved to Trash.")
    return redirect("webmail-inbox")


@login_required
@require_POST
def webmail_spam_message(request, email_id):
    client, account_id = _client_and_account(request)
    if client is None:
        return redirect("webmail-home")
    try:
        spam_message(client, account_id=account_id, email_id=email_id)
    except (MessageActionError, MailJMAPError) as exc:
        return _action_error(request, exc)
    messages.success(request, "Message marked as spam.")
    return redirect("webmail-inbox")


@login_required
@require_POST
def webmail_permanently_delete_message(request, email_id):
    client, account_id = _client_and_account(request)
    if client is None:
        return redirect("webmail-home")
    if request.POST.get("confirm") != "delete":
        messages.error(request, "Permanent deletion confirmation was missing.")
        return redirect("webmail-message-actions", email_id=email_id)
    try:
        permanently_delete_message(client, account_id=account_id, email_id=email_id)
    except (MessageActionError, MailJMAPError) as exc:
        return _action_error(request, exc)
    messages.success(request, "Message permanently deleted.")
    return redirect("webmail-inbox")
