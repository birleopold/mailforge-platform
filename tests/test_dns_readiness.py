import pytest
from django.test import override_settings
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.domains.dns_readiness import (
    check_domain_dns,
    extract_dkim_records,
    inspect_domain_dns,
)
from apps.domains.models import Domain
from apps.tenants.models import Tenant


DKIM_ZONE = """$ORIGIN example.com.
$TTL 3600
mailforge-2026._domainkey 3600 IN TXT "v=DKIM1; k=rsa; p=ABC" "DEF"
"""


class FakeTXT:
    def __init__(self, value: str):
        self.strings = [value.encode()]


class FakeMX:
    def __init__(self, exchange: str):
        self.exchange = exchange


class FakePTR:
    def __init__(self, target: str):
        self.target = target


class FakeResolver:
    def __init__(self, records):
        self.records = records

    def resolve(self, name, record_type, **kwargs):
        return self.records.get((str(name), record_type), [])


class FakeBackend:
    def __init__(self, zone_file):
        self.zone_file = zone_file
        self.calls = []

    def get_domain(self, domain_id):
        self.calls.append(domain_id)
        return {"id": domain_id, "name": "example.com", "dnsZoneFile": self.zone_file}


def dkim_records():
    records = extract_dkim_records(DKIM_ZONE, "example.com")
    assert records is not None
    return records


def healthy_records(domain_name="example.com"):
    return {
        (domain_name, "MX"): [FakeMX("mail.mailforge.test.")],
        (domain_name, "TXT"): [FakeTXT("v=spf1 mx -all")],
        (f"mailforge-2026._domainkey.{domain_name}", "TXT"): [
            FakeTXT("v=DKIM1; k=rsa; p=ABCDEF")
        ],
        (f"_dmarc.{domain_name}", "TXT"): [FakeTXT("v=DMARC1; p=quarantine")],
        ("10.113.0.203.in-addr.arpa.", "PTR"): [FakePTR("mail.mailforge.test.")],
    }


def test_extracts_split_stalwart_dkim_txt_from_zone_file():
    assert dkim_records() == [
        {
            "name": "mailforge-2026._domainkey.example.com",
            "value": "v=DKIM1; k=rsa; p=ABCDEF",
        }
    ]


@override_settings(
    MAILFORGE_MAIL_HOSTNAME="mail.mailforge.test",
    MAILFORGE_MAIL_IPV4="203.0.113.10",
)
def test_dns_readiness_passes_with_required_records():
    result = inspect_domain_dns(
        "example.com",
        resolver=FakeResolver(healthy_records()),
        dkim_records=dkim_records(),
    )

    assert result.ready is True
    assert result.checks["mx"]["status"] == "pass"
    assert result.checks["spf"]["status"] == "pass"
    assert result.checks["dkim"]["status"] == "pass"
    assert result.checks["dmarc"]["status"] == "pass"
    assert result.checks["ptr"]["status"] == "pass"


@override_settings(
    MAILFORGE_MAIL_HOSTNAME="mail.mailforge.test",
    MAILFORGE_MAIL_IPV4="",
)
def test_multiple_spf_records_block_readiness():
    records = healthy_records()
    records[("example.com", "TXT")] = [
        FakeTXT("v=spf1 mx -all"),
        FakeTXT("v=spf1 include:example.net -all"),
    ]
    result = inspect_domain_dns(
        "example.com",
        resolver=FakeResolver(records),
        dkim_records=dkim_records(),
    )

    assert result.ready is False
    assert result.checks["spf"]["status"] == "fail"
    assert result.checks["ptr"]["status"] == "skip"


@override_settings(
    MAILFORGE_MAIL_HOSTNAME="mail.mailforge.test",
    MAILFORGE_MAIL_IPV4="",
)
def test_missing_or_wrong_dkim_blocks_readiness():
    records = healthy_records()
    records[("mailforge-2026._domainkey.example.com", "TXT")] = [
        FakeTXT("v=DKIM1; k=rsa; p=WRONG")
    ]
    result = inspect_domain_dns(
        "example.com",
        resolver=FakeResolver(records),
        dkim_records=dkim_records(),
    )

    assert result.ready is False
    assert result.checks["dkim"]["status"] == "fail"
    assert "mailforge-2026._domainkey.example.com" in result.checks["dkim"]["detail"]


@override_settings(
    MAILFORGE_MAIL_HOSTNAME="mail.mailforge.test",
    MAILFORGE_MAIL_IPV4="",
)
def test_missing_stalwart_dkim_expectation_blocks_readiness():
    result = inspect_domain_dns(
        "example.com",
        resolver=FakeResolver(healthy_records()),
        dkim_records=None,
    )

    assert result.ready is False
    assert result.checks["dkim"]["status"] == "warn"
    assert result.checks["dkim"]["required"] is True


@pytest.mark.django_db
@override_settings(
    MAILFORGE_MAIL_HOSTNAME="mail.mailforge.test",
    MAILFORGE_MAIL_IPV4="203.0.113.10",
)
def test_dns_gate_enables_and_disables_sending():
    tenant = Tenant.objects.create(name="Acme", slug="dns-acme")
    domain = Domain.objects.create(
        tenant=tenant,
        name="example.com",
        status=Domain.Status.DNS_CONFIGURATION,
        verified_at=timezone.now(),
        backend_identifier="domain-1",
        dns_zone_file=DKIM_ZONE,
    )

    first = check_domain_dns(
        domain.pk,
        resolver=FakeResolver(healthy_records()),
        backend=object(),
    )
    domain.refresh_from_db()

    assert first.ready is True
    assert domain.status == Domain.Status.ACTIVE
    assert domain.sending_enabled is True
    assert domain.dns_checked_at is not None
    assert AuditEvent.objects.filter(action="domain.sending_readiness_changed").count() == 1

    broken = healthy_records()
    broken[("mailforge-2026._domainkey.example.com", "TXT")] = []
    second = check_domain_dns(
        domain.pk,
        resolver=FakeResolver(broken),
        backend=object(),
    )
    domain.refresh_from_db()

    assert second.ready is False
    assert domain.status == Domain.Status.DNS_CONFIGURATION
    assert domain.sending_enabled is False
    assert AuditEvent.objects.filter(action="domain.sending_readiness_changed").count() == 2


@pytest.mark.django_db
@override_settings(
    MAILFORGE_MAIL_HOSTNAME="mail.mailforge.test",
    MAILFORGE_MAIL_IPV4="203.0.113.10",
)
def test_dns_check_refreshes_stalwart_zone_before_dkim_validation():
    tenant = Tenant.objects.create(name="Acme", slug="dns-refresh")
    domain = Domain.objects.create(
        tenant=tenant,
        name="example.com",
        status=Domain.Status.DNS_CONFIGURATION,
        verified_at=timezone.now(),
        backend_identifier="domain-1",
        dns_zone_file="stale invalid zone",
    )
    backend = FakeBackend(DKIM_ZONE)

    result = check_domain_dns(
        domain.pk,
        resolver=FakeResolver(healthy_records()),
        backend=backend,
    )
    domain.refresh_from_db()

    assert result.ready is True
    assert backend.calls == ["domain-1"]
    assert domain.dns_zone_file == DKIM_ZONE
    assert domain.dns_checks["dkim"]["status"] == "pass"
