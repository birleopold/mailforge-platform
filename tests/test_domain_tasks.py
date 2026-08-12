import pytest

from apps.domains.models import Domain
from apps.domains.tasks import reconcile_all_domain_readiness, reconcile_domain_readiness
from apps.tenants.models import Tenant


@pytest.mark.django_db
def test_reconcile_all_queues_each_provisioned_domain(monkeypatch):
    tenant = Tenant.objects.create(name="Scheduled", slug="scheduled")
    first = Domain.objects.create(
        tenant=tenant,
        name="first.example.com",
        backend_identifier="domain-1",
    )
    second = Domain.objects.create(
        tenant=tenant,
        name="second.example.com",
        backend_identifier="domain-2",
        status=Domain.Status.SUSPENDED,
    )
    Domain.objects.create(
        tenant=tenant,
        name="unprovisioned.example.com",
        backend_identifier="",
    )
    queued = []
    monkeypatch.setattr(reconcile_domain_readiness, "delay", queued.append)

    result = reconcile_all_domain_readiness()

    assert queued == [first.pk, second.pk]
    assert result == {"queued": 2, "domain_ids": [first.pk, second.pk]}


@pytest.mark.django_db
def test_reconcile_domain_returns_compact_status(monkeypatch):
    tenant = Tenant.objects.create(name="Single", slug="single")
    domain = Domain.objects.create(
        tenant=tenant,
        name="single.example.com",
        backend_identifier="domain-1",
        status=Domain.Status.DNS_CONFIGURATION,
    )

    class Result:
        ready = False
        checks = {
            "mx": {"status": "pass"},
            "dkim": {"status": "fail"},
            "smtp_policy": {"status": "pass"},
        }

    def fake_check(domain_id):
        assert domain_id == domain.pk
        Domain.objects.filter(pk=domain_id).update(sending_enabled=False)
        return Result()

    monkeypatch.setattr("apps.domains.tasks.check_domain_dns", fake_check)

    result = reconcile_domain_readiness(domain.pk)

    assert result == {
        "domain_id": domain.pk,
        "ready": False,
        "status": Domain.Status.DNS_CONFIGURATION,
        "sending_enabled": False,
        "checks": {"mx": "pass", "dkim": "fail", "smtp_policy": "pass"},
    }
