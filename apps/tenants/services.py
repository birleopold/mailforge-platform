from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.audit.models import AuditEvent
from apps.tenants.models import Tenant, TenantInvitation, TenantMembership


INVITABLE_ROLES = {
    TenantMembership.Role.ADMIN,
    TenantMembership.Role.BILLING,
    TenantMembership.Role.VIEWER,
}
MEMBERSHIP_MANAGE_ROLES = {
    TenantMembership.Role.OWNER,
    TenantMembership.Role.ADMIN,
}


class TenantMembershipError(RuntimeError):
    pass


@dataclass(frozen=True)
class TenantInvitationResult:
    invitation: TenantInvitation
    token: str


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def invitation_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _actor_membership(tenant: Tenant, actor) -> TenantMembership:
    membership = TenantMembership.objects.filter(tenant=tenant, user=actor).first()
    if membership is None:
        raise TenantMembershipError("You are not a member of this organization.")
    return membership


@transaction.atomic
def create_tenant(*, name: str, owner) -> Tenant:
    clean_name = name.strip()
    base = slugify(clean_name)[:45] or "tenant"
    slug = base
    while Tenant.objects.filter(slug=slug).exists():
        slug = f"{base}-{uuid4().hex[:6]}"

    tenant = Tenant.objects.create(
        name=clean_name,
        slug=slug,
        kind=Tenant.Kind.CUSTOMER,
        status=Tenant.Status.ACTIVE,
        plan_code="free",
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=owner,
        role=TenantMembership.Role.OWNER,
    )
    AuditEvent.objects.create(
        tenant=tenant,
        actor=owner,
        action="tenant.created",
        target_type="tenant",
        target_id=str(tenant.pk),
        metadata={"name": tenant.name, "slug": tenant.slug},
    )
    return tenant


@transaction.atomic
def create_tenant_invitation(
    tenant_id: int,
    *,
    email: str,
    role: str,
    actor,
    expires_hours: int = 72,
) -> TenantInvitationResult:
    tenant = Tenant.objects.select_for_update().get(pk=tenant_id)
    actor_membership = _actor_membership(tenant, actor)
    if actor_membership.role not in MEMBERSHIP_MANAGE_ROLES:
        raise TenantMembershipError("Only owners and administrators can invite members.")
    if role not in INVITABLE_ROLES:
        raise TenantMembershipError("Choose an administrator, billing, or viewer role.")

    email = _normalize_email(email)
    User = get_user_model()
    existing_users = User.objects.filter(email__iexact=email).values_list("pk", flat=True)
    if TenantMembership.objects.filter(tenant=tenant, user_id__in=existing_users).exists():
        raise TenantMembershipError("That email address is already a member of this organization.")

    now = timezone.now()
    TenantInvitation.objects.filter(
        tenant=tenant,
        email__iexact=email,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=now)

    token = secrets.token_urlsafe(32)
    invitation = TenantInvitation.objects.create(
        tenant=tenant,
        email=email,
        role=role,
        token_hash=invitation_token_hash(token),
        invited_by=actor,
        expires_at=now + timedelta(hours=max(1, expires_hours)),
    )
    AuditEvent.objects.create(
        tenant=tenant,
        actor=actor,
        action="tenant.invitation.created",
        target_type="tenant_invitation",
        target_id=str(invitation.pk),
        metadata={
            "email": invitation.email,
            "role": invitation.role,
            "expires_at": invitation.expires_at.isoformat(),
        },
    )
    return TenantInvitationResult(invitation=invitation, token=token)


def get_active_invitation(token: str) -> TenantInvitation:
    token_hash = invitation_token_hash(token)
    invitation = (
        TenantInvitation.objects.select_related("tenant", "invited_by")
        .filter(token_hash=token_hash)
        .first()
    )
    if invitation is None:
        raise TenantMembershipError("This invitation is invalid.")
    if invitation.accepted_at is not None:
        raise TenantMembershipError("This invitation has already been accepted.")
    if invitation.revoked_at is not None:
        raise TenantMembershipError("This invitation has been revoked.")
    if invitation.expires_at <= timezone.now():
        raise TenantMembershipError("This invitation has expired.")
    return invitation


