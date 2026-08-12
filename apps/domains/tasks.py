from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from apps.domains.services import (
    DomainOwnershipVerifier,
    DomainVerificationTemporaryError,
)


@shared_task(
    bind=True,
    autoretry_for=(DomainVerificationTemporaryError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def verify_domain_ownership(self, domain_id):
    domain = Domain.objects.get(pk=domain_id)

    if domain.verified_at is not None:
        return {"domain_id": domain_id, "verified": True, "already_verified": True}

    result = DomainOwnershipVerifier().verify(domain)
    if not result.verified:
        return {
            "domain_id": domain_id,
            "verified": False,
            "observed_values": list(result.observed_values),
        }

    with transaction.atomic():
        locked = Domain.objects.select_for_update().get(pk=domain_id)
        if locked.verified_at is None:
            locked.status = Domain.Status.VERIFIED
            locked.verified_at = timezone.now()
            locked.save(update_fields=["status", "verified_at"])
            AuditEvent.objects.create(
                tenant=locked.tenant,
                action="domain.ownership_verified",
                target_type="domain",
                target_id=str(locked.pk),
                metadata={
                    "domain": locked.name,
                    "record_name": locked.verification_record_name,
                },
            )

    return {"domain_id": domain_id, "verified": True}
