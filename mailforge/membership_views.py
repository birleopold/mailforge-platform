from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.tenants.models import TenantInvitation, TenantMembership
from apps.tenants.services import (
    MEMBERSHIP_MANAGE_ROLES,
    TenantMembershipError,
    accept_tenant_invitation,
    change_membership_role,
    create_tenant_invitation,
    get_active_invitation,
    remove_tenant_membership,
    revoke_tenant_invitation,
    send_tenant_invitation_email,
)
from mailforge.forms import InvitationSignupForm, TenantInvitationForm, TenantMembershipRoleForm


User = get_user_model()


def _membership_or_404(user, tenant_slug):
    membership = (
        TenantMembership.objects.select_related("tenant")
        .filter(user=user, tenant__slug=tenant_slug)
        .first()
    )
    if membership is None:
        raise Http404
    return membership


def _members_redirect(tenant_slug):
    return redirect("portal-members", tenant_slug=tenant_slug)


@login_required
def member_management(request, tenant_slug):
    membership = _membership_or_404(request.user, tenant_slug)
    tenant = membership.tenant
    members = tenant.memberships.select_related("user").order_by("role", "user__username")
    pending_invitations = tenant.invitations.filter(
        accepted_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).select_related("invited_by")
    return render(
        request,
        "portal/members.html",
        {
            "tenant": tenant,
            "membership": membership,
            "members": members,
            "pending_invitations": pending_invitations,
            "invite_form": TenantInvitationForm(),
            "role_form": TenantMembershipRoleForm(),
            "can_invite": membership.role in MEMBERSHIP_MANAGE_ROLES,
            "can_manage_roles": membership.role == TenantMembership.Role.OWNER,
        },
    )


@login_required
@require_POST
def tenant_invite(request, tenant_slug):
    membership = _membership_or_404(request.user, tenant_slug)
    form = TenantInvitationForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid email address and member role.")
        return _members_redirect(tenant_slug)

    try:
        result = create_tenant_invitation(
            membership.tenant.pk,
            email=form.cleaned_data["email"],
            role=form.cleaned_data["role"],
            actor=request.user,
            expires_hours=settings.MAILFORGE_INVITATION_HOURS,
        )
    except TenantMembershipError as exc:
        messages.error(request, str(exc))
        return _members_redirect(tenant_slug)

    accept_path = reverse("tenant-invitation", kwargs={"token": result.token})
    accept_url = request.build_absolute_uri(accept_path)
    try:
        send_tenant_invitation_email(result.invitation, accept_url=accept_url)
    except Exception:
        revoke_tenant_invitation(result.invitation.pk, actor=request.user)
        messages.error(
            request,
            "The invitation was not sent and was revoked. Check the portal email settings and try again.",
        )
    else:
        messages.success(request, f"Invitation sent to {result.invitation.email}.")
    return _members_redirect(tenant_slug)


@login_required
@require_POST
def invitation_revoke(request, tenant_slug, invitation_pk):
    membership = _membership_or_404(request.user, tenant_slug)
    invitation = get_object_or_404(
        TenantInvitation,
        pk=invitation_pk,
        tenant=membership.tenant,
    )
    try:
        revoke_tenant_invitation(invitation.pk, actor=request.user)
    except TenantMembershipError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Invitation for {invitation.email} revoked.")
    return _members_redirect(tenant_slug)


@login_required
@require_POST
def membership_role_update(request, tenant_slug, membership_pk):
    actor_membership = _membership_or_404(request.user, tenant_slug)
    target = get_object_or_404(
        TenantMembership.objects.select_related("user"),
        pk=membership_pk,
        tenant=actor_membership.tenant,
    )
    form = TenantMembershipRoleForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a valid member role.")
        return _members_redirect(tenant_slug)
    try:
        updated = change_membership_role(
            target.pk,
            role=form.cleaned_data["role"],
            actor=request.user,
        )
    except TenantMembershipError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Role updated for {updated.user.get_username()}.")
    return _members_redirect(tenant_slug)


@login_required
@require_POST
def membership_remove(request, tenant_slug, membership_pk):
    actor_membership = _membership_or_404(request.user, tenant_slug)
    target = get_object_or_404(
        TenantMembership.objects.select_related("user"),
        pk=membership_pk,
        tenant=actor_membership.tenant,
    )
    username = target.user.get_username()
    try:
        remove_tenant_membership(target.pk, actor=request.user)
    except TenantMembershipError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{username} removed from the organization.")
    return _members_redirect(tenant_slug)


def tenant_invitation(request, token):
    try:
        invitation = get_active_invitation(token)
    except TenantMembershipError as exc:
        return render(
            request,
            "registration/invitation.html",
            {"invitation_error": str(exc)},
            status=410,
        )

    if request.user.is_authenticated:
        if (request.user.email or "").strip().lower() != invitation.email:
            return render(
                request,
                "registration/invitation.html",
                {
                    "invitation": invitation,
                    "invitation_error": (
                        "This invitation belongs to a different email address. "
                        "Sign out and use the invited account."
                    ),
                },
                status=403,
            )
        if request.method == "POST":
            try:
                membership = accept_tenant_invitation(token, user=request.user)
            except TenantMembershipError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"You joined {membership.tenant.name}.")
                return redirect("portal-tenant", tenant_slug=membership.tenant.slug)
        return render(request, "registration/invitation.html", {"invitation": invitation})

    existing_user = User.objects.filter(email__iexact=invitation.email).exists()
    if existing_user:
        login_url = reverse("login")
        next_url = request.get_full_path()
        return render(
            request,
            "registration/invitation.html",
            {
                "invitation": invitation,
                "login_url": f"{login_url}?{urlencode({'next': next_url})}",
            },
        )

    form = InvitationSignupForm(request.POST or None, initial={"username": invitation.email})
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.create_user(email=invitation.email)
                membership = accept_tenant_invitation(token, user=user)
        except TenantMembershipError as exc:
            form.add_error(None, str(exc))
        else:
            auth_login(request, user)
            messages.success(request, f"Account created. You joined {membership.tenant.name}.")
            return redirect("portal-tenant", tenant_slug=membership.tenant.slug)

    return render(
        request,
        "registration/invitation.html",
        {"invitation": invitation, "signup_form": form},
    )
