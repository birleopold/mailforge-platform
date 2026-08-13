from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from integrations.stalwart.mail_jmap import JMAP_CORE, JMAP_MAIL, JMAP_SUBMISSION, MailJMAPError


class DraftError(RuntimeError):
    pass


@dataclass(frozen=True)
class DraftSaveResult:
    draft_id: str
    created: bool


def _mailbox_by_role(client, account_id: str, role: str) -> dict[str, Any] | None:
    return next(
        (mailbox for mailbox in client.list_mailboxes(account_id) if mailbox.get("role") == role),
        None,
    )


def _identity_by_id(client, identity_id: str) -> dict[str, Any]:
    identity = next(
        (item for item in client.list_identities() if str(item.get("id")) == str(identity_id)),
        None,
    )
    if not identity or not identity.get("email") or str(identity["email"]).startswith("*@"):
        raise DraftError("The selected sending identity is not available.")
    return identity


def _with_signature(body: str, identity: dict[str, Any]) -> str:
    signature = str(identity.get("textSignature") or "").strip()
    body = body or ""
    if not signature:
        return body
    if body.rstrip().endswith(signature):
        return body
    if not body.strip():
        return signature
    return f"{body.rstrip()}\n\n{signature}"


def _attachment_part(attachment: dict[str, Any]) -> dict[str, Any] | None:
    blob_id = attachment.get("blobId")
    if not blob_id:
        return None
    return {
        "blobId": str(blob_id),
        "type": attachment.get("type") or "application/octet-stream",
        "name": attachment.get("name") or "attachment",
        "disposition": "attachment",
        "size": int(attachment.get("size") or 0),
    }


def _dedupe_attachments(*groups) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for group in groups:
        for attachment in group or []:
            part = _attachment_part(attachment)
            if part is None:
                continue
            key = (part["blobId"], part["name"])
            if key in seen:
                continue
            result.append(part)
            seen.add(key)
    return result


def _draft_payload(
    *,
    drafts_id: str,
    identity: dict[str, Any],
    to,
    cc,
    bcc,
    subject: str,
    body: str,
    attachments,
    in_reply_to=None,
    references=None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mailboxIds": {drafts_id: True},
        "keywords": {"$draft": True, "$seen": True},
        "from": [{"name": identity.get("name") or "", "email": identity["email"]}],
        "to": list(to or []),
        "subject": subject or "",
        "bodyStructure": {"type": "text/plain", "partId": "body"},
        "bodyValues": {"body": {"value": body or "", "isTruncated": False}},
    }
    if cc:
        payload["cc"] = list(cc)
    else:
        payload["cc"] = []
    if bcc:
        payload["bcc"] = list(bcc)
    else:
        payload["bcc"] = []
    if attachments:
        payload["attachments"] = list(attachments)
    else:
        payload["attachments"] = []
    if in_reply_to:
        payload["inReplyTo"] = list(dict.fromkeys(in_reply_to))
    else:
        payload["inReplyTo"] = []
    if references:
        payload["references"] = list(dict.fromkeys(references))
    else:
        payload["references"] = []
    return payload


def get_saved_draft(client, *, account_id: str, draft_id: str) -> dict[str, Any]:
    drafts = _mailbox_by_role(client, account_id, "drafts")
    if drafts is None:
        raise DraftError("This mail account does not have a Drafts mailbox.")
    try:
        email = client.get_email(account_id, str(draft_id))
    except MailJMAPError as exc:
        raise DraftError("The saved draft could not be read.") from exc
    mailbox_ids = email.get("mailboxIds") or {}
    keywords = email.get("keywords") or {}
    if drafts["id"] not in mailbox_ids or "$draft" not in keywords:
        raise DraftError("The selected message is not an editable draft.")
    return email


