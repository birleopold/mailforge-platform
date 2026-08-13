from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render

from integrations.stalwart.mail_jmap import JMAP_CORE, JMAP_MAIL, MailJMAPError
from mailforge.webmail_views import _account_context, _mail_client, _plain_text_body


THREAD_EMAIL_PROPERTIES = [
    "id",
    "blobId",
    "threadId",
    "mailboxIds",
    "keywords",
    "size",
    "receivedAt",
    "sentAt",
    "messageId",
    "inReplyTo",
    "references",
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
]


def _thread_email_ids(client, *, account_id: str, thread_id: str) -> list[str]:
    responses = client.call(
        [
            [
                "Thread/get",
                {
                    "accountId": account_id,
                    "ids": [thread_id],
                    "properties": ["id", "emailIds"],
                },
                "thread-get",
            ]
        ],
        using=(JMAP_CORE, JMAP_MAIL),
    )
    items = responses[0][1].get("list", [])
    if len(items) != 1:
        raise MailJMAPError("Conversation not found.")
    return [str(item) for item in items[0].get("emailIds", []) if item]


def _thread_emails(client, *, account_id: str, email_ids: list[str]) -> list[dict]:
    if not email_ids:
        return []

    by_id = {}
    # Keep batches below common maxObjectsInGet values while preserving the
    # server-defined chronological Thread/emailIds order in the final result.
    for offset in range(0, min(len(email_ids), 200), 50):
        batch = email_ids[offset : offset + 50]
        responses = client.call(
            [
                [
                    "Email/get",
                    {
                        "accountId": account_id,
                        "ids": batch,
                        "properties": THREAD_EMAIL_PROPERTIES,
                        "fetchTextBodyValues": True,
                        "fetchHTMLBodyValues": True,
                        "maxBodyValueBytes": 1048576,
                    },
                    f"thread-emails-{offset}",
                ]
            ],
            using=(JMAP_CORE, JMAP_MAIL),
        )
        for email in responses[0][1].get("list", []):
            if email.get("id"):
                by_id[str(email["id"])] = email

    return [by_id[email_id] for email_id in email_ids[:200] if email_id in by_id]


@login_required
def webmail_thread(request, thread_id):
    client = _mail_client(request)
    if client is None:
        return redirect("webmail-home")

    try:
        account_id, account = _account_context(client)
        email_ids = _thread_email_ids(client, account_id=account_id, thread_id=thread_id)
        emails = _thread_emails(client, account_id=account_id, email_ids=email_ids)
    except MailJMAPError:
        raise Http404 from None

    if not emails:
        raise Http404

    truncated = len(email_ids) > len(emails)
    conversation = [
        {
            "email": email,
            "plain_text_body": _plain_text_body(email) or email.get("preview", ""),
        }
        for email in emails
    ]
    if truncated:
        messages.warning(
            request,
            "This conversation is very large. MailForge is showing the first 200 messages.",
        )

    return render(
        request,
        "webmail/thread.html",
        {
            "mail_account": account,
            "thread_id": thread_id,
            "conversation": conversation,
            "message_count": len(email_ids),
            "truncated": truncated,
            "subject": emails[-1].get("subject") or "(no subject)",
        },
    )
