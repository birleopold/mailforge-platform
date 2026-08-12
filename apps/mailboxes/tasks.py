from celery import shared_task

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def provision_mailbox(self, mailbox_id):
    # Must be idempotent:
    # - lock/read current mailbox state
    # - skip if already ACTIVE and backend object exists
    # - provision via MailBackend adapter
    # - persist backend identifier
    # - append AuditEvent
    return {"mailbox_id": mailbox_id, "status": "not_implemented"}