def save_draft(
    client,
    *,
    account_id: str,
    identity_id: str,
    to,
    subject: str,
    body: str,
    cc=None,
    bcc=None,
    attachments=None,
    draft_id: str | None = None,
    in_reply_to=None,
    references=None,
    apply_signature: bool = False,
) -> DraftSaveResult:
    drafts = _mailbox_by_role(client, account_id, "drafts")
    if drafts is None:
        raise DraftError("This mail account does not have a Drafts mailbox.")
    identity = _identity_by_id(client, identity_id)

    existing_attachments = []
    if draft_id:
        existing = get_saved_draft(client, account_id=account_id, draft_id=draft_id)
        existing_attachments = existing.get("attachments") or []
        if in_reply_to is None:
            in_reply_to = existing.get("inReplyTo") or []
        if references is None:
            references = existing.get("references") or []

    combined_attachments = _dedupe_attachments(existing_attachments, attachments)
    rendered_body = _with_signature(body or "", identity) if apply_signature else (body or "")
    payload = _draft_payload(
        drafts_id=str(drafts["id"]),
        identity=identity,
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject,
        body=rendered_body,
        attachments=combined_attachments,
        in_reply_to=in_reply_to,
        references=references,
    )

    if draft_id:
        arguments = {
            "accountId": account_id,
            "update": {str(draft_id): payload},
        }
        responses = client.call(
            [["Email/set", arguments, "draft-save"]],
            using=(JMAP_CORE, JMAP_MAIL),
        )
        data = responses[0][1]
        error = (data.get("notUpdated") or {}).get(str(draft_id))
        if error:
            raise DraftError(f"The draft could not be updated: {error}")
        return DraftSaveResult(draft_id=str(draft_id), created=False)

    responses = client.call(
        [
            [
                "Email/set",
                {"accountId": account_id, "create": {"mailforge-draft": payload}},
                "draft-save",
            ]
        ],
        using=(JMAP_CORE, JMAP_MAIL),
    )
    data = responses[0][1]
    created = (data.get("created") or {}).get("mailforge-draft")
    if not created or not created.get("id"):
        error = (data.get("notCreated") or {}).get("mailforge-draft")
        raise DraftError(f"The draft could not be created: {error or data}")
    return DraftSaveResult(draft_id=str(created["id"]), created=True)


def submit_saved_draft(
    client,
    *,
    account_id: str,
    draft_id: str,
    identity_id: str,
) -> dict[str, Any]:
    get_saved_draft(client, account_id=account_id, draft_id=draft_id)
    _identity_by_id(client, identity_id)
    sent = _mailbox_by_role(client, account_id, "sent")
    if sent is None:
        raise DraftError("This mail account does not have a Sent mailbox.")

    responses = client.call(
        [
            [
                "EmailSubmission/set",
                {
                    "accountId": account_id,
                    "create": {
                        "submission": {
                            "identityId": identity_id,
                            "emailId": draft_id,
                        }
                    },
                    "onSuccessUpdateEmail": {
                        "#submission": {
                            f"mailboxIds/{sent['id']}": True,
                            "keywords/$draft": None,
                        }
                    },
                },
                "draft-submit",
            ]
        ],
        using=(JMAP_CORE, JMAP_MAIL, JMAP_SUBMISSION),
    )
    data = responses[0][1]
    created = (data.get("created") or {}).get("submission")
    if not created:
        error = (data.get("notCreated") or {}).get("submission")
        raise DraftError(f"The draft could not be submitted: {error or data}")
    return created


def discard_draft(client, *, account_id: str, draft_id: str) -> None:
    get_saved_draft(client, account_id=account_id, draft_id=draft_id)
    responses = client.call(
        [
            [
                "Email/set",
                {"accountId": account_id, "destroy": [str(draft_id)]},
                "draft-discard",
            ]
        ],
        using=(JMAP_CORE, JMAP_MAIL),
    )
    data = responses[0][1]
    error = (data.get("notDestroyed") or {}).get(str(draft_id))
    if error:
        raise DraftError(f"The draft could not be discarded: {error}")
    if str(draft_id) not in set(data.get("destroyed") or []):
        raise DraftError("The mail server did not confirm draft deletion.")
