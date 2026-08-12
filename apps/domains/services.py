from __future__ import annotations

from dataclasses import dataclass

import dns.exception
import dns.resolver


class DomainVerificationTemporaryError(RuntimeError):
    """Raised when DNS verification should be retried later."""


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    observed_values: tuple[str, ...]


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
