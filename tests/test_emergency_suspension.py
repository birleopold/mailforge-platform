import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.domains.dns_readiness import check_domain_dns
from apps.domains.lifecycle import reactivate_domain, suspend_domain
from apps.domains.models import Domain
from apps.mailboxes.forwarders import ForwarderLifecycleError, update_forwarder
from apps.mailboxes.models import Alias, Mailbox
from apps.mailboxes.services import MailboxLifecycleError, reactivate_mailbox
from apps.tenants.lifecycle import reactivate_tenant, suspend_tenant
from apps.tenants.models import Tenant, TenantMembership
from apps.tenants.services import TenantMembershipError, create_tenant


User = get_user_model()


class FakeBackend:
    def __init__(self, *, fail_suspend=(), fail_unsuspend=()):
        self.fail_suspend = set(fail_suspend)
        self.fail_unsuspend = set(fail_unsuspend)
        self.calls = []

    def set_account_suspended(self, *, account_id, suspended, sending_enabled=False):
        self.calls.append((str(account_id), bool(suspended), bool(sending_enabled)))
        if suspended and str(account_id) in self.fail_suspend:
            raise RuntimeError("suspend failed")
        if not suspended and str(account_id) in self.fail_unsuspend:
            raise RuntimeError("reactivate failed")


class EmptyResolver:
    def resolve(self, name, record_type, **kwargs):
        return []


def domain_with_mailbox(tenant, *, name, account_id, status=Domain.Status.ACTIVE):
    domain = Domain.objects.create(
        tenant=tenant,
        name=name,
        status=status,
        verified_at=timezone.now(),
        backend="stalwart",
        backend_identifier=f"domain-{account_id}",
        sending_enabled=status == Domain.Status.ACTIVE,
    )
    mailbox = Mailbox.objects.create(
        domain=domain,
        local_part="user",
        status=Mailbox.Status.ACTIVE,
        backend_identifier=account_id,
    )
    return domain, mailbox


@pytest.mark.django_db
def test_domain_emergency_suspend_revokes_mailbox_permissions_and_fails_closed():
    owner = User.objects.create_user(username="suspend-owner", email="owner@example.com")
    tenant = create_tenant(name="Suspend Acme", owner=owner)
    domain, _ = domain_with_mailbox(tenant, name="suspend.example", account_id="account-1")
    backend = FakeBackend()

    result = suspend_domain(domain.pk, actor=owner, backend=backend)
    domain.refresh_from_db()

    assert result.success is True
    assert domain.status == Domain.Status.SUSPENDED
    assert domain.sending_enabled is False
    assert backend.calls == [("account-1", True, False)]
    assert domain.dns_checks["emergency_suspension"]["status"] == "pass"
    assert AuditEvent.objects.filter(action="domain.emergency_suspended").exists()


@pytest.mark.django_db
def test_domain_stays_suspended_when_backend_enforcement_fails():
    owner = User.objects.create_user(username="fail-owner", email="fail-owner@example.com")
    tenant = create_tenant(name="Failure Acme", owner=owner)
    domain, _ = domain_with_mailbox(tenant, name="failure.example", account_id="account-fail")
    backend = FakeBackend(fail_suspend={"account-fail"})

    result = suspend_domain(domain.pk, actor=owner, backend=backend)
    domain.refresh_from_db()

    assert result.success is False
    assert result.failed_addresses == ("user@failure.example",)
    assert domain.status == Domain.Status.SUSPENDED
    assert domain.sending_enabled is False
    assert domain.dns_checks["emergency_suspension"]["status"] == "fail"


@pytest.mark.django_db
def test_domain_reactivation_restores_access_with_sending_disabled_first():
    owner = User.objects.create_user(username="reactivate-owner", email="reactivate@example.com")
    tenant = create_tenant(name="Reactivate Acme", owner=owner)
    domain, _ = domain_with_mailbox(
        tenant,
        name="reactivate.example",
        account_id="account-2",
        status=Domain.Status.SUSPENDED,
    )
    backend = FakeBackend()

    result = reactivate_domain(
        domain.pk,
        actor=owner,
        backend=backend,
        run_dns_check=False,
    )
    domain.refresh_from_db()

    assert result.success is True
    assert domain.status == Domain.Status.DNS_CONFIGURATION
    assert domain.sending_enabled is False
    assert backend.calls == [("account-2", False, False)]
    assert AuditEvent.objects.filter(action="domain.emergency_reactivated").exists()


