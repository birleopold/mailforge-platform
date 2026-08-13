from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from apps.mailboxes.models import Alias, Mailbox, normalize_local_part
from apps.tenants.models import Tenant
from integrations.factory import get_mail_backend


class MailboxProvisioningError(RuntimeError):
    pass


class MailboxLifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class MailboxProvisioningResult:
    mailbox: Mailbox


def provision_mailbox(
    domain_id: int,
    *,
    local_part: str,
    password: str,
    display_name: str = "",
    quota_mb: int | None = None,
    backend=None,
    actor=None,
) -> MailboxProvisioningResult:
    domain = Domain.objects.select_related("tenant").get(pk=domain_id)
    if domain.tenant.status != Tenant.Status.ACTIVE:
        raise MailboxProvisioningError("The organization is suspended.")
    if not domain.backend_identifier:
        raise MailboxProvisioningError("The domain must be provisioned before mailboxes are created.")
    if domain.status not in {Domain.Status.DNS_CONFIGURATION, Domain.Status.ACTIVE}:
        raise MailboxProvisioningError("The domain is not ready for mailbox provisioning.")

    local_part = normalize_local_part(local_part)
    quota_mb = quota_mb or settings.MAILFORGE_DEFAULT_MAILBOX_QUOTA_MB
    if quota_mb <= 0 or quota_mb > settings.MAILFORGE_MAX_MAILBOX_QUOTA_MB:
        raise MailboxProvisioningError("Mailbox quota is outside the allowed range.")

    with transaction.atomic():
        locked_domain = Domain.objects.select_for_update().get(pk=domain_id)
        active_count = locked_domain.mailboxes.exclude(status=Mailbox.Status.DELETED).count()
        if active_count >= settings.MAILFORGE_DEFAULT_MAX_MAILBOXES:
            raise MailboxProvisioningError("This domain has reached its mailbox limit.")
        if Alias.objects.filter(domain=locked_domain, local_part=local_part, active=True).exists():
            raise MailboxProvisioningError("That address is already used by an alias.")
        try:
            mailbox = Mailbox.objects.create(
                domain=locked_domain,
                local_part=local_part,
                display_name=display_name.strip(),
                quota_mb=quota_mb,
                status=Mailbox.Status.PROVISIONING,
            )
        except IntegrityError as exc:
            raise MailboxProvisioningError("That mailbox already exists.") from exc

    try:
        resolved_backend = backend or get_mail_backend()
        created = resolved_backend.create_mailbox(
            email=mailbox.email_address,
            password=password,
            quota_mb=quota_mb,
            display_name=mailbox.display_name,
            sending_enabled=domain.sending_enabled and domain.status == Domain.Status.ACTIVE,
        )
        backend_identifier = str(created["id"])
    except Exception:
        mailbox.delete()
        raise

    mailbox.backend_identifier = backend_identifier
    mailbox.status = Mailbox.Status.ACTIVE
    mailbox.save(update_fields=["backend_identifier", "status"])
    AuditEvent.objects.create(
        tenant=domain.tenant,
        actor=actor,
        action="mailbox.provisioned",
        target_type="mailbox",
        target_id=str(mailbox.pk),
        metadata={
            "email": mailbox.email_address,
            "quota_mb": mailbox.quota_mb,
            "backend_identifier": backend_identifier,
            "sending_enabled": domain.sending_enabled and domain.status == Domain.Status.ACTIVE,
        },
    )
    return MailboxProvisioningResult(mailbox=mailbox)


def _mailbox_for_lifecycle(mailbox_id: int) -> Mailbox:
    mailbox = Mailbox.objects.select_related("domain__tenant").get(pk=mailbox_id)
    if mailbox.status == Mailbox.Status.DELETED:
        raise MailboxLifecycleError("This mailbox has already been deleted.")
    if not mailbox.backend_identifier:
        raise MailboxLifecycleError("This mailbox is not provisioned in the mail backend.")
    return mailbox


