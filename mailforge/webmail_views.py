from __future__ import annotations

import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.domains.models import Domain
from integrations.stalwart.mail_jmap import MailJMAPClient, MailJMAPError
from integrations.stalwart.oauth import StalwartOAuthClient, StalwartOAuthError, create_pkce_flow
from mailforge.forms import ComposeForm
from mailforge.webmail_auth import (
    WebmailSessionError,
    clear_oauth_token,
    get_oauth_token,
    pop_oauth_flow,
    store_oauth_flow,
    store_oauth_token,
    token_needs_refresh,
)


def _oauth_client() -> StalwartOAuthClient:
    return StalwartOAuthClient(
        client_id=settings.MAILFORGE_OAUTH_CLIENT_ID,
        client_secret=settings.MAILFORGE_OAUTH_CLIENT_SECRET,
    )


def _usable_token(request):
    try:
        token = get_oauth_token(request)
    except WebmailSessionError:
        clear_oauth_token(request)
        return None
    if not token:
        return None
    if not token_needs_refresh(token):
        return token

    refresh_token = token.get("refresh_token")
    if not refresh_token:
        clear_oauth_token(request)
        return None
    try:
        refreshed = _oauth_client().refresh_token(refresh_token)
    except StalwartOAuthError:
        clear_oauth_token(request)
        return None
    if not refreshed.get("refresh_token"):
        refreshed["refresh_token"] = refresh_token
    store_oauth_token(request, refreshed)
    return get_oauth_token(request)


def _mail_client(request) -> MailJMAPClient | None:
    token = _usable_token(request)
    if not token:
        return None
    return MailJMAPClient(access_token=token["access_token"])


def _account_context(client: MailJMAPClient):
    session = client.session()
    account_id = client.primary_mail_account_id()
    account = session.get("accounts", {}).get(account_id, {})
    return account_id, account


def _plain_text_body(email: dict) -> str:
    body_values = email.get("bodyValues") or {}
    chunks = []
    for part in email.get("textBody") or []:
        value = body_values.get(part.get("partId"), {}).get("value")
        if value:
            chunks.append(value)
    return "\n\n".join(chunks).strip()


def _concrete_identities(client: MailJMAPClient):
    return [
        identity
        for identity in client.list_identities()
        if identity.get("id") and identity.get("email") and not identity["email"].startswith("*@")
    ]


def _identity_domain_ready(identity: dict) -> bool:
    email = identity.get("email", "")
    if "@" not in email:
        return False
    domain_name = email.rsplit("@", 1)[1].lower()
    return Domain.objects.filter(
        name=domain_name,
        sending_enabled=True,
        status=Domain.Status.ACTIVE,
    ).exists()


@login_required
def webmail_home(request):
    if _usable_token(request):
        return redirect("webmail-inbox")
    return render(request, "webmail/connect.html")


@login_required
@require_POST
def webmail_connect(request):
    flow = create_pkce_flow()
    redirect_uri = request.build_absolute_uri("/mail/oauth/callback/")
    try:
        oauth = _oauth_client()
        authorization_url = oauth.authorization_url(
            redirect_uri=redirect_uri,
            state=flow.state,
            code_challenge=flow.challenge,
            scope=settings.MAILFORGE_OAUTH_SCOPE,
        )
    except (StalwartOAuthError, KeyError):
        messages.error(request, "Stalwart OAuth is not configured or is temporarily unavailable.")
        return redirect("webmail-home")

    store_oauth_flow(
        request,
        state=flow.state,
        verifier=flow.verifier,
        redirect_uri=redirect_uri,
    )
    return redirect(authorization_url)


@login_required
def webmail_oauth_callback(request):
    if request.GET.get("error"):
        clear_oauth_token(request)
        messages.error(request, "Mailbox authorization was denied or could not be completed.")
        return redirect("webmail-home")

    code = request.GET.get("code", "")
    state = request.GET.get("state", "")
    try:
        flow = pop_oauth_flow(request)
    except WebmailSessionError as exc:
        messages.error(request, str(exc))
        return redirect("webmail-home")

    if not code or not state or not secrets.compare_digest(state, str(flow.get("state", ""))):
        clear_oauth_token(request)
        messages.error(request, "Mailbox authorization state was invalid. Please try again.")
        return redirect("webmail-home")

    try:
        token = _oauth_client().exchange_code(
            code=code,
            redirect_uri=flow["redirect_uri"],
            code_verifier=flow["verifier"],
        )
        store_oauth_token(request, token)
        client = _mail_client(request)
        if client is None:
            raise MailJMAPError("No usable mailbox token was returned.")
        _account_context(client)
    except (StalwartOAuthError, MailJMAPError, WebmailSessionError, KeyError):
        clear_oauth_token(request)
        messages.error(request, "Mailbox authorization completed, but the JMAP account could not be opened.")
        return redirect("webmail-home")

    messages.success(request, "Mailbox connected securely.")
    return redirect("webmail-inbox")