@transaction.atomic
def accept_tenant_invitation(token: str, *, user) -> TenantMembership:
    invitation = get_active_invitation(token)
    invitation = TenantInvitation.objects.select_for_update().select_related("tenant").get(
        pk=invitation.pk
    )
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise TenantMembershipError("This invitation is no longer active.")
    if invitation.expires_at <= timezone.now():
        raise TenantMembershipError("This invitation has expired.")
    if _normalize_email(user.email or "") != invitation.email:
        raise TenantMembershipError("Sign in with the email address that received this invitation.")

    membership, created = TenantMembership.objects.get_or_create(
        tenant=invitation.tenant,
        user=user,
        defaults={"role": invitation.role},
    )
    if not created and membership.role == TenantMembership.Role.OWNER:
        raise TenantMembershipError("Organization owners cannot be changed through invitations.")
    if not created:
        membership.role = invitation.role
        membership.save(update_fields=["role"])

    now = timezone.now()
    invitation.accepted_at = now
    invitation.accepted_by = user
    invitation.save(update_fields=["accepted_at", "accepted_by"])
    AuditEvent.objects.create(
        tenant=invitation.tenant,
        actor=user,
        action="tenant.invitation.accepted",
        target_type="tenant_membership",
        target_id=str(membership.pk),
        metadata={"email": invitation.email, "role": membership.role},
    )
    return membership


@transaction.atomic
def revoke_tenant_invitation(invitation_id: int, *, actor) -> TenantInvitation:
    invitation = TenantInvitation.objects.select_for_update().select_related("tenant").get(
        pk=invitation_id
    )
    actor_membership = _actor_membership(invitation.tenant, actor)
    if actor_membership.role not in MEMBERSHIP_MANAGE_ROLES:
        raise TenantMembershipError("Only owners and administrators can revoke invitations.")
    if invitation.accepted_at is not None:
        raise TenantMembershipError("Accepted invitations cannot be revoked.")
    if invitation.revoked_at is None:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
        AuditEvent.objects.create(
            tenant=invitation.tenant,
            actor=actor,
            action="tenant.invitation.revoked",
            target_type="tenant_invitation",
            target_id=str(invitation.pk),
            metadata={"email": invitation.email, "role": invitation.role},
        )
    return invitation


@transaction.atomic
def change_membership_role(membership_id: int, *, role: str, actor) -> TenantMembership:
    membership = (
        TenantMembership.objects.select_for_update()
        .select_related("tenant", "user")
        .get(pk=membership_id)
    )
    actor_membership = _actor_membership(membership.tenant, actor)
    if actor_membership.role != TenantMembership.Role.OWNER:
        raise TenantMembershipError("Only the organization owner can change member roles.")
    if membership.role == TenantMembership.Role.OWNER:
        raise TenantMembershipError("The owner role cannot be changed here.")
    if role not in INVITABLE_ROLES:
        raise TenantMembershipError("Choose an administrator, billing, or viewer role.")

    previous = membership.role
    if previous != role:
        membership.role = role
        membership.save(update_fields=["role"])
        AuditEvent.objects.create(
            tenant=membership.tenant,
            actor=actor,
            action="tenant.membership.role_changed",
            target_type="tenant_membership",
            target_id=str(membership.pk),
            metadata={
                "user_id": membership.user_id,
                "email": membership.user.email,
                "previous_role": previous,
                "role": role,
            },
        )
    return membership


@transaction.atomic
def remove_tenant_membership(membership_id: int, *, actor) -> None:
    membership = (
        TenantMembership.objects.select_for_update()
        .select_related("tenant", "user")
        .get(pk=membership_id)
    )
    actor_membership = _actor_membership(membership.tenant, actor)
    if actor_membership.role != TenantMembership.Role.OWNER:
        raise TenantMembershipError("Only the organization owner can remove members.")
    if membership.role == TenantMembership.Role.OWNER:
        raise TenantMembershipError("The organization owner cannot be removed.")

    metadata = {
        "user_id": membership.user_id,
        "email": membership.user.email,
        "role": membership.role,
    }
    tenant = membership.tenant
    membership_id_value = membership.pk
    membership.delete()
    AuditEvent.objects.create(
        tenant=tenant,
        actor=actor,
        action="tenant.membership.removed",
        target_type="tenant_membership",
        target_id=str(membership_id_value),
        metadata=metadata,
    )
