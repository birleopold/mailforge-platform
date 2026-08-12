import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, TenantMembership


User = get_user_model()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_creating_tenant_makes_user_owner():
    user = User.objects.create_user(username="owner")
    response = client_for(user).post(
        "/api/v1/tenants/",
        {"name": "Acme Limited"},
        format="json",
    )

    assert response.status_code == 201
    tenant = Tenant.objects.get(slug=response.data["slug"])
    membership = TenantMembership.objects.get(tenant=tenant, user=user)
    assert membership.role == TenantMembership.Role.OWNER
    assert tenant.plan_code == "free"


@pytest.mark.django_db
def test_tenant_list_only_contains_memberships_for_user():
    user_a = User.objects.create_user(username="alice")
    user_b = User.objects.create_user(username="bob")
    tenant_a = Tenant.objects.create(name="A", slug="a")
    tenant_b = Tenant.objects.create(name="B", slug="b")
    TenantMembership.objects.create(
        tenant=tenant_a,
        user=user_a,
        role=TenantMembership.Role.OWNER,
    )
    TenantMembership.objects.create(
        tenant=tenant_b,
        user=user_b,
        role=TenantMembership.Role.OWNER,
    )

    response = client_for(user_a).get("/api/v1/tenants/")

    assert response.status_code == 200
    assert [item["slug"] for item in response.data] == ["a"]
