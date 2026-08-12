import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.domains.models import Domain, normalize_domain_name
from apps.domains.services import DomainOwnershipVerifier
from apps.tenants.models import Tenant


class FakeTXT:
    def __init__(self, *chunks: bytes):
        self.strings = list(chunks)


class FakeResolver:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def resolve(self, name, record_type, **kwargs):
        self.calls.append((name, record_type, kwargs))
        return self.records


def test_domain_normalization():
    assert normalize_domain_name(" Example.COM. ") == "example.com"


def test_rejects_non_fqdn():
    with pytest.raises(ValidationError):
        normalize_domain_name("localhost")


@pytest.mark.django_db
def test_domain_is_globally_unique_after_normalization():
    tenant_a = Tenant.objects.create(name="A", slug="a")
    tenant_b = Tenant.objects.create(name="B", slug="b")
    Domain.objects.create(tenant=tenant_a, name="Example.COM")
    with pytest.raises(IntegrityError):
        Domain.objects.create(tenant=tenant_b, name="example.com.")


@pytest.mark.django_db
def test_verifier_accepts_exact_txt_token():
    tenant = Tenant.objects.create(name="A", slug="verify-a")
    domain = Domain.objects.create(tenant=tenant, name="example.com")
    resolver = FakeResolver([FakeTXT(domain.verification_record_value.encode())])

    result = DomainOwnershipVerifier(resolver=resolver).verify(domain)

    assert result.verified is True
    assert domain.verification_record_value in result.observed_values
    assert resolver.calls[0][0] == "_mailforge-verify.example.com"
    assert resolver.calls[0][1] == "TXT"


@pytest.mark.django_db
def test_verifier_rejects_wrong_token():
    tenant = Tenant.objects.create(name="A", slug="verify-b")
    domain = Domain.objects.create(tenant=tenant, name="example.org")
    resolver = FakeResolver([FakeTXT(b"mailforge-verification=wrong")])

    result = DomainOwnershipVerifier(resolver=resolver).verify(domain)

    assert result.verified is False
