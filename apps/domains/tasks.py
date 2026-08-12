from celery import shared_task

from apps.domains.dns_readiness import check_domain_dns
from apps.domains.models import Domain
from apps.domains.services import (
    DomainVerificationTemporaryError,
    verify_domain_and_record,
)


@shared_task(
    bind=True,
    autoretry_for=(DomainVerificationTemporaryError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def verify_domain_ownership(self, domain_id):
    result = verify_domain_and_record(domain_id)
    return {
        "domain_id": domain_id,
        "verified": result.verified,
        "already_verified": result.already_verified,
        "observed_values": list(result.observed_values),
    }


@shared_task
def reconcile_domain_readiness(domain_id):
    result = check_domain_dns(domain_id)
    domain = Domain.objects.only("status", "sending_enabled").get(pk=domain_id)
    return {
        "domain_id": domain_id,
        "ready": result.ready,
        "status": domain.status,
        "sending_enabled": domain.sending_enabled,
        "checks": {
            name: check.get("status")
            for name, check in result.checks.items()
        },
    }


@shared_task
def reconcile_all_domain_readiness():
    domain_ids = list(
        Domain.objects.exclude(backend_identifier="")
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    for domain_id in domain_ids:
        reconcile_domain_readiness.delay(domain_id)
    return {"queued": len(domain_ids), "domain_ids": domain_ids}
