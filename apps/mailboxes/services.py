from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from apps.mailboxes.models import Alias, Mailbox, normalize_local_part
from integrations.factory import get_mail_backend


class MailboxProvisioningError(RuntimeError):
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
