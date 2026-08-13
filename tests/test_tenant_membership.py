import re

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.tenants.models import TenantInvitation, TenantMembership
from apps.tenants.services import (
    TenantMembershipError,
    accept_tenant_invitation,
    change_membership_role,
    create_tenant,
    create_tenant_invitation,
    get_active_invitation,
    invitation_token_hash,
    remove_tenant_membership,
)


User = get_user_model()


def api_client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_invitation_stores_only_token_digest():
    owner = User.objects.create_user(username="owner", email="owner@example.com")
    tenant = create_tenant(name="Acme", owner=owner)

    result = create_tenant_invitation(
        tenant.pk,
        email="NEW@example.com",
        role=TenantMembership.Role.VIEWER,
        actor=owner,
    )

    result.invitation.refresh_from_db()
    assert result.invitation.email == "new@example.com"
    assert result.invitation.token_hash == invitation_token_hash(result.token)
    assert result.invitation.token_hash != result.token
    assert get_active_invitation(result.token).pk == result.invitation.pk
    assert AuditEvent.objects.filter(action="tenant.invitation.created").exists()


@pytest.mark.django_db
def test_invitation_acceptance_requires_matching_email():
    owner = User.objects.create_user(username="owner2", email="owner2@example.com")
    tenant = create_tenant(name="Acme Two", owner=owner)
    result = create_tenant_invitation(
        tenant.pk,
        email="invitee@example.com",
        role=TenantMembership.Role.ADMIN,
        actor=owner,
    )
    wrong_user = User.objects.create_user(username="wrong", email="wrong@example.com")

    with pytest.raises(TenantMembershipError):
        accept_tenant_invitation(result.token, user=wrong_user)

    assert not TenantMembership.objects.filter(tenant=tenant, user=wrong_user).exists()


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_owner_can_send_portal_invitation_and_new_user_can_accept(client):
    owner = User.objects.create_user(
        username="portal-owner",
        email="portal-owner@example.com",
        password="owner-password-123",
    )
    tenant = create_tenant(name="Portal Acme", owner=owner)
    client.force_login(owner)

    response = client.post(
        reverse("portal-tenant-invite", kwargs={"tenant_slug": tenant.slug}),
        {"email": "newperson@example.com", "role": TenantMembership.Role.VIEWER},
    )

    assert response.status_code == 302
    invitation = TenantInvitation.objects.get(email="newperson@example.com")
    assert invitation.accepted_at is None
    assert len(mail.outbox) == 1
    match = re.search(r"https?://[^\s]+/invitations/([^/]+)/", mail.outbox[0].body)
    assert match is not None
    token = match.group(1)
    assert invitation.token_hash == invitation_token_hash(token)

    client.logout()
    accept_response = client.post(
        reverse("tenant-invitation", kwargs={"token": token}),
        {
            "username": "newperson",
            "password1": "very-strong-password-123",
            "password2": "very-strong-password-123",
        },
    )

    assert accept_response.status_code == 302
    new_user = User.objects.get(username="newperson")
    membership = TenantMembership.objects.get(tenant=tenant, user=new_user)
    assert new_user.email == "newperson@example.com"
    assert membership.role == TenantMembership.Role.VIEWER
    invitation.refresh_from_db()
    assert invitation.accepted_at is not None
    assert invitation.accepted_by == new_user


@pytest.mark.django_db
def test_only_owner_can_change_roles_and_remove_members():
    owner = User.objects.create_user(username="role-owner", email="role-owner@example.com")
    admin = User.objects.create_user(username="role-admin", email="role-admin@example.com")
    viewer = User.objects.create_user(username="role-viewer", email="role-viewer@example.com")
    tenant = create_tenant(name="Role Acme", owner=owner)
    TenantMembership.objects.create(tenant=tenant, user=admin, role=TenantMembership.Role.ADMIN)
    viewer_membership = TenantMembership.objects.create(
        tenant=tenant,
        user=viewer,
        role=TenantMembership.Role.VIEWER,
    )

    with pytest.raises(TenantMembershipError):
        change_membership_role(
            viewer_membership.pk,
            role=TenantMembership.Role.BILLING,
            actor=admin,
        )

    updated = change_membership_role(
        viewer_membership.pk,
        role=TenantMembership.Role.BILLING,
        actor=owner,
    )
    assert updated.role == TenantMembership.Role.BILLING

    with pytest.raises(TenantMembershipError):
        remove_tenant_membership(viewer_membership.pk, actor=admin)

    remove_tenant_membership(viewer_membership.pk, actor=owner)
    assert not TenantMembership.objects.filter(pk=viewer_membership.pk).exists()
    assert AuditEvent.objects.filter(action="tenant.membership.role_changed").exists()
    assert AuditEvent.objects.filter(action="tenant.membership.removed").exists()


@pytest.mark.django_db
def test_owner_membership_cannot_be_demoted_or_removed():
    owner = User.objects.create_user(username="protected-owner", email="protected@example.com")
    tenant = create_tenant(name="Protected Acme", owner=owner)
    owner_membership = TenantMembership.objects.get(tenant=tenant, user=owner)

    with pytest.raises(TenantMembershipError):
        change_membership_role(
            owner_membership.pk,
            role=TenantMembership.Role.ADMIN,
            actor=owner,
        )
    with pytest.raises(TenantMembershipError):
        remove_tenant_membership(owner_membership.pk, actor=owner)


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_invitation_api_returns_accept_url_without_token_hash():
    owner = User.objects.create_user(username="api-owner", email="api-owner@example.com")
    tenant = create_tenant(name="API Acme", owner=owner)

    response = api_client_for(owner).post(
        f"/api/v1/tenants/{tenant.slug}/invitations/",
        {"email": "api-invite@example.com", "role": TenantMembership.Role.ADMIN},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["email"] == "api-invite@example.com"
    assert response.data["role"] == TenantMembership.Role.ADMIN
    assert "/invitations/" in response.data["accept_url"]
    assert "token_hash" not in response.data
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_viewer_cannot_invite_or_change_member_role_via_api():
    owner = User.objects.create_user(username="api-owner2", email="owner2@example.com")
    viewer = User.objects.create_user(username="api-viewer", email="viewer@example.com")
    target = User.objects.create_user(username="api-target", email="target@example.com")
    tenant = create_tenant(name="API Restricted", owner=owner)
    TenantMembership.objects.create(tenant=tenant, user=viewer, role=TenantMembership.Role.VIEWER)
    target_membership = TenantMembership.objects.create(
        tenant=tenant,
        user=target,
        role=TenantMembership.Role.VIEWER,
    )
    client = api_client_for(viewer)

    invite_response = client.post(
        f"/api/v1/tenants/{tenant.slug}/invitations/",
        {"email": "blocked@example.com", "role": TenantMembership.Role.VIEWER},
        format="json",
    )
    role_response = client.patch(
        f"/api/v1/tenants/{tenant.slug}/members/{target_membership.pk}/",
        {"role": TenantMembership.Role.ADMIN},
        format="json",
    )

    assert invite_response.status_code == 403
    assert role_response.status_code == 403
