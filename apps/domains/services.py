from __future__ import annotations

from dataclasses import dataclass

import dns.exception
import dns.resolver
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from apps.tenants.models import Tenant


class DomainVerificationTemporaryError(RuntimeError):
    """Raised when DNS verification should be retried later."""


class DomainVerificationBlockedError(DomainVerificationTemporaryError):
    """Raised when emergency suspension intentionally blocks verification state changes."""


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    observed_values: tuple[str, ...]
    already_verified: bool = False


class DomainOwnershipVerifier:
    def __init__(self, resolver=None, *, lifetime: float = 5.0):
        self.resolver = resolver or dns.resolver.Resolver()
        self.lifetime = lifetime

    @staticmethod
    def _txt_value(record) -> str:
        strings = getattr(record, "strings", None)
        if strings is not None:
            return b"".join(strings).decode("utf-8", errors="replace")
        return record.to_text().replace('" "', '').strip('"')

    def verify(self, domain) -> VerificationResult:
        try:
            answer = self.resolver.resolve(
                domain.verification_record_name,
                "TXT",
                lifetime=self.lifetime,
                search=False,
            )
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return VerificationResult(False, ())
        except (
            dns.resolver.NoNameservers,
            dns.resolver.LifetimeTimeout,
            dns.exception.Timeout,
        ) as exc:
            raise DomainVerificationTemporaryError(str(exc)) from exc

        values = tuple(self._txt_value(record) for record in answer)
        return VerificationResult(domain.verification_record_value in values, values)


def verify_domain_and_record(domain_id: int, *, verifier=None) -> VerificationResult:
    """Verify a domain and persist the successful transition exactly once."""
    domain = Domain.objects.select_related("tenant").get(pk=domain_id)
    if domain.tenant.status != Tenant.Status.ACTIVE:
        raise DomainVerificationBlockedError("Reactivate the organization before verifying domains.")
    if domain.status == Domain.Status.SUSPENDED:
        raise DomainVerificationBlockedError("Reactivate the domain before verifying ownership.")
    if domain.verified_at is not None:
        return VerificationResult(True, (), already_verified=True)

    verifier = verifier or DomainOwnershipVerifier()
    result = verifier.verify(domain)
    if not result.verified:
        return result

    with transaction.atomic():
        locked = Domain.objects.select_for_update().select_related("tenant").get(pk=domain_id)
        if locked.verified_at is None:
            locked.status = Domain.Status.VERIFIED
            locked.verified_at = timezone.now()
            locked.save(update_fields=["status", "verified_at"])
            AuditEvent.objects.create(
                tenant=locked.tenant,
                action="domain.ownership_verified",
                target_type="domain",
                target_id=str(locked.pk),
                metadata={
                    "domain": locked.name,
                    "record_name": locked.verification_record_name,
                    "observed_values": list(result.observed_values),
                },
            )
        else:
            return VerificationResult(True, result.observed_values, already_verified=True)

    return result
