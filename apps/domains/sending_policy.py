from dataclasses import dataclass

from apps.mailboxes.models import Mailbox
from integrations.factory import (
    MailBackendConfigurationError,
    UnsupportedMailBackend,
    get_mail_backend,
)


@dataclass(frozen=True)
class SendingPolicySyncResult:
    success: bool
    mailbox_count: int
    failed_addresses: tuple[str, ...] = ()
    detail: str = ""


def _active_provisioned_mailboxes(domain):
    return list(
        domain.mailboxes.filter(status=Mailbox.Status.ACTIVE)
        .exclude(backend_identifier="")
        .order_by("local_part")
    )


def _resolve_backend(mailboxes, backend):
    try:
        return backend or get_mail_backend(), None
    except (MailBackendConfigurationError, UnsupportedMailBackend):
        return None, SendingPolicySyncResult(
            success=False,
            mailbox_count=len(mailboxes),
            failed_addresses=tuple(mailbox.email_address for mailbox in mailboxes),
            detail="The Stalwart management backend is not configured for mailbox policy enforcement.",
        )


def sync_domain_sending_policy(
    domain,
    *,
    enabled: bool,
    backend=None,
) -> SendingPolicySyncResult:
    mailboxes = _active_provisioned_mailboxes(domain)
    if not mailboxes:
        return SendingPolicySyncResult(
            success=True,
            mailbox_count=0,
            detail="No active provisioned mailboxes require SMTP policy synchronization.",
        )

    backend, error = _resolve_backend(mailboxes, backend)
    if error is not None:
        return error

    setter = getattr(backend, "set_account_sending_enabled", None)
    if setter is None:
        return SendingPolicySyncResult(
            success=False,
            mailbox_count=len(mailboxes),
            failed_addresses=tuple(mailbox.email_address for mailbox in mailboxes),
            detail="The configured mail backend cannot enforce per-account sending permissions.",
        )

    failures = []
    for mailbox in mailboxes:
        try:
            setter(account_id=mailbox.backend_identifier, enabled=enabled)
        except Exception:
            failures.append(mailbox.email_address)

    if failures:
        return SendingPolicySyncResult(
            success=False,
            mailbox_count=len(mailboxes),
            failed_addresses=tuple(failures),
            detail="Stalwart sending permission synchronization failed for: " + ", ".join(failures),
        )

    state = "enabled" if enabled else "disabled"
    return SendingPolicySyncResult(
        success=True,
        mailbox_count=len(mailboxes),
        detail=f"Stalwart emailSend permission is {state} for all active MailForge mailboxes.",
    )


def sync_domain_emergency_suspension(domain, *, backend=None) -> SendingPolicySyncResult:
    """Re-apply the stronger all-permissions suspension used by emergency controls."""
    mailboxes = _active_provisioned_mailboxes(domain)
    if not mailboxes:
        return SendingPolicySyncResult(
            success=True,
            mailbox_count=0,
            detail="No active provisioned mailboxes require emergency suspension synchronization.",
        )

    backend, error = _resolve_backend(mailboxes, backend)
    if error is not None:
        return error

    setter = getattr(backend, "set_account_suspended", None)
    if setter is None:
        return SendingPolicySyncResult(
            success=False,
            mailbox_count=len(mailboxes),
            failed_addresses=tuple(mailbox.email_address for mailbox in mailboxes),
            detail="The configured mail backend cannot enforce emergency mailbox suspension.",
        )

    failures = []
    for mailbox in mailboxes:
        try:
            setter(
                account_id=mailbox.backend_identifier,
                suspended=True,
                sending_enabled=False,
            )
        except Exception:
            failures.append(mailbox.email_address)

    if failures:
        return SendingPolicySyncResult(
            success=False,
            mailbox_count=len(mailboxes),
            failed_addresses=tuple(failures),
            detail="Emergency Stalwart suspension synchronization failed for: "
            + ", ".join(failures),
        )

    return SendingPolicySyncResult(
        success=True,
        mailbox_count=len(mailboxes),
        detail="Emergency suspension is enforced for all active MailForge mailbox accounts.",
    )