def _audit_mailbox(mailbox: Mailbox, *, actor, action: str, metadata=None):
    AuditEvent.objects.create(
        tenant=mailbox.domain.tenant,
        actor=actor,
        action=action,
        target_type="mailbox",
        target_id=str(mailbox.pk),
        metadata={"email": mailbox.email_address, **(metadata or {})},
    )


def suspend_mailbox(mailbox_id: int, *, backend=None, actor=None) -> Mailbox:
    mailbox = _mailbox_for_lifecycle(mailbox_id)
    if mailbox.status == Mailbox.Status.SUSPENDED:
        return mailbox
    if mailbox.status != Mailbox.Status.ACTIVE:
        raise MailboxLifecycleError("Only active mailboxes can be suspended.")

    resolved_backend = backend or get_mail_backend()
    resolved_backend.set_account_suspended(
        account_id=mailbox.backend_identifier,
        suspended=True,
    )
    Mailbox.objects.filter(pk=mailbox.pk, status=Mailbox.Status.ACTIVE).update(
        status=Mailbox.Status.SUSPENDED
    )
    mailbox.refresh_from_db()
    _audit_mailbox(mailbox, actor=actor, action="mailbox.suspended")
    return mailbox


def reactivate_mailbox(mailbox_id: int, *, backend=None, actor=None) -> Mailbox:
    mailbox = _mailbox_for_lifecycle(mailbox_id)
    if mailbox.status == Mailbox.Status.ACTIVE:
        return mailbox
    if mailbox.status != Mailbox.Status.SUSPENDED:
        raise MailboxLifecycleError("Only suspended mailboxes can be reactivated.")

    domain = mailbox.domain
    if domain.tenant.status != Tenant.Status.ACTIVE:
        raise MailboxLifecycleError("Reactivate the organization before reactivating mailboxes.")
    if domain.status == Domain.Status.SUSPENDED:
        raise MailboxLifecycleError("Reactivate the domain before reactivating mailboxes.")
    sending_enabled = domain.sending_enabled and domain.status == Domain.Status.ACTIVE
    resolved_backend = backend or get_mail_backend()
    resolved_backend.set_account_suspended(
        account_id=mailbox.backend_identifier,
        suspended=False,
        sending_enabled=sending_enabled,
    )
    Mailbox.objects.filter(pk=mailbox.pk, status=Mailbox.Status.SUSPENDED).update(
        status=Mailbox.Status.ACTIVE
    )
    mailbox.refresh_from_db()
    _audit_mailbox(
        mailbox,
        actor=actor,
        action="mailbox.reactivated",
        metadata={"sending_enabled": sending_enabled},
    )
    return mailbox


def reset_mailbox_password(
    mailbox_id: int,
    *,
    password: str,
    backend=None,
    actor=None,
) -> Mailbox:
    mailbox = _mailbox_for_lifecycle(mailbox_id)
    if mailbox.status not in {Mailbox.Status.ACTIVE, Mailbox.Status.SUSPENDED}:
        raise MailboxLifecycleError("This mailbox cannot have its password reset in its current state.")

    resolved_backend = backend or get_mail_backend()
    resolved_backend.reset_account_password(
        account_id=mailbox.backend_identifier,
        password=password,
    )
    _audit_mailbox(mailbox, actor=actor, action="mailbox.password_reset")
    return mailbox


def delete_mailbox(mailbox_id: int, *, backend=None, actor=None) -> Mailbox:
    mailbox = _mailbox_for_lifecycle(mailbox_id)
    if mailbox.status not in {Mailbox.Status.ACTIVE, Mailbox.Status.SUSPENDED}:
        raise MailboxLifecycleError("This mailbox cannot be deleted in its current state.")

    resolved_backend = backend or get_mail_backend()
    resolved_backend.delete_account(account_id=mailbox.backend_identifier)
    Mailbox.objects.filter(pk=mailbox.pk).update(status=Mailbox.Status.DELETED)
    mailbox.refresh_from_db()
    _audit_mailbox(
        mailbox,
        actor=actor,
        action="mailbox.deleted",
        metadata={"backend_identifier": mailbox.backend_identifier},
    )
    return mailbox