@login_required
def webmail_inbox(request):
    client = _mail_client(request)
    if client is None:
        return redirect("webmail-home")

    selected_mailbox = request.GET.get("mailbox") or None
    search_text = (request.GET.get("q") or "").strip()[:500]
    try:
        _, account = _account_context(client)
        mailboxes = client.list_mailboxes()
        mailbox_ids = {mailbox.get("id") for mailbox in mailboxes}
        if selected_mailbox and selected_mailbox not in mailbox_ids:
            raise Http404
        messages_page = client.list_emails(
            mailbox_id=selected_mailbox,
            search_text=search_text,
            limit=50,
        )
    except MailJMAPError:
        messages.error(request, "The mailbox server is temporarily unavailable.")
        return render(
            request,
            "webmail/inbox.html",
            {
                "mail_account": {},
                "mailboxes": [],
                "emails": [],
                "total": 0,
                "selected_mailbox": selected_mailbox,
                "search_text": search_text,
                "mail_error": True,
            },
            status=503,
        )

    return render(
        request,
        "webmail/inbox.html",
        {
            "mail_account": account,
            "mailboxes": mailboxes,
            "emails": messages_page["emails"],
            "total": messages_page["total"],
            "selected_mailbox": selected_mailbox,
            "search_text": search_text,
            "mail_error": False,
        },
    )


@login_required
def webmail_message(request, email_id):
    client = _mail_client(request)
    if client is None:
        return redirect("webmail-home")
    try:
        _, account = _account_context(client)
        email = client.get_email(email_id)
        keywords = email.get("keywords") or {}
        if "$seen" not in keywords:
            client.set_seen(email_id, seen=True)
            email["keywords"] = {**keywords, "$seen": True}
    except MailJMAPError:
        raise Http404 from None

    return render(
        request,
        "webmail/message.html",
        {
            "mail_account": account,
            "email": email,
            "plain_text_body": _plain_text_body(email) or email.get("preview", ""),
        },
    )


@login_required
@require_POST
def webmail_mark_unread(request, email_id):
    client = _mail_client(request)
    if client is None:
        return redirect("webmail-home")
    try:
        client.set_seen(email_id, seen=False)
    except MailJMAPError:
        messages.error(request, "The message could not be marked unread.")
    else:
        messages.success(request, "Message marked unread.")
    return redirect("webmail-inbox")


@login_required
def webmail_compose(request):
    client = _mail_client(request)
    if client is None:
        return redirect("webmail-home")

    try:
        _, account = _account_context(client)
        identities = _concrete_identities(client)
    except MailJMAPError:
        messages.error(request, "Sending identities could not be loaded from the mail server.")
        return redirect("webmail-inbox")

    if not identities:
        messages.error(request, "This mailbox has no concrete sending identity.")
        return redirect("webmail-inbox")

    form = ComposeForm(request.POST or None, identities=identities)
    if request.method == "POST" and form.is_valid():
        identity = next(
            (item for item in identities if item["id"] == form.cleaned_data["identity_id"]),
            None,
        )
        if identity is None or not _identity_domain_ready(identity):
            form.add_error(
                "identity_id",
                "Sending is disabled for this domain until MailForge DNS readiness checks pass.",
            )
        else:
            try:
                client.send_plaintext(
                    identity_id=identity["id"],
                    to=form.cleaned_data["to"],
                    cc=form.cleaned_data["cc"],
                    bcc=form.cleaned_data["bcc"],
                    subject=form.cleaned_data["subject"],
                    body=form.cleaned_data["body"],
                )
            except MailJMAPError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, "Message submitted for delivery.")
                return redirect("webmail-inbox")

    return render(
        request,
        "webmail/compose.html",
        {
            "mail_account": account,
            "form": form,
        },
    )


@login_required
@require_POST
def webmail_disconnect(request):
    clear_oauth_token(request)
    messages.success(request, "Mailbox disconnected from this browser session.")
    return redirect("webmail-home")
