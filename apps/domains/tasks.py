from celery import shared_task

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
