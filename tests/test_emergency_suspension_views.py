import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.domains.models import Domain
from apps.tenants.models import Tenant, TenantMembership
from apps.tenants.services import create_tenant


User = get_user_model()


def api_client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_owner_can_emergency_suspend_and_reactivate_tenant_through_api():
    owner = User.objects.create_user(username="emergency-api-owner", email="owner@example.com")
    tenant = create_tenant(name="Emergency API", owner=owner)
    domain = Domain.objects.create(
        tenant=tenant,
        name="emergency-api.example",
        status=Domain.Status.PENDING_VERIFICATION,
    )
    client = api_client_for(owner)

    suspended = client.post(f"/api/v1/tenants/{tenant.slug}/suspend/", {}, format="json")
    tenant.refresh_from_db()
    domain.refresh_from_db()

    assert suspended.status_code == 200
    assert suspended.data["backend_enforced"] is True
    assert tenant.status == Tenant.Status.SUSPENDED
    assert domain.status == Domain.Status.SUSPENDED

    reactivated = client.post(f"/api/v1/tenants/{tenant.slug}/reactivate/", {}, format="json")
    tenant.refresh_from_db()
    domain.refresh_from_db()

    assert reactivated.status_code == 200
    assert reactivated.data["backend_restored"] is True
    assert tenant.status == Tenant.Status.ACTIVE
    assert domain.status == Domain.Status.PENDING_VERIFICATION


@pytest.mark.django_db
def test_admin_cannot_use_tenant_emergency_api_but_can_suspend_domain():
    owner = User.objects.create_user(username="emergency-owner2", email="owner2@example.com")
    admin = User.objects.create_user(username="emergency-admin", email="admin@example.com")
    tenant = create_tenant(name="Emergency Roles", owner=owner)
    TenantMembership.objects.create(tenant=tenant, user=admin, role=TenantMembership.Role.ADMIN)
    domain = Domain.objects.create(
        tenant=tenant,
        name="admin-domain.example",
        status=Domain.Status.PENDING_VERIFICATION,
    )
    client = api_client_for(admin)

    tenant_response = client.post(f"/api/v1/tenants/{tenant.slug}/suspend/", {}, format="json")
    domain_response = client.post(
        f"/api/v1/tenants/{tenant.slug}/domains/{domain.pk}/suspend/",
        {},
        format="json",
    )
    domain.refresh_from_db()

    assert tenant_response.status_code == 403
    assert domain_response.status_code == 200
    assert domain.status == Domain.Status.SUSPENDED


@pytest.mark.django_db
def test_viewer_cannot_use_domain_emergency_api():
    owner = User.objects.create_user(username="emergency-owner3", email="owner3@example.com")
    viewer = User.objects.create_user(username="emergency-viewer", email="viewer@example.com")
    tenant = create_tenant(name="Emergency Viewer", owner=owner)
    TenantMembership.objects.create(tenant=tenant, user=viewer, role=TenantMembership.Role.VIEWER)
    domain = Domain.objects.create(
        tenant=tenant,
        name="viewer-domain.example",
        status=Domain.Status.PENDING_VERIFICATION,
    )

    response = api_client_for(viewer).post(
        f"/api/v1/tenants/{tenant.slug}/domains/{domain.pk}/suspend/",
        {},
        format="json",
    )

    assert response.status_code == 403
    domain.refresh_from_db()
    assert domain.status == Domain.Status.PENDING_VERIFICATION


@pytest.mark.django_db
def test_portal_owner_sees_and_can_use_emergency_tenant_controls(client):
    owner = User.objects.create_user(
        username="portal-emergency-owner",
        email="portal-owner@example.com",
        password="owner-password-123",
    )
    tenant = create_tenant(name="Portal Emergency", owner=owner)
    client.force_login(owner)

    page = client.get(reverse("portal-tenant", kwargs={"tenant_slug": tenant.slug}))
    assert page.status_code == 200
    assert b"Emergency suspend organization" in page.content

    response = client.post(reverse("portal-tenant-suspend", kwargs={"tenant_slug": tenant.slug}))
    tenant.refresh_from_db()

    assert response.status_code == 302
    assert tenant.status == Tenant.Status.SUSPENDED

    page = client.get(reverse("portal-tenant", kwargs={"tenant_slug": tenant.slug}))
    assert b"Reactivate organization" in page.content


@pytest.mark.django_db
def test_portal_admin_does_not_get_tenant_emergency_control(client):
    owner = User.objects.create_user(username="portal-owner4", email="owner4@example.com")
    admin = User.objects.create_user(
        username="portal-admin4",
        email="admin4@example.com",
        password="admin-password-123",
    )
    tenant = create_tenant(name="Portal Admin Emergency", owner=owner)
    TenantMembership.objects.create(tenant=tenant, user=admin, role=TenantMembership.Role.ADMIN)
    client.force_login(admin)

    page = client.get(reverse("portal-tenant", kwargs={"tenant_slug": tenant.slug}))

    assert page.status_code == 200
    assert b"Emergency suspend organization" not in page.content
