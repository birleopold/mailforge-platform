from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from integrations.stalwart.mail_jmap import JMAP_CORE, JMAP_MAIL, MailJMAPError
from mailforge.webmail_views import _account_context, _mail_client


PAGE_SIZE = 50
MAX_PAGE = 10000


@dataclass(frozen=True)
class EmailPage:
    emails: list[dict]
    total: int | None
    position: int
    page: int
    pages: int | None
    has_previous: bool
    has_next: bool


def _page_number(raw: str | None) -> int:
    try:
        value = int(raw or "1")
    except (TypeError, ValueError):
        return 1
    return min(max(value, 1), MAX_PAGE)


def _mailbox_choice(mailboxes, requested_id: str | None):
    if requested_id:
        selected = next(
            (item for item in mailboxes if str(item.get("id")) == str(requested_id)),
            None,
        )
        if selected is not None:
            return selected
    return next(
        (item for item in mailboxes if item.get("role") == "inbox"),
        mailboxes[0] if mailboxes else None,
    )


def _query_email_page(
    client,
    *,
    account_id: str,
    mailbox_id: str,
    page: int,
    text: str = "",
) -> EmailPage:
    position = (page - 1) * PAGE_SIZE
    filter_value = {"inMailbox": mailbox_id}
    if text:
        filter_value["text"] = text

    responses = client.call(
        [
            [
                "Email/query",
                {
                    "accountId": account_id,
                    "filter": filter_value,
                    "sort": [{"property": "receivedAt", "isAscending": False}],
                    "position": position,
                    "limit": PAGE_SIZE,
                    "calculateTotal": True,
                },
                "inbox-query",
            ]
        ],
        using=(JMAP_CORE, JMAP_MAIL),
    )
    query_data = responses[0][1]
    ids = [str(item) for item in query_data.get("ids", []) if item]
    actual_position = int(query_data.get("position") or position)
    total_value = query_data.get("total")
    total = int(total_value) if isinstance(total_value, int) and total_value >= 0 else None

    emails = []
    if ids:
        responses = client.call(
            [
                [
                    "Email/get",
                    {
                        "accountId": account_id,
                        "ids": ids,
                        "properties": [
                            "id",
                            "threadId",
                            "mailboxIds",
                            "keywords",
                            "size",
                            "receivedAt",
                            "sentAt",
                            "from",
                            "to",
                            "subject",
                            "preview",
                            "hasAttachment",
                        ],
                    },
                    "inbox-get",
                ]
            ],
            using=(JMAP_CORE, JMAP_MAIL),
        )
        by_id = {
            str(email["id"]): email
            for email in responses[0][1].get("list", [])
            if email.get("id")
        }
        emails = [by_id[email_id] for email_id in ids if email_id in by_id]

    actual_page = actual_position // PAGE_SIZE + 1
    pages = ceil(total / PAGE_SIZE) if total else (0 if total == 0 else None)
    has_previous = actual_position > 0
    if total is not None:
        has_next = actual_position + len(ids) < total
    else:
        has_next = len(ids) == PAGE_SIZE

    return EmailPage(
        emails=emails,
        total=total,
        position=actual_position,
        page=actual_page,
        pages=pages,
        has_previous=has_previous,
        has_next=has_next,
    )


@login_required
def webmail_inbox(request):
    client = _mail_client(request)
    if client is None:
        return redirect("webmail-home")

    try:
        account_id, account = _account_context(client)
        mailboxes = client.list_mailboxes(account_id)
    except MailJMAPError:
        return redirect("webmail-home")

    selected = _mailbox_choice(mailboxes, request.GET.get("mailbox"))
    if selected is None:
        return render(
            request,
            "webmail/inbox_paginated.html",
            {
                "mail_account": account,
                "mailboxes": [],
                "emails": [],
                "selected_mailbox": None,
                "search_text": "",
                "page": 1,
                "total": 0,
            },
        )

    search_text = (request.GET.get("q") or "").strip()[:500]
    requested_page = _page_number(request.GET.get("page"))
    try:
        result = _query_email_page(
            client,
            account_id=account_id,
            mailbox_id=str(selected["id"]),
            page=requested_page,
            text=search_text,
        )
    except MailJMAPError:
        return redirect("webmail-home")

    return render(
        request,
        "webmail/inbox_paginated.html",
        {
            "mail_account": account,
            "mailboxes": mailboxes,
            "emails": result.emails,
            "selected_mailbox": selected,
            "selected_mailbox_id": str(selected["id"]),
            "search_text": search_text,
            "page": result.page,
            "pages": result.pages,
            "total": result.total,
            "has_previous": result.has_previous,
            "has_next": result.has_next,
            "previous_page": max(result.page - 1, 1),
            "next_page": result.page + 1,
            "page_size": PAGE_SIZE,
        },
    )
