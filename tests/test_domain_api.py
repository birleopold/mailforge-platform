from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from apps.domains.services import VerificationResult
from apps.tenants.models import Tenant, TenantMembership


User = get_user_model()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def add_member(tenant, user, role):
    return TenantMembership.objects.create(tenant=tenant, user=user, role=role)


@pytest.mark.django_db
def test_non_member_cannot_list_tenant_domains():
    member = User.objects.create_user(username="member")
    outsider = User.objects.create_user(username="outsider")
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    add_member(tenant, member, TenantMembership.Role.OWNER)
    Domain.objects.create(tenant=tenant, name="example.com")

    response = client_for(outsider).get("/api/v1/tenants/acme/domains/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_viewer_cannot_create_domain():
    user = User.objects.create_user(username="viewer")
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    add_member(tenant, user, TenantMembership.Role.VIEWER)

    response = client_for(user).post(
        "/api/v1/tenants/acme/domains/",
        {"name": "example.com"},
        format="json",
    )

    assert response.status_code == 403
    assert Domain.objects.count() == 0


@pytest.mark.django_db
def test_owner_can_add_domain_and_receives_dns_challenge():
    user = User.objects.create_user(username="owner")
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    add_member(tenant, user, TenantMembership.Role.OWNER)

    response = client_for(user).post(
        "/api/v1/tenants/acme/domains/",
        {"name": "Example.COM."},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["name"] == "example.com"
    assert response.data["verification_record_name"] == "_mailforge-verify.example.com"
    assert response.data["verification_record_value"].startswith("mailforge-verification=")
    assert AuditEvent.objects.filter(action="domain.created", tenant=tenant).exists()


@pytest.mark.django_db
def test_owner_can_verify_domain_synchronously():
    user = User.objects.create_user(username="owner")
    tenant = Tenant.objects.create(name="Acme", slug="acme")
    add_member(tenant, user, TenantMembership.Role.OWNER)
    domain = Domain.objects.create(tenant=tenant, name="example.com")

    with patch(
        "apps.domains.services.DomainOwnershipVerifier.verify",
        return_value=VerificationResult(True, (domain.verification_record_value,)),
    ):
        response = client_for(user).post(
            f"/api/v1/tenants/acme/domains/{domain.pk}/verify/",
            format="json",
        )

    assert response.status_code == 200
    assert response.data["verified"] is True
    domain.refresh_from_db()
    assert domain.status == Domain.Status.VERIFIED
    assert domain.verified_at is not None
    assert AuditEvent.objects.filter(
        action="domain.ownership_verified",
        tenant=tenant,
        target_id=str(domain.pk),
    ).count() == 1
