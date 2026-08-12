from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from integrations.factory import get_mail_backend


class DomainProvisioningError(RuntimeError):
    pass


@dataclass(frozen=True)
class DomainProvisioningResult:
    backend_identifier: str
    already_provisioned: bool = False


def provision_domain(domain_id: int, *, backend=None, actor=None) -> DomainProvisioningResult:
    domain = Domain.objects.select_related("tenant").get(pk=domain_id)
    if domain.verified_at is None:
        raise DomainProvisioningError("Domain ownership must be verified before provisioning.")
    if domain.backend_identifier:
        return DomainProvisioningResult(domain.backend_identifier, already_provisioned=True)

    backend = backend or get_mail_backend()

    with transaction.atomic():
        locked = Domain.objects.select_for_update().select_related("tenant").get(pk=domain_id)
        if locked.backend_identifier:
            return DomainProvisioningResult(
                locked.backend_identifier,
                already_provisioned=True,
            )
        locked.status = Domain.Status.PROVISIONING
        locked.save(update_fields=["status"])

    try:
        created = backend.create_domain(
            domain=domain.name,
            max_mailboxes=settings.MAILFORGE_DEFAULT_MAX_MAILBOXES,
            quota_mb=settings.MAILFORGE_DEFAULT_DOMAIN_QUOTA_MB,
        )
        backend_identifier = str(created["id"])
    except Exception:
        Domain.objects.filter(pk=domain_id).update(status=Domain.Status.VERIFIED)
        raise

    with transaction.atomic():
        locked = Domain.objects.select_for_update().select_related("tenant").get(pk=domain_id)
        locked.backend = "stalwart"
        locked.backend_identifier = backend_identifier
        locked.status = Domain.Status.DNS_CONFIGURATION
        locked.save(update_fields=["backend", "backend_identifier", "status"])
        AuditEvent.objects.create(
            tenant=locked.tenant,
            actor=actor,
            action="domain.provisioned",
            target_type="domain",
            target_id=str(locked.pk),
            metadata={
                "domain": locked.name,
                "backend": locked.backend,
                "backend_identifier": backend_identifier,
            },
        )

    return DomainProvisioningResult(backend_identifier)
