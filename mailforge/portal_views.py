from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import AuditEvent
from apps.domains.dns_readiness import check_domain_dns
from apps.domains.models import Domain
from apps.domains.provisioning import DomainProvisioningError, provision_domain
from apps.domains.services import DomainVerificationTemporaryError, verify_domain_and_record
from apps.mailboxes.forwarders import ForwarderProvisioningError, provision_forwarder
from apps.mailboxes.models import Mailbox
from apps.mailboxes.services import (
    MailboxLifecycleError,
    MailboxProvisioningError,
    delete_mailbox,
    provision_mailbox,
    reactivate_mailbox,
    reset_mailbox_password,
    suspend_mailbox,
)
from apps.tenants.models import TenantMembership
from apps.tenants.services import create_tenant
from integrations.factory import MailBackendConfigurationError, UnsupportedMailBackend
from integrations.stalwart.client import StalwartAPIError
from mailforge.forms import (
    DomainCreateForm,
    ForwarderCreateForm,
    MailboxCreateForm,
    MailboxDeleteForm,
    MailboxPasswordResetForm,
    TenantCreateForm,
)


MANAGE_ROLES = {TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN}
BACKEND_ERRORS = (MailBackendConfigurationError, UnsupportedMailBackend, StalwartAPIError)


def _membership_or_404(user, tenant_slug):
    membership = (
        TenantMembership.objects.select_related("tenant")
        .filter(user=user, tenant__slug=tenant_slug)
        .first()
    )
    if membership is None:
        raise Http404
    return membership


def _require_manager(membership):
    if membership.role not in MANAGE_ROLES:
        raise PermissionDenied


def _portal_mailbox(membership, domain_pk, mailbox_pk):
    domain = get_object_or_404(membership.tenant.domains, pk=domain_pk)
    mailbox = get_object_or_404(
        domain.mailboxes.exclude(status=Mailbox.Status.DELETED),
        pk=mailbox_pk,
    )
    return domain, mailbox


def _domain_redirect(tenant_slug, domain_pk):
    return redirect("portal-domain", tenant_slug=tenant_slug, domain_pk=domain_pk)


@login_required
def dashboard(request):
    memberships = (
        TenantMembership.objects.select_related("tenant")
        .filter(user=request.user)
        .order_by("tenant__name")
    )
    return render(
        request,
        "portal/dashboard.html",
        {"memberships": memberships, "tenant_form": TenantCreateForm()},
    )


@login_required
@require_POST
def tenant_create(request):
    form = TenantCreateForm(request.POST)
    if form.is_valid():
        tenant = create_tenant(name=form.cleaned_data["name"], owner=request.user)
        messages.success(request, f"Organization {tenant.name} created.")
        return redirect("portal-tenant", tenant_slug=tenant.slug)
    messages.error(request, "Please enter a valid organization name.")
    return redirect("dashboard")


@login_required
def tenant_detail(request, tenant_slug):
    membership = _membership_or_404(request.user, tenant_slug)
    tenant = membership.tenant
    return render(
        request,
        "portal/tenant.html",
        {
            "membership": membership,
            "tenant": tenant,
            "domains": tenant.domains.order_by("name"),
            "domain_form": DomainCreateForm(),
            "can_manage": membership.role in MANAGE_ROLES,
        },
    )


@login_required
@require_POST
def domain_create(request, tenant_slug):
    membership = _membership_or_404(request.user, tenant_slug)
    _require_manager(membership)
    form = DomainCreateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid fully-qualified domain name.")
        return redirect("portal-tenant", tenant_slug=tenant_slug)

    try:
        domain = Domain.objects.create(
            tenant=membership.tenant,
            name=form.cleaned_data["name"],
            backend="stalwart",
        )
    except IntegrityError:
        messages.error(request, "That domain is already registered in MailForge.")
        return redirect("portal-tenant", tenant_slug=tenant_slug)

    AuditEvent.objects.create(
        tenant=membership.tenant,
        actor=request.user,
        action="domain.created",
        target_type="domain",
        target_id=str(domain.pk),
        metadata={"domain": domain.name},
    )
    messages.success(request, f"Domain {domain.name} added. Add the TXT record to verify ownership.")
    return redirect("portal-domain", tenant_slug=tenant_slug, domain_pk=domain.pk)


