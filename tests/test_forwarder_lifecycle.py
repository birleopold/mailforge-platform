from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from apps.mailboxes.models import Alias
from apps.tenants.models import Tenant, TenantMembership


User = get_user_model()


class FakeForwarderBackend:
    def __init__(self):
        self.calls = []

    def update_alias(self, *, alias_id, destinations):
        self.calls.append(("update", alias_id, list(destinations)))

    def delete_alias(self, *, alias_id):
        self.calls.append(("delete", alias_id))


def setup_forwarder(*, role=TenantMembership.Role.OWNER):
    user = User.objects.create_user(username=f"forwarder-{role}", password="test-password-123")
    tenant = Tenant.objects.create(name="Forwarder Tenant", slug=f"forwarder-{role}")
    TenantMembership.objects.create(tenant=tenant, user=user, role=role)
    domain = Domain.objects.create(
        tenant=tenant,
        name=f"{role}.forwarder.example.com",
        status=Domain.Status.DNS_CONFIGURATION,
        backend_identifier="domain-1",
    )
    forwarder = Alias.objects.create(
        domain=domain,
        local_part="support",
        destinations=["first@example.net"],
        backend_identifier="list-1",
        active=True,
    )
    return user, tenant, domain, forwarder


def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_owner_can_update_and_delete_forwarder_via_api():
    user, tenant, domain, forwarder = setup_forwarder()
    backend = FakeForwarderBackend()
    url = f"/api/v1/tenants/{tenant.slug}/domains/{domain.pk}/forwarders/{forwarder.pk}/"

    with patch("apps.mailboxes.forwarders.get_mail_backend", return_value=backend):
        response = api_client(user).patch(
            url,
            {"destinations": ["Second@Example.NET", "third@example.org"]},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["destinations"] == ["second@example.net", "third@example.org"]

        response = api_client(user).delete(url)
        assert response.status_code == 204

    forwarder.refresh_from_db()
    assert forwarder.active is False
    assert backend.calls == [
        ("update", "list-1", ["second@example.net", "third@example.org"]),
        ("delete", "list-1"),
    ]
    assert set(
        AuditEvent.objects.filter(tenant=tenant, target_id=str(forwarder.pk)).values_list(
            "action", flat=True
        )
    ) >= {"forwarder.updated", "forwarder.deleted"}


@pytest.mark.django_db
def test_forwarder_update_rejects_self_loop_before_backend_call():
    user, tenant, domain, forwarder = setup_forwarder()
    backend = FakeForwarderBackend()
    url = f"/api/v1/tenants/{tenant.slug}/domains/{domain.pk}/forwarders/{forwarder.pk}/"

    with patch("apps.mailboxes.forwarders.get_mail_backend", return_value=backend):
        response = api_client(user).patch(
            url,
            {"destinations": [forwarder.email_address]},
            format="json",
        )

    assert response.status_code == 409
    assert backend.calls == []
    forwarder.refresh_from_db()
    assert forwarder.destinations == ["first@example.net"]
    assert forwarder.active is True


@pytest.mark.django_db
def test_viewer_cannot_update_or_delete_forwarder():
    user, tenant, domain, forwarder = setup_forwarder(role=TenantMembership.Role.VIEWER)
    url = f"/api/v1/tenants/{tenant.slug}/domains/{domain.pk}/forwarders/{forwarder.pk}/"

    response = api_client(user).patch(
        url,
        {"destinations": ["other@example.net"]},
        format="json",
    )
    assert response.status_code == 403

    response = api_client(user).delete(url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_portal_edits_forwarder_and_requires_typed_delete_confirmation():
    user, tenant, domain, forwarder = setup_forwarder()
    backend = FakeForwarderBackend()
    client = Client()
    client.force_login(user)

    page = client.get(f"/portal/tenants/{tenant.slug}/domains/{domain.pk}/")
    assert page.status_code == 200
    assert b"Edit destinations" in page.content
    assert b"Delete forwarder" in page.content

    with patch("apps.mailboxes.forwarders.get_mail_backend", return_value=backend):
        response = client.post(
            f"/portal/tenants/{tenant.slug}/domains/{domain.pk}/forwarders/{forwarder.pk}/update/",
            {"destinations": "new@example.net, NEW@example.net, audit@example.org"},
        )
        assert response.status_code == 302

        response = client.post(
            f"/portal/tenants/{tenant.slug}/domains/{domain.pk}/forwarders/{forwarder.pk}/delete/",
            {"confirm_email": "wrong@example.com"},
        )
        assert response.status_code == 302
        forwarder.refresh_from_db()
        assert forwarder.active is True

        response = client.post(
            f"/portal/tenants/{tenant.slug}/domains/{domain.pk}/forwarders/{forwarder.pk}/delete/",
            {"confirm_email": forwarder.email_address},
        )
        assert response.status_code == 302

    forwarder.refresh_from_db()
    assert forwarder.destinations == ["new@example.net", "audit@example.org"]
    assert forwarder.active is False
    assert backend.calls == [
        ("update", "list-1", ["new@example.net", "audit@example.org"]),
        ("delete", "list-1"),
    ]
