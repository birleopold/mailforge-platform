from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.audit.models import AuditEvent
from apps.domains.dns_readiness import check_domain_dns
from apps.domains.models import Domain
from apps.mailboxes.models import Mailbox
from integrations.factory import get_mail_backend


class DomainLifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class DomainSuspensionResult:
    domain: Domain
    success: bool
    failed_addresses: tuple[str, ...] = ()


def _active_backend_mailboxes(domain: Domain):
    return list(
        domain.mailboxes.filter(status=Mailbox.Status.ACTIVE)
        .exclude(backend_identifier="")
        .order_by("local_part")
    )


def _suspension_setter(backend):
    setter = getattr(backend, "set_account_suspended", None)
    if setter is None:
        raise DomainLifecycleError(
            "The configured mail backend cannot enforce emergency mailbox suspension."
        )
    return setter


def suspend_domain(domain_id: int, *, actor=None, backend=None) -> DomainSuspensionResult:
    domain = Domain.objects.select_related("tenant").get(pk=domain_id)
    if domain.status == Domain.Status.DECOMMISSIONED:
        raise DomainLifecycleError("A decommissioned domain cannot be suspended.")

    mailboxes = _active_backend_mailboxes(domain)
    failures = []
    if mailboxes:
        backend = backend or get_mail_backend()
        setter = _suspension_setter(backend)
        for mailbox in mailboxes:
            try:
                setter(
                    account_id=mailbox.backend_identifier,
                    suspended=True,
                    sending_enabled=False,
                )
            except Exception:
                failures.append(mailbox.email_address)

    with transaction.atomic():
        locked = Domain.objects.select_for_update().select_related("tenant").get(pk=domain_id)
        checks = dict(locked.dns_checks or {})
        checks["emergency_suspension"] = {
            "status": "pass" if not failures else "fail",
            "required": True,
            "expected": "All active Stalwart mailbox permissions suspended",
            "observed": failures,
            "detail": (
                "Emergency suspension is enforced for all active provisioned mailboxes."
                if not failures
                else "Emergency suspension could not be confirmed for: " + ", ".join(failures)
            ),
        }
        changed = locked.status != Domain.Status.SUSPENDED or locked.sending_enabled
        locked.status = Domain.Status.SUSPENDED
        locked.sending_enabled = False
        locked.dns_checks = checks
        locked.save(update_fields=["status", "sending_enabled", "dns_checks"])
        if changed or failures:
            AuditEvent.objects.create(
                tenant=locked.tenant,
                actor=actor,
                action="domain.emergency_suspended",
                target_type="domain",
                target_id=str(locked.pk),
                metadata={
                    "domain": locked.name,
                    "backend_enforced": not failures,
                    "failed_addresses": failures,
                },
            )

    domain.refresh_from_db()
    return DomainSuspensionResult(
        domain=domain,
        success=not failures,
        failed_addresses=tuple(failures),
    )


def reactivate_domain(
    domain_id: int,
    *,
    actor=None,
    backend=None,
    resolver=None,
    allow_suspended_tenant: bool = False,
    run_dns_check: bool = True,
) -> DomainSuspensionResult:
    domain = Domain.objects.select_related("tenant").get(pk=domain_id)
    if domain.status == Domain.Status.DECOMMISSIONED:
        raise DomainLifecycleError("A decommissioned domain cannot be reactivated.")
    if domain.tenant.status == domain.tenant.Status.SUSPENDED and not allow_suspended_tenant:
        raise DomainLifecycleError("Reactivate the organization before reactivating this domain.")
    if domain.status != Domain.Status.SUSPENDED:
        return DomainSuspensionResult(domain=domain, success=True)

    mailboxes = _active_backend_mailboxes(domain)
    failures = []
    restored = []
    if mailboxes:
        backend = backend or get_mail_backend()
        setter = _suspension_setter(backend)
        for mailbox in mailboxes:
            try:
                setter(
                    account_id=mailbox.backend_identifier,
                    suspended=False,
                    sending_enabled=False,
                )
                restored.append(mailbox)
            except Exception:
                failures.append(mailbox.email_address)

        if failures:
            for mailbox in restored:
                try:
                    setter(
                        account_id=mailbox.backend_identifier,
                        suspended=True,
                        sending_enabled=False,
                    )
                except Exception:
                    if mailbox.email_address not in failures:
                        failures.append(mailbox.email_address)
            return DomainSuspensionResult(
                domain=domain,
                success=False,
                failed_addresses=tuple(failures),
            )

    with transaction.atomic():
        locked = Domain.objects.select_for_update().select_related("tenant").get(pk=domain_id)
        if locked.backend_identifier:
            locked.status = Domain.Status.DNS_CONFIGURATION
        elif locked.verified_at:
            locked.status = Domain.Status.VERIFIED
        else:
            locked.status = Domain.Status.PENDING_VERIFICATION
        locked.sending_enabled = False
        checks = dict(locked.dns_checks or {})
        checks["emergency_suspension"] = {
            "status": "pass",
            "required": False,
            "expected": "Emergency suspension cleared",
            "observed": [],
            "detail": "Emergency mailbox suspension has been cleared; normal readiness rules apply.",
        }
        locked.dns_checks = checks
        locked.save(update_fields=["status", "sending_enabled", "dns_checks"])
        AuditEvent.objects.create(
            tenant=locked.tenant,
            actor=actor,
            action="domain.emergency_reactivated",
            target_type="domain",
            target_id=str(locked.pk),
            metadata={"domain": locked.name},
        )

    if domain.backend_identifier and run_dns_check:
        check_domain_dns(domain_id, actor=actor, resolver=resolver, backend=backend)

    domain.refresh_from_db()
    return DomainSuspensionResult(domain=domain, success=True)