@login_required
def domain_detail(request, tenant_slug, domain_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    domain = get_object_or_404(membership.tenant.domains, pk=domain_pk)
    mailboxes = domain.mailboxes.exclude(status=Mailbox.Status.DELETED).order_by("local_part")
    forwarders = domain.aliases.filter(active=True).order_by("local_part")
    return render(
        request,
        "portal/domain.html",
        {
            "membership": membership,
            "tenant": membership.tenant,
            "domain": domain,
            "mailboxes": mailboxes,
            "forwarders": forwarders,
            "mailbox_form": MailboxCreateForm(),
            "password_reset_form": MailboxPasswordResetForm(),
            "forwarder_form": ForwarderCreateForm(),
            "can_manage": membership.role in MANAGE_ROLES,
        },
    )


@login_required
@require_POST
def domain_verify(request, tenant_slug, domain_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    _require_manager(membership)
    domain = get_object_or_404(membership.tenant.domains, pk=domain_pk)
    try:
        result = verify_domain_and_record(domain.pk)
    except DomainVerificationTemporaryError:
        messages.error(request, "DNS verification is temporarily unavailable. Try again shortly.")
    else:
        if result.verified:
            messages.success(request, "Domain ownership verified.")
        else:
            messages.warning(request, "The verification TXT record is not visible yet.")
    return _domain_redirect(tenant_slug, domain.pk)


@login_required
@require_POST
def domain_provision(request, tenant_slug, domain_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    _require_manager(membership)
    domain = get_object_or_404(membership.tenant.domains, pk=domain_pk)
    try:
        provision_domain(domain.pk, actor=request.user)
    except DomainProvisioningError as exc:
        messages.error(request, str(exc))
    except BACKEND_ERRORS:
        messages.error(request, "Stalwart is not configured or is temporarily unavailable.")
    else:
        messages.success(request, "Domain provisioned in Stalwart.")
    return _domain_redirect(tenant_slug, domain.pk)


@login_required
@require_POST
def domain_dns_check(request, tenant_slug, domain_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    _require_manager(membership)
    domain = get_object_or_404(membership.tenant.domains, pk=domain_pk)
    result = check_domain_dns(domain.pk, actor=request.user)
    if result.ready:
        messages.success(request, "Required DNS records and backend sending policy are healthy.")
    else:
        messages.warning(request, "Domain readiness is not fully healthy yet. Review the checks below.")
    return _domain_redirect(tenant_slug, domain.pk)


@login_required
@require_POST
def mailbox_create(request, tenant_slug, domain_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    _require_manager(membership)
    domain = get_object_or_404(membership.tenant.domains, pk=domain_pk)
    form = MailboxCreateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please correct the mailbox details and password requirements.")
        return _domain_redirect(tenant_slug, domain.pk)

    try:
        result = provision_mailbox(
            domain.pk,
            local_part=form.cleaned_data["local_part"],
            password=form.cleaned_data["password"],
            display_name=form.cleaned_data.get("display_name", ""),
            quota_mb=form.cleaned_data.get("quota_mb"),
            actor=request.user,
        )
    except MailboxProvisioningError as exc:
        messages.error(request, str(exc))
    except BACKEND_ERRORS:
        messages.error(request, "Stalwart is not configured or is temporarily unavailable.")
    else:
        messages.success(request, f"Mailbox {result.mailbox.email_address} created.")
    return _domain_redirect(tenant_slug, domain.pk)


@login_required
@require_POST
def mailbox_suspend(request, tenant_slug, domain_pk, mailbox_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    _require_manager(membership)
    domain, mailbox = _portal_mailbox(membership, domain_pk, mailbox_pk)
    try:
        suspend_mailbox(mailbox.pk, actor=request.user)
    except MailboxLifecycleError as exc:
        messages.error(request, str(exc))
    except BACKEND_ERRORS:
        messages.error(request, "Stalwart is temporarily unavailable; mailbox state was not changed.")
    else:
        messages.success(request, f"Mailbox {mailbox.email_address} suspended.")
    return _domain_redirect(tenant_slug, domain.pk)


@login_required
@require_POST
def mailbox_reactivate(request, tenant_slug, domain_pk, mailbox_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    _require_manager(membership)
    domain, mailbox = _portal_mailbox(membership, domain_pk, mailbox_pk)
    try:
        reactivate_mailbox(mailbox.pk, actor=request.user)
    except MailboxLifecycleError as exc:
        messages.error(request, str(exc))
    except BACKEND_ERRORS:
        messages.error(request, "Stalwart is temporarily unavailable; mailbox state was not changed.")
    else:
        messages.success(request, f"Mailbox {mailbox.email_address} reactivated.")
    return _domain_redirect(tenant_slug, domain.pk)


@login_required
@require_POST
def mailbox_password_reset(request, tenant_slug, domain_pk, mailbox_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    _require_manager(membership)
    domain, mailbox = _portal_mailbox(membership, domain_pk, mailbox_pk)
    form = MailboxPasswordResetForm(request.POST)
    if not form.is_valid():
        messages.error(request, "The new password does not meet the password requirements.")
        return _domain_redirect(tenant_slug, domain.pk)
    try:
        reset_mailbox_password(
            mailbox.pk,
            password=form.cleaned_data["password"],
            actor=request.user,
        )
    except MailboxLifecycleError as exc:
        messages.error(request, str(exc))
    except BACKEND_ERRORS:
        messages.error(request, "Stalwart is temporarily unavailable; the password was not changed.")
    else:
        messages.success(request, f"Password reset for {mailbox.email_address}.")
    return _domain_redirect(tenant_slug, domain.pk)


@login_required
@require_POST
def mailbox_delete(request, tenant_slug, domain_pk, mailbox_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    _require_manager(membership)
    domain, mailbox = _portal_mailbox(membership, domain_pk, mailbox_pk)
    form = MailboxDeleteForm(request.POST, expected_email=mailbox.email_address)
    if not form.is_valid():
        messages.error(request, "Mailbox deletion confirmation did not match the address.")
        return _domain_redirect(tenant_slug, domain.pk)
    try:
        delete_mailbox(mailbox.pk, actor=request.user)
    except MailboxLifecycleError as exc:
        messages.error(request, str(exc))
    except BACKEND_ERRORS:
        messages.error(request, "Stalwart is temporarily unavailable; the mailbox was not deleted.")
    else:
        messages.success(request, f"Mailbox {mailbox.email_address} deleted and address reserved.")
    return _domain_redirect(tenant_slug, domain.pk)


@login_required
@require_POST
def forwarder_create(request, tenant_slug, domain_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    _require_manager(membership)
    domain = get_object_or_404(membership.tenant.domains, pk=domain_pk)
    form = ForwarderCreateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please correct the forwarder details and try again.")
        return _domain_redirect(tenant_slug, domain.pk)

    try:
        result = provision_forwarder(
            domain.pk,
            local_part=form.cleaned_data["local_part"],
            destinations=form.cleaned_data["destinations"],
            actor=request.user,
        )
    except ForwarderProvisioningError as exc:
        messages.error(request, str(exc))
    except BACKEND_ERRORS:
        messages.error(request, "Stalwart is not configured or is temporarily unavailable.")
    else:
        messages.success(request, f"Forwarder {result.alias.email_address} created.")
    return _domain_redirect(tenant_slug, domain.pk)
