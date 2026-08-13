from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.audit.models import AuditEvent
from apps.domains.dns_readiness import check_domain_dns
from apps.domains.lifecycle import reactivate_domain, suspend_domain
from apps.domains.models import Domain
from apps.tenants.models import Tenant, TenantMembership
from apps.tenants.services import TenantMembershipError


@dataclass(frozen=True)
class TenantSuspensionResult:
    tenant: Tenant
    success: bool
    failed_domains: tuple[str, ...] = ()


def _require_owner(tenant: Tenant, actor):
    membership = TenantMembership.objects.filter(tenant=tenant, user=actor).first()
    if membership is None or membership.role != TenantMembership.Role.OWNER:
        raise TenantMembershipError("Only the organization owner can use emergency suspension controls.")


def suspend_tenant(tenant_id: int, *, actor, backend=None) -> TenantSuspensionResult:
    tenant = Tenant.objects.get(pk=tenant_id)
    _require_owner(tenant, actor)

    with transaction.atomic():
        locked = Tenant.objects.select_for_update().get(pk=tenant_id)
        changed = locked.status != Tenant.Status.SUSPENDED
        locked.status = Tenant.Status.SUSPENDED
        locked.save(update_fields=["status"])
        if changed:
            AuditEvent.objects.create(
                tenant=locked,
                actor=actor,
                action="tenant.emergency_suspended",
                target_type="tenant",
                target_id=str(locked.pk),
                metadata={"tenant": locked.slug},
            )

    failures = []
    domains = tenant.domains.exclude(status=Domain.Status.DECOMMISSIONED).order_by("name")
    for domain in domains:
        try:
            result = suspend_domain(domain.pk, actor=actor, backend=backend)
        except Exception:
            failures.append(domain.name)
        else:
            if not result.success:
                failures.append(domain.name)

    tenant.refresh_from_db()
    return TenantSuspensionResult(
        tenant=tenant,
        success=not failures,
        failed_domains=tuple(failures),
    )


def reactivate_tenant(
    tenant_id: int,
    *,
    actor,
    backend=None,
    resolver=None,
) -> TenantSuspensionResult:
    tenant = Tenant.objects.get(pk=tenant_id)
    _require_owner(tenant, actor)
    if tenant.status != Tenant.Status.SUSPENDED:
        return TenantSuspensionResult(tenant=tenant, success=True)

    failures = []
    restored_domains = []
    suspended_domains = list(
        tenant.domains.filter(status=Domain.Status.SUSPENDED).order_by("name")
    )
    for domain in suspended_domains:
        try:
            result = reactivate_domain(
                domain.pk,
                actor=actor,
                backend=backend,
                resolver=resolver,
                allow_suspended_tenant=True,
                run_dns_check=False,
            )
        except Exception:
            failures.append(domain.name)
        else:
            if result.success:
                restored_domains.append(result.domain)
            else:
                failures.append(domain.name)

    if failures:
        for domain in restored_domains:
            try:
                suspend_domain(domain.pk, actor=actor, backend=backend)
            except Exception:
                if domain.name not in failures:
                    failures.append(domain.name)
        tenant.refresh_from_db()
        return TenantSuspensionResult(
            tenant=tenant,
            success=False,
            failed_domains=tuple(failures),
        )

    with transaction.atomic():
        locked = Tenant.objects.select_for_update().get(pk=tenant_id)
        locked.status = Tenant.Status.ACTIVE
        locked.save(update_fields=["status"])
        AuditEvent.objects.create(
            tenant=locked,
            actor=actor,
            action="tenant.emergency_reactivated",
            target_type="tenant",
            target_id=str(locked.pk),
            metadata={"tenant": locked.slug},
        )

    for domain in tenant.domains.exclude(status=Domain.Status.DECOMMISSIONED).filter(
        backend_identifier__gt=""
    ):
        check_domain_dns(domain.pk, actor=actor, resolver=resolver, backend=backend)

    tenant.refresh_from_db()
    return TenantSuspensionResult(tenant=tenant, success=True)
