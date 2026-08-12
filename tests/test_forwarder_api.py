from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from apps.mailboxes.models import Alias, Mailbox
from apps.tenants.models import Tenant, TenantMembership


User = get_user_model()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def provisioned_domain(user):
    tenant = Tenant.objects.create(name="Acme", slug="acme-forwarders")
    TenantMembership.objects.create(
        tenant=tenant,
        user=user,
        role=TenantMembership.Role.OWNER,
    )
    domain = Domain.objects.create(
        tenant=tenant,
        name="example.com",
        status=Domain.Status.DNS_CONFIGURATION,
        backend="stalwart",
        backend_identifier="domain-1",
    )
    return tenant, domain


class FakeMailBackend:
    def create_alias(self, *, address, destinations):
        assert address == "sales@example.com"
        assert destinations == ["alice@example.net", "bob@example.org"]
        return {"id": "list-1"}


@pytest.mark.django_db
def test_owner_can_create_forwarder():
    user = User.objects.create_user(username="forwarder-owner")
    tenant, domain = provisioned_domain(user)

    with patch(
        "apps.mailboxes.forwarders.get_mail_backend",
        return_value=FakeMailBackend(),
    ):
        response = client_for(user).post(
            f"/api/v1/tenants/{tenant.slug}/domains/{domain.pk}/forwarders/",
            {
                "local_part": "Sales",
                "destinations": ["alice@example.net", "bob@example.org"],
            },
            format="json",
        )

    assert response.status_code == 201
    alias = Alias.objects.get()
    assert alias.local_part == "sales"
    assert alias.backend_identifier == "list-1"
    assert alias.active is True
    assert AuditEvent.objects.filter(
        action="forwarder.provisioned",
        tenant=tenant,
        target_id=str(alias.pk),
    ).exists()


@pytest.mark.django_db
def test_forwarder_cannot_replace_existing_mailbox():
    user = User.objects.create_user(username="mailbox-owner")
    tenant, domain = provisioned_domain(user)
    Mailbox.objects.create(
        domain=domain,
        local_part="sales",
        status=Mailbox.Status.ACTIVE,
        backend_identifier="account-1",
    )

    response = client_for(user).post(
        f"/api/v1/tenants/{tenant.slug}/domains/{domain.pk}/forwarders/",
        {
            "local_part": "sales",
            "destinations": ["alice@example.net"],
        },
        format="json",
    )

    assert response.status_code == 409
    assert Alias.objects.count() == 0


@pytest.mark.django_db
def test_forwarder_rejects_self_loop():
    user = User.objects.create_user(username="loop-owner")
    tenant, domain = provisioned_domain(user)

    response = client_for(user).post(
        f"/api/v1/tenants/{tenant.slug}/domains/{domain.pk}/forwarders/",
        {
            "local_part": "sales",
            "destinations": ["sales@example.com"],
        },
        format="json",
    )

    assert response.status_code == 409
    assert Alias.objects.count() == 0
