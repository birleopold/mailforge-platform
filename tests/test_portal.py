import pytest
from django.contrib.auth import get_user_model

from apps.domains.models import Domain
from apps.tenants.models import Tenant, TenantMembership


User = get_user_model()


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_logged_in_user_sees_only_own_organizations(client):
    user = User.objects.create_user(username="alice")
    other = User.objects.create_user(username="bob")
    own = Tenant.objects.create(name="Alice Co", slug="alice-co")
    hidden = Tenant.objects.create(name="Bob Co", slug="bob-co")
    TenantMembership.objects.create(
        tenant=own,
        user=user,
        role=TenantMembership.Role.OWNER,
    )
    TenantMembership.objects.create(
        tenant=hidden,
        user=other,
        role=TenantMembership.Role.OWNER,
    )
    client.force_login(user)

    response = client.get("/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Alice Co" in content
    assert "Bob Co" not in content


@pytest.mark.django_db
def test_other_users_tenant_page_returns_404(client):
    user = User.objects.create_user(username="alice")
    other = User.objects.create_user(username="bob")
    tenant = Tenant.objects.create(name="Private Co", slug="private-co")
    TenantMembership.objects.create(
        tenant=tenant,
        user=other,
        role=TenantMembership.Role.OWNER,
    )
    client.force_login(user)

    response = client.get("/portal/tenants/private-co/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_domain_page_renders_verification_challenge_for_owner(client):
    user = User.objects.create_user(username="owner")
    tenant = Tenant.objects.create(name="Acme", slug="acme-portal")
    TenantMembership.objects.create(
        tenant=tenant,
        user=user,
        role=TenantMembership.Role.OWNER,
    )
    domain = Domain.objects.create(tenant=tenant, name="example.com")
    client.force_login(user)

    response = client.get(f"/portal/tenants/{tenant.slug}/domains/{domain.pk}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "_mailforge-verify.example.com" in content
    assert domain.verification_record_value in content
