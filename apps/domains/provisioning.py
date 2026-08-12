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


def _domain_dns_zone_file(backend, backend_identifier: str) -> str:
    getter = getattr(backend, "get_domain", None)
    if getter is None:
        return ""
    try:
        snapshot = getter(backend_identifier)
    except Exception:
        # DNS expectation discovery is useful metadata, but must not turn a successfully
        # created mail domain into a failed provisioning transaction.
        return ""
    return str(snapshot.get("dnsZoneFile") or "")


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

    dns_zone_file = _domain_dns_zone_file(backend, backend_identifier)

    with transaction.atomic():
        locked = Domain.objects.select_for_update().select_related("tenant").get(pk=domain_id)
        locked.backend = "stalwart"
        locked.backend_identifier = backend_identifier
        locked.dns_zone_file = dns_zone_file
        locked.status = Domain.Status.DNS_CONFIGURATION
        locked.save(
            update_fields=["backend", "backend_identifier", "dns_zone_file", "status"]
        )
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
                "dns_zone_discovered": bool(dns_zone_file),
            },
        )

    return DomainProvisioningResult(backend_identifier)
