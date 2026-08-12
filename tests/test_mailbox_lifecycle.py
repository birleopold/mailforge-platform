from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from apps.mailboxes.models import Mailbox
from apps.tenants.models import Tenant, TenantMembership


User = get_user_model()


class FakeLifecycleBackend:
    def __init__(self):
        self.calls = []

    def set_account_suspended(self, *, account_id, suspended, sending_enabled=False):
        self.calls.append(("suspended", account_id, suspended, sending_enabled))

    def reset_account_password(self, *, account_id, password):
        self.calls.append(("password", account_id, password))

    def delete_account(self, *, account_id):
        self.calls.append(("delete", account_id))


def setup_mailbox(*, role=TenantMembership.Role.OWNER, status=Mailbox.Status.ACTIVE):
    user = User.objects.create_user(username=f"user-{role}-{status}", password="test-password-123")
    tenant = Tenant.objects.create(name="Mailbox Tenant", slug=f"mailbox-{role}-{status}")
    TenantMembership.objects.create(tenant=tenant, user=user, role=role)
    domain = Domain.objects.create(
        tenant=tenant,
        name=f"{role}-{status}.example.com",
        status=Domain.Status.DNS_CONFIGURATION,
        backend_identifier="domain-1",
        sending_enabled=False,
    )
    mailbox = Mailbox.objects.create(
        domain=domain,
        local_part="alice",
        status=status,
        backend_identifier="account-1",
    )
    return user, tenant, domain, mailbox


def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_owner_can_suspend_reactivate_reset_and_delete_mailbox():
    user, tenant, domain, mailbox = setup_mailbox()
    backend = FakeLifecycleBackend()
    base = f"/api/v1/tenants/{tenant.slug}/domains/{domain.pk}/mailboxes/{mailbox.pk}"

    with patch("apps.mailboxes.services.get_mail_backend", return_value=backend):
        response = api_client(user).post(f"{base}/suspend/", {}, format="json")
        assert response.status_code == 200
        mailbox.refresh_from_db()
        assert mailbox.status == Mailbox.Status.SUSPENDED

        response = api_client(user).post(f"{base}/reactivate/", {}, format="json")
        assert response.status_code == 200
        mailbox.refresh_from_db()
        assert mailbox.status == Mailbox.Status.ACTIVE

        response = api_client(user).post(
            f"{base}/password-reset/",
            {"password": "A-new-long-password-478!"},
            format="json",
        )
        assert response.status_code == 200
        assert "password" not in response.data

        response = api_client(user).delete(f"{base}/")
        assert response.status_code == 204

    mailbox.refresh_from_db()
    assert mailbox.status == Mailbox.Status.DELETED
    assert backend.calls == [
        ("suspended", "account-1", True, False),
        ("suspended", "account-1", False, False),
        ("password", "account-1", "A-new-long-password-478!"),
        ("delete", "account-1"),
    ]
    assert set(
        AuditEvent.objects.filter(tenant=tenant, target_id=str(mailbox.pk)).values_list(
            "action", flat=True
        )
    ) >= {
        "mailbox.suspended",
        "mailbox.reactivated",
        "mailbox.password_reset",
        "mailbox.deleted",
    }


@pytest.mark.django_db
def test_viewer_cannot_change_mailbox_lifecycle():
    user, tenant, domain, mailbox = setup_mailbox(role=TenantMembership.Role.VIEWER)
    base = f"/api/v1/tenants/{tenant.slug}/domains/{domain.pk}/mailboxes/{mailbox.pk}"

    response = api_client(user).post(f"{base}/suspend/", {}, format="json")

    assert response.status_code == 403
    mailbox.refresh_from_db()
    assert mailbox.status == Mailbox.Status.ACTIVE


@pytest.mark.django_db
def test_portal_renders_mailbox_admin_and_requires_typed_delete_confirmation():
    user, tenant, domain, mailbox = setup_mailbox()
    backend = FakeLifecycleBackend()
    client = Client()
    client.force_login(user)

    page = client.get(f"/portal/tenants/{tenant.slug}/domains/{domain.pk}/")
    assert page.status_code == 200
    assert b"Create mailbox" in page.content
    assert b"Suspend" in page.content
    assert b"Reset password" in page.content
    assert b"Delete mailbox" in page.content

    with patch("apps.mailboxes.services.get_mail_backend", return_value=backend):
        response = client.post(
            f"/portal/tenants/{tenant.slug}/domains/{domain.pk}/mailboxes/{mailbox.pk}/delete/",
            {"confirm_email": "wrong@example.com"},
        )
        assert response.status_code == 302
        mailbox.refresh_from_db()
        assert mailbox.status == Mailbox.Status.ACTIVE
        assert backend.calls == []

        response = client.post(
            f"/portal/tenants/{tenant.slug}/domains/{domain.pk}/mailboxes/{mailbox.pk}/delete/",
            {"confirm_email": mailbox.email_address},
        )
        assert response.status_code == 302

    mailbox.refresh_from_db()
    assert mailbox.status == Mailbox.Status.DELETED
    assert backend.calls == [("delete", "account-1")]