@pytest.mark.django_db
def test_individual_mailbox_cannot_bypass_suspended_domain():
    owner = User.objects.create_user(username="mailbox-owner3", email="mailbox@example.com")
    tenant = create_tenant(name="Mailbox Guard", owner=owner)
    domain = Domain.objects.create(
        tenant=tenant,
        name="guard.example",
        status=Domain.Status.SUSPENDED,
        backend_identifier="domain-guard",
    )
    mailbox = Mailbox.objects.create(
        domain=domain,
        local_part="user",
        status=Mailbox.Status.SUSPENDED,
        backend_identifier="account-guard",
    )

    with pytest.raises(MailboxLifecycleError):
        reactivate_mailbox(mailbox.pk, backend=FakeBackend(), actor=owner)

    mailbox.refresh_from_db()
    assert mailbox.status == Mailbox.Status.SUSPENDED


@pytest.mark.django_db
def test_forwarder_changes_are_blocked_during_domain_suspension():
    owner = User.objects.create_user(username="forwarder-guard", email="forwarder@example.com")
    tenant = create_tenant(name="Forwarder Guard", owner=owner)
    domain = Domain.objects.create(
        tenant=tenant,
        name="forwarder-guard.example",
        status=Domain.Status.SUSPENDED,
        backend_identifier="domain-forwarder",
    )
    alias = Alias.objects.create(
        domain=domain,
        local_part="sales",
        destinations=["one@example.net"],
        active=True,
        backend_identifier="list-1",
    )

    with pytest.raises(ForwarderLifecycleError):
        update_forwarder(
            alias.pk,
            destinations=["two@example.net"],
            backend=object(),
            actor=owner,
        )


@pytest.mark.django_db
def test_tenant_emergency_suspend_cascades_and_is_owner_only():
    owner = User.objects.create_user(username="tenant-owner", email="tenant-owner@example.com")
    admin = User.objects.create_user(username="tenant-admin", email="tenant-admin@example.com")
    tenant = create_tenant(name="Tenant Emergency", owner=owner)
    TenantMembership.objects.create(tenant=tenant, user=admin, role=TenantMembership.Role.ADMIN)
    first, _ = domain_with_mailbox(tenant, name="one.example", account_id="account-one")
    second, _ = domain_with_mailbox(tenant, name="two.example", account_id="account-two")
    backend = FakeBackend()

    with pytest.raises(TenantMembershipError):
        suspend_tenant(tenant.pk, actor=admin, backend=backend)

    result = suspend_tenant(tenant.pk, actor=owner, backend=backend)
    tenant.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()

    assert result.success is True
    assert tenant.status == Tenant.Status.SUSPENDED
    assert first.status == Domain.Status.SUSPENDED
    assert second.status == Domain.Status.SUSPENDED
    assert ("account-one", True, False) in backend.calls
    assert ("account-two", True, False) in backend.calls
    assert AuditEvent.objects.filter(action="tenant.emergency_suspended").exists()


@pytest.mark.django_db
def test_tenant_reactivation_rolls_back_if_one_domain_cannot_restore():
    owner = User.objects.create_user(username="rollback-owner", email="rollback@example.com")
    tenant = create_tenant(name="Rollback Acme", owner=owner)
    tenant.status = Tenant.Status.SUSPENDED
    tenant.save(update_fields=["status"])
    first, _ = domain_with_mailbox(
        tenant,
        name="rollback-one.example",
        account_id="restore-one",
        status=Domain.Status.SUSPENDED,
    )
    second, _ = domain_with_mailbox(
        tenant,
        name="rollback-two.example",
        account_id="restore-two",
        status=Domain.Status.SUSPENDED,
    )
    backend = FakeBackend(fail_unsuspend={"restore-two"})

    result = reactivate_tenant(tenant.pk, actor=owner, backend=backend)
    tenant.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()

    assert result.success is False
    assert "rollback-two.example" in result.failed_domains
    assert tenant.status == Tenant.Status.SUSPENDED
    assert first.status == Domain.Status.SUSPENDED
    assert second.status == Domain.Status.SUSPENDED
    assert ("restore-one", False, False) in backend.calls
    assert ("restore-one", True, False) in backend.calls


@pytest.mark.django_db
def test_periodic_dns_reconciliation_reapplies_full_emergency_suspension():
    owner = User.objects.create_user(username="reconcile-owner", email="reconcile@example.com")
    tenant = create_tenant(name="Reconcile Emergency", owner=owner)
    domain, _ = domain_with_mailbox(
        tenant,
        name="reconcile.example",
        account_id="reconcile-account",
        status=Domain.Status.SUSPENDED,
    )
    backend = FakeBackend()

    result = check_domain_dns(
        domain.pk,
        resolver=EmptyResolver(),
        backend=backend,
    )
    domain.refresh_from_db()

    assert result.ready is False
    assert domain.status == Domain.Status.SUSPENDED
    assert domain.sending_enabled is False
    assert result.checks["smtp_policy"]["status"] == "pass"
    assert result.checks["smtp_policy"]["expected"] == (
        "All active Stalwart mailbox permissions suspended"
    )
    assert backend.calls == [("reconcile-account", True, False)]
