from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from integrations.stalwart.mail_jmap import MailJMAPError
from mailforge.drafts import (
    DraftError,
    discard_draft,
    get_saved_draft,
    save_draft,
    submit_saved_draft,
)
from mailforge.forms import DraftComposeForm
from mailforge.webmail_views import (
    COMPOSE_MODES,
    _account_context,
    _address_text,
    _compose_initial,
    _compose_labels,
    _concrete_identities,
    _identity_domain_ready,
    _mail_client,
    _plain_text_body,
    _preferred_identity_id,
    _reply_threading,
)


def _source_message(client, account_id: str, source_id: str, mode: str | None):
    if not source_id or mode not in COMPOSE_MODES:
        return None, None
    try:
        return client.get_email(account_id, source_id), mode
    except MailJMAPError as exc:
        raise DraftError("The source message for this draft is no longer available.") from exc


def _upload_attachments(client, uploaded_files):
    uploaded = []
    for file_obj in uploaded_files or []:
        uploaded.append(
            client.upload(
                file_obj.read(),
                content_type=file_obj.content_type or "application/octet-stream",
                name=file_obj.name,
            )
        )
    return uploaded


def _attachment_bytes(*groups) -> int:
    total = 0
    seen = set()
    for group in groups:
        for item in group or []:
            key = (str(item.get("blobId") or ""), str(item.get("name") or ""))
            if key in seen:
                continue
            seen.add(key)
            total += int(item.get("size") or 0)
    return total


def _source_attachments(source, mode):
    if source and mode == "forward":
        return list(source.get("attachments") or [])
    return []


def _identity_for_draft(draft, identities):
    sender = next(iter(draft.get("from") or []), {})
    sender_email = str(sender.get("email") or "").lower()
    for identity in identities:
        if identity["email"].lower() == sender_email:
            return identity["id"]
    return _preferred_identity_id(draft, identities)


def _draft_initial(draft, identities):
    return {
        "identity_id": _identity_for_draft(draft, identities),
        "to": _address_text(draft.get("to") or []),
        "cc": _address_text(draft.get("cc") or []),
        "bcc": _address_text(draft.get("bcc") or []),
        "subject": draft.get("subject") or "",
        "body": _plain_text_body(draft) or "",
    }


def _render_compose(
    request,
    *,
    form,
    identities,
    draft_id="",
    existing_attachments=None,
    source=None,
    mode=None,
):
    page_title, submit_label = _compose_labels(mode)
    if draft_id:
        page_title = "Edit draft"
        submit_label = "Send draft"
    return render(
        request,
        "webmail/compose.html",
        {
            "form": form,
            "sending_ready": any(_identity_domain_ready(item) for item in identities),
            "page_title": page_title,
            "submit_label": submit_label,
            "mode": mode,
            "source": source,
            "draft_id": draft_id,
            "existing_attachments": existing_attachments or [],
            "draft_enabled": True,
        },
    )


def _form_and_context(request, client, account_id, identities):
    draft_id = (request.POST.get("draft_id") or "").strip()
    source_id = (request.POST.get("source_id") or "").strip()
    requested_mode = (request.POST.get("compose_mode") or "").strip() or None
    source, mode = _source_message(client, account_id, source_id, requested_mode)
    form = DraftComposeForm(request.POST, request.FILES, identities=identities)
    existing = None
    if draft_id:
        existing = get_saved_draft(client, account_id=account_id, draft_id=draft_id)
    return form, draft_id, existing, source, mode


def _combined_size_ok(form, existing, source, mode) -> bool:
    new_size = sum(file_obj.size for file_obj in form.cleaned_data.get("attachments") or [])
    total = _attachment_bytes(
        (existing or {}).get("attachments") or [],
        _source_attachments(source, mode),
    ) + new_size
    max_total = settings.MAILFORGE_MAX_TOTAL_ATTACHMENT_MB * 1024 * 1024
    if total > max_total:
        form.add_error(
            "attachments",
            f"Saved and new attachments exceed the {settings.MAILFORGE_MAX_TOTAL_ATTACHMENT_MB} MB total limit.",
        )
        return False
    return True


@login_required
def webmail_edit_draft(request, draft_id):
    client = _mail_client(request)
    if client is None:
        return redirect("webmail-home")
    try:
        account_id, _ = _account_context(client)
        identities = _concrete_identities(client)
        draft = get_saved_draft(client, account_id=account_id, draft_id=draft_id)
    except (DraftError, MailJMAPError):
        raise Http404 from None

    form = DraftComposeForm(initial=_draft_initial(draft, identities), identities=identities)
    return _render_compose(
        request,
        form=form,
        identities=identities,
        draft_id=draft_id,
        existing_attachments=draft.get("attachments") or [],
    )


@login_required
@require_POST
def webmail_save_draft(request):
    client = _mail_client(request)
    if client is None:
        return redirect("webmail-home")
    try:
        account_id, _ = _account_context(client)
        identities = _concrete_identities(client)
        form, draft_id, existing, source, mode = _form_and_context(
            request, client, account_id, identities
        )
    except (DraftError, MailJMAPError) as exc:
        messages.error(request, str(exc))
        return redirect("webmail-inbox")

    if not form.is_valid() or not _combined_size_ok(form, existing, source, mode):
        return _render_compose(
            request,
            form=form,
            identities=identities,
            draft_id=draft_id,
            existing_attachments=(existing or {}).get("attachments") or [],
            source=source,
            mode=mode,
        )

    try:
        uploaded = _upload_attachments(client, form.cleaned_data.get("attachments"))
        in_reply_to, references = _reply_threading(source, mode)
        result = save_draft(
            client,
            account_id=account_id,
            identity_id=form.cleaned_data["identity_id"],
            to=form.cleaned_data["to"],
            cc=form.cleaned_data["cc"],
            bcc=form.cleaned_data["bcc"],
            subject=form.cleaned_data.get("subject", ""),
            body=form.cleaned_data.get("body", ""),
            attachments=[*_source_attachments(source, mode), *uploaded],
            draft_id=draft_id or None,
            in_reply_to=in_reply_to or None,
            references=references or None,
        )
    except (DraftError, MailJMAPError) as exc:
        messages.error(request, str(exc))
        return _render_compose(
            request,
            form=form,
            identities=identities,
            draft_id=draft_id,
            existing_attachments=(existing or {}).get("attachments") or [],
            source=source,
            mode=mode,
        )

    messages.success(request, "Draft saved.")
    return redirect("webmail-edit-draft", draft_id=result.draft_id)


