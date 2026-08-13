from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.domains.lifecycle import DomainLifecycleError, reactivate_domain, suspend_domain
from apps.tenants.lifecycle import reactivate_tenant, suspend_tenant
from apps.tenants.models import TenantMembership
from apps.tenants.services import TenantMembershipError


MANAGE_ROLES = {TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN}


def _membership_or_404(user, tenant_slug):
    membership = (
        TenantMembership.objects.select_related("tenant")
        .filter(user=user, tenant__slug=tenant_slug)
        .first()
    )
    if membership is None:
        raise Http404
    return membership


@login_required
@require_POST
def tenant_suspend(request, tenant_slug):
    membership = _membership_or_404(request.user, tenant_slug)
    try:
        result = suspend_tenant(membership.tenant.pk, actor=request.user)
    except TenantMembershipError as exc:
        messages.error(request, str(exc))
    else:
        if result.success:
            messages.success(request, "Organization emergency suspension is fully enforced.")
        else:
            messages.warning(
                request,
                "Organization is suspended in MailForge, but backend enforcement needs retry for: "
                + ", ".join(result.failed_domains),
            )
    return redirect("portal-tenant", tenant_slug=tenant_slug)


@login_required
@require_POST
def tenant_reactivate(request, tenant_slug):
    membership = _membership_or_404(request.user, tenant_slug)
    try:
        result = reactivate_tenant(membership.tenant.pk, actor=request.user)
    except TenantMembershipError as exc:
        messages.error(request, str(exc))
    else:
        if result.success:
            messages.success(
                request,
                "Organization reactivated. Each domain is again governed by normal DNS readiness.",
            )
        else:
            messages.error(
                request,
                "Organization remains suspended because these domains could not be safely restored: "
                + ", ".join(result.failed_domains),
            )
    return redirect("portal-tenant", tenant_slug=tenant_slug)


@login_required
@require_POST
def domain_suspend(request, tenant_slug, domain_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    if membership.role not in MANAGE_ROLES:
        messages.error(request, "Only owners and administrators can suspend domains.")
        return redirect("portal-domain", tenant_slug=tenant_slug, domain_pk=domain_pk)
    domain = get_object_or_404(membership.tenant.domains, pk=domain_pk)
    try:
        result = suspend_domain(domain.pk, actor=request.user)
    except DomainLifecycleError as exc:
        messages.error(request, str(exc))
    else:
        if result.success:
            messages.success(request, f"Emergency suspension enforced for {domain.name}.")
        else:
            messages.warning(
                request,
                "Domain is suspended in MailForge, but retry backend enforcement for: "
                + ", ".join(result.failed_addresses),
            )
    return redirect("portal-domain", tenant_slug=tenant_slug, domain_pk=domain.pk)


@login_required
@require_POST
def domain_reactivate(request, tenant_slug, domain_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    if membership.role not in MANAGE_ROLES:
        messages.error(request, "Only owners and administrators can reactivate domains.")
        return redirect("portal-domain", tenant_slug=tenant_slug, domain_pk=domain_pk)
    domain = get_object_or_404(membership.tenant.domains, pk=domain_pk)
    try:
        result = reactivate_domain(domain.pk, actor=request.user)
    except DomainLifecycleError as exc:
        messages.error(request, str(exc))
    else:
        if result.success:
            messages.success(
                request,
                f"{domain.name} reactivated. DNS readiness now controls outbound sending.",
            )
        else:
            messages.error(
                request,
                "Domain remains suspended because mailbox permissions could not be safely restored: "
                + ", ".join(result.failed_addresses),
            )
    return redirect("portal-domain", tenant_slug=tenant_slug, domain_pk=domain.pk)
