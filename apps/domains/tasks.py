from celery import shared_task

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def verify_domain_ownership(self, domain_id):
    # TODO:
    # 1. load Domain
    # 2. resolve TXT for domain.verification_record_name
    # 3. compare exact token
    # 4. update status/verified_at transactionally
    # 5. create an AuditEvent
    return {"domain_id": domain_id, "status": "not_implemented"}