@login_required
@require_POST
def webmail_autosave_draft(request):
    client = _mail_client(request)
    if client is None:
        return JsonResponse({"detail": "Mailbox is not connected."}, status=401)
    try:
        account_id, _ = _account_context(client)
        identities = _concrete_identities(client)
        form, draft_id, existing, source, mode = _form_and_context(
            request, client, account_id, identities
        )
    except (DraftError, MailJMAPError) as exc:
        return JsonResponse({"detail": str(exc)}, status=409)

    if not form.is_valid():
        return JsonResponse({"detail": "Draft contains fields that are not valid yet."}, status=422)
    if not _combined_size_ok(form, existing, source, mode):
        return JsonResponse({"detail": "Draft attachments exceed the total limit."}, status=422)

    try:
        in_reply_to, references = _reply_threading(source, mode)
        result = save_draft(
            client,
            account_id=account_id,
            identity_id=form.cleaned_data["identity_id"],
            to=form.cleaned_data["to"],
            cc=form.cleaned_data["cc"],
            bcc=form.cleaned_data["bcc"],
            subject=form.cleaned_data.get("subject", ""),
            body=form.cleaned_data.get("body", ""),
            attachments=_source_attachments(source, mode),
            draft_id=draft_id or None,
            in_reply_to=in_reply_to or None,
            references=references or None,
        )
    except (DraftError, MailJMAPError) as exc:
        return JsonResponse({"detail": str(exc)}, status=409)

    return JsonResponse(
        {
            "draft_id": result.draft_id,
            "created": result.created,
            "detail": "Draft saved.",
        }
    )


@login_required
@require_POST
def webmail_send_draft(request):
    client = _mail_client(request)
    if client is None:
        return redirect("webmail-home")
    try:
        account_id, _ = _account_context(client)
        identities = _concrete_identities(client)
        form, draft_id, existing, source, mode = _form_and_context(
            request, client, account_id, identities
        )
    except (DraftError, MailJMAPError) as exc:
        messages.error(request, str(exc))
        return redirect("webmail-inbox")

    if form.is_valid() and not any(
        (form.cleaned_data.get("to"), form.cleaned_data.get("cc"), form.cleaned_data.get("bcc"))
    ):
        form.add_error("to", "Enter at least one recipient before sending.")
    if not form.is_valid() or not _combined_size_ok(form, existing, source, mode):
        return _render_compose(
            request,
            form=form,
            identities=identities,
            draft_id=draft_id,
            existing_attachments=(existing or {}).get("attachments") or [],
            source=source,
            mode=mode,
        )

    selected_identity = next(
        (item for item in identities if item["id"] == form.cleaned_data["identity_id"]),
        None,
    )
    if not selected_identity or not _identity_domain_ready(selected_identity):
        messages.error(
            request,
            "Sending is disabled for that identity until its domain passes MailForge readiness checks.",
        )
        return _render_compose(
            request,
            form=form,
            identities=identities,
            draft_id=draft_id,
            existing_attachments=(existing or {}).get("attachments") or [],
            source=source,
            mode=mode,
        )

    try:
        uploaded = _upload_attachments(client, form.cleaned_data.get("attachments"))
        in_reply_to, references = _reply_threading(source, mode)
        saved = save_draft(
            client,
            account_id=account_id,
            identity_id=form.cleaned_data["identity_id"],
            to=form.cleaned_data["to"],
            cc=form.cleaned_data["cc"],
            bcc=form.cleaned_data["bcc"],
            subject=form.cleaned_data.get("subject", ""),
            body=form.cleaned_data.get("body", ""),
            attachments=[*_source_attachments(source, mode), *uploaded],
            draft_id=draft_id or None,
            in_reply_to=in_reply_to or None,
            references=references or None,
            apply_signature=True,
        )
        submit_saved_draft(
            client,
            account_id=account_id,
            draft_id=saved.draft_id,
            identity_id=form.cleaned_data["identity_id"],
        )
        if source and mode in {"reply", "reply-all"}:
            client.mark_answered(account_id, source["id"])
    except (DraftError, MailJMAPError) as exc:
        messages.error(request, str(exc))
        return _render_compose(
            request,
            form=form,
            identities=identities,
            draft_id=draft_id,
            existing_attachments=(existing or {}).get("attachments") or [],
            source=source,
            mode=mode,
        )

    messages.success(request, "Message sent.")
    return redirect("webmail-inbox")


@login_required
@require_POST
def webmail_discard_draft(request, draft_id):
    client = _mail_client(request)
    if client is None:
        return redirect("webmail-home")
    try:
        account_id, _ = _account_context(client)
        discard_draft(client, account_id=account_id, draft_id=draft_id)
    except (DraftError, MailJMAPError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Draft discarded.")
    return redirect("webmail-inbox")
