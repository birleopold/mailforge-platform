from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from integrations.stalwart.mail_jmap import JMAP_CORE, JMAP_MAIL
from mailforge.inbox_views import MAX_PAGE, PAGE_SIZE, _page_number, _query_email_page


User = get_user_model()


class FakeInboxClient:
    def __init__(self, *, total=125):
        self.total = total
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
        return [
            {
                "id": "inbox",
                "name": "Inbox",
                "role": "inbox",
                "unreadEmails": 7,
            },
            {
                "id": "drafts",
                "name": "Drafts",
                "role": "drafts",
                "unreadEmails": 0,
            },
        ]

    def call(self, method_calls, *, using=None):
        self.calls.append((method_calls, tuple(using or ())))
        method, arguments, call_id = method_calls[0]
        assert tuple(using or ()) == (JMAP_CORE, JMAP_MAIL)
        if method == "Email/query":
            position = arguments["position"]
            remaining = max(self.total - position, 0)
            count = min(arguments["limit"], remaining)
            ids = [f"email-{position + index}" for index in range(count)]
            return [
                [
                    "Email/query",
                    {
                        "ids": ids,
                        "position": position,
                        "total": self.total,
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
                        "threadId": f"thread-{email_id}",
                        "mailboxIds": {"inbox": True},
                        "keywords": {"$seen": True},
                        "receivedAt": "2026-08-13T08:00:00Z",
                        "from": [{"name": "Sender", "email": "sender@example.net"}],
                        "to": [{"email": "user@example.com"}],
                        "subject": f"Subject {email_id}",
                        "preview": f"Preview {email_id}",
                        "hasAttachment": False,
                        "size": 100,
                    }
                )
            return [["Email/get", {"list": emails}, call_id]]
        raise AssertionError(method)


def _query_calls(client):
    return [
        calls[0]
        for calls, _ in client.calls
        if calls[0][0] == "Email/query"
    ]


def test_page_number_is_bounded_and_forgiving():
    assert _page_number(None) == 1
    assert _page_number("bad") == 1
    assert _page_number("-5") == 1
    assert _page_number(str(MAX_PAGE + 100)) == MAX_PAGE


def test_second_page_uses_jmap_position_and_restores_query_order():
    client = FakeInboxClient(total=125)

    result = _query_email_page(
        client,
        account_id="account-1",
        mailbox_id="inbox",
        page=2,
    )

    query = _query_calls(client)[0]
    assert query[1]["position"] == PAGE_SIZE
    assert query[1]["limit"] == PAGE_SIZE
    assert query[1]["calculateTotal"] is True
    assert result.page == 2
    assert result.pages == 3
    assert result.total == 125
    assert result.has_previous is True
    assert result.has_next is True
    assert result.emails[0]["id"] == "email-50"
    assert result.emails[-1]["id"] == "email-99"


def test_search_filter_is_sent_to_jmap_query():
    client = FakeInboxClient(total=10)

    _query_email_page(
        client,
        account_id="account-1",
        mailbox_id="drafts",
        page=1,
        text="quarterly report",
    )

    query = _query_calls(client)[0]
    assert query[1]["filter"] == {
        "inMailbox": "drafts",
        "text": "quarterly report",
    }


def test_out_of_range_page_requeries_last_real_page():
    client = FakeInboxClient(total=125)

    result = _query_email_page(
        client,
        account_id="account-1",
        mailbox_id="inbox",
        page=9,
    )

    queries = _query_calls(client)
    assert [query[1]["position"] for query in queries] == [400, 100]
    assert result.page == 3
    assert result.pages == 3
    assert result.has_next is False
    assert result.emails[0]["id"] == "email-100"
    assert result.emails[-1]["id"] == "email-124"


def test_empty_mailbox_normalizes_to_page_one_without_navigation():
    client = FakeInboxClient(total=0)

    result = _query_email_page(
        client,
        account_id="account-1",
        mailbox_id="inbox",
        page=99,
    )

    assert result.page == 1
    assert result.pages == 0
    assert result.emails == []
    assert result.has_previous is False
    assert result.has_next is False


@pytest.mark.django_db
def test_inbox_view_preserves_mailbox_search_and_page_navigation(client):
    user = User.objects.create_user(
        username="pagination-user",
        email="user@example.com",
        password="pagination-password-123",
    )
    client.force_login(user)
    jmap = FakeInboxClient(total=125)

    with patch("mailforge.inbox_views._mail_client", return_value=jmap):
        response = client.get(
            reverse("webmail-inbox"),
            {"mailbox": "inbox", "q": "invoice", "page": 2},
        )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Page 2 of 3" in content
    assert "125 messages" in content
    assert "search: “invoice”" in content
    assert "page=1" in content
    assert "page=3" in content
    assert "q=invoice" in content
    assert "mailbox=inbox" in content
    query = _query_calls(jmap)[0]
    assert query[1]["position"] == 50
    assert query[1]["filter"] == {"inMailbox": "inbox", "text": "invoice"}


@pytest.mark.django_db
def test_unknown_mailbox_id_falls_back_to_inbox(client):
    user = User.objects.create_user(
        username="mailbox-fallback-user",
        email="fallback@example.com",
        password="fallback-password-123",
    )
    client.force_login(user)
    jmap = FakeInboxClient(total=5)

    with patch("mailforge.inbox_views._mail_client", return_value=jmap):
        response = client.get(
            reverse("webmail-inbox"),
            {"mailbox": "not-in-account"},
        )

    assert response.status_code == 200
    assert b"Inbox" in response.content
    query = _query_calls(jmap)[0]
    assert query[1]["filter"] == {"inMailbox": "inbox"}
