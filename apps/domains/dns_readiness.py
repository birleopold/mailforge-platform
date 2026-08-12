from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import dns.exception
import dns.name
import dns.resolver
import dns.reversename
import dns.rdatatype
import dns.zone
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from integrations.factory import (
    MailBackendConfigurationError,
    UnsupportedMailBackend,
    get_mail_backend,
)
from integrations.stalwart.client import StalwartAPIError


@dataclass(frozen=True)
class DNSReadinessResult:
    ready: bool
    checks: dict[str, dict[str, Any]]


def _txt_value(record) -> str:
    strings = getattr(record, "strings", None)
    if strings is not None:
        return b"".join(strings).decode("utf-8", errors="replace")
    return record.to_text().replace('" "', "").strip('"')


def _normalized_txt(value: str) -> str:
    return "".join(value.split())


def extract_dkim_records(zone_file: str, domain_name: str) -> list[dict[str, str]] | None:
    if not zone_file.strip():
        return None
    try:
        zone = dns.zone.from_text(
            zone_file,
            origin=dns.name.from_text(f"{domain_name}."),
            relativize=False,
            check_origin=False,
            allow_include=False,
        )
    except (dns.exception.DNSException, ValueError):
        return None

    suffix = f"._domainkey.{domain_name}".lower()
    records = []
    seen = set()
    for record_name, node in zone.nodes.items():
        name = record_name.to_text().rstrip(".").lower()
        if not name.endswith(suffix):
            continue
        for rdataset in node.rdatasets:
            if rdataset.rdtype != dns.rdatatype.TXT:
                continue
            for record in rdataset:
                value = _txt_value(record).strip()
                if not value.lower().startswith("v=dkim1"):
                    continue
                key = (name, _normalized_txt(value))
                if key in seen:
                    continue
                records.append({"name": name, "value": value})
                seen.add(key)
    return sorted(records, key=lambda item: (item["name"], item["value"]))


def _resolve(resolver, name: str, record_type: str):
    try:
        return resolver.resolve(name, record_type, lifetime=5.0, search=False)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return ()
    except (
        dns.resolver.NoNameservers,
        dns.resolver.LifetimeTimeout,
        dns.exception.Timeout,
    ):
        return None


def _check_mx(resolver, domain_name: str, mail_hostname: str) -> dict[str, Any]:
    if not mail_hostname:
        return {
            "status": "fail",
            "required": True,
            "expected": "Configure MAILFORGE_MAIL_HOSTNAME",
            "observed": [],
            "detail": "MailForge does not yet know the public mail hostname.",
        }

    answer = _resolve(resolver, domain_name, "MX")
    if answer is None:
        return {
            "status": "warn",
            "required": True,
            "expected": mail_hostname,
            "observed": [],
            "detail": "MX lookup temporarily failed.",
        }

    observed = sorted({str(record.exchange).rstrip(".").lower() for record in answer})
    target = mail_hostname.rstrip(".").lower()
    passed = target in observed
    return {
        "status": "pass" if passed else "fail",
        "required": True,
        "expected": target,
        "observed": observed,
        "detail": "MX points to the MailForge mail host." if passed else "Add an MX record pointing to the MailForge mail host.",
    }


def _check_spf(resolver, domain_name: str) -> dict[str, Any]:
    answer = _resolve(resolver, domain_name, "TXT")
    if answer is None:
        return {
            "status": "warn",
            "required": True,
            "expected": "v=spf1 mx -all",
            "observed": [],
            "detail": "SPF lookup temporarily failed.",
        }

    values = [_txt_value(record).strip() for record in answer]
    spf_records = [value for value in values if value.lower().startswith("v=spf1")]
    passed = len(spf_records) == 1
    detail = "A single SPF policy is published."
    if not spf_records:
        detail = "Publish an SPF TXT record for this domain."
    elif len(spf_records) > 1:
        detail = "Multiple SPF records are published; combine them into one policy."
    return {
        "status": "pass" if passed else "fail",
        "required": True,
        "expected": "v=spf1 mx -all",
        "observed": spf_records,
        "detail": detail,
    }


def _check_dkim(resolver, expected_records: list[dict[str, str]] | None) -> dict[str, Any]:
    if expected_records is None:
        return {
            "status": "warn",
            "required": True,
            "expected": "Stalwart-generated _domainkey TXT records",
            "observed": [],
            "detail": "Stalwart's current DKIM DNS expectation is not available yet.",
        }
    if not expected_records:
        return {
            "status": "fail",
            "required": True,
            "expected": "Stalwart-generated _domainkey TXT records",
            "observed": [],
            "detail": "Stalwart's DNS zone does not currently contain an active DKIM TXT record.",
        }

    expected_display = [f"{item['name']}={item['value']}" for item in expected_records]
    observed_display = []
    failed_names = []
    temporary_names = []

    for item in expected_records:
        answer = _resolve(resolver, item["name"], "TXT")
        if answer is None:
            temporary_names.append(item["name"])
            continue
        observed_values = [_txt_value(record).strip() for record in answer]
        observed_display.extend(f"{item['name']}={value}" for value in observed_values)
        expected_value = _normalized_txt(item["value"])
        if expected_value not in {_normalized_txt(value) for value in observed_values}:
            failed_names.append(item["name"])

    if failed_names:
        status = "fail"
        detail = "Publish the exact Stalwart DKIM TXT record(s): " + ", ".join(failed_names)
    elif temporary_names:
        status = "warn"
        detail = "DKIM lookup temporarily failed for: " + ", ".join(temporary_names)
    else:
        status = "pass"
        detail = "All active Stalwart DKIM signing records are published."

    return {
        "status": status,
        "required": True,
        "expected": expected_display,
        "observed": observed_display,
        "detail": detail,
    }


def _check_dmarc(resolver, domain_name: str) -> dict[str, Any]:
    record_name = f"_dmarc.{domain_name}"
    answer = _resolve(resolver, record_name, "TXT")
    if answer is None:
        return {
            "status": "warn",
            "required": True,
            "expected": "v=DMARC1; p=quarantine",
            "observed": [],
            "detail": "DMARC lookup temporarily failed.",
        }

    values = [_txt_value(record).strip() for record in answer]
    dmarc_records = [value for value in values if value.lower().startswith("v=dmarc1")]
    has_policy = False
    if len(dmarc_records) == 1:
        tags = {
            part.split("=", 1)[0].strip().lower(): part.split("=", 1)[1].strip().lower()
            for part in dmarc_records[0].split(";")
            if "=" in part
        }
        has_policy = tags.get("p") in {"none", "quarantine", "reject"}
    passed = len(dmarc_records) == 1 and has_policy
    return {
        "status": "pass" if passed else "fail",
        "required": True,
        "expected": "v=DMARC1; p=quarantine",
        "observed": dmarc_records,
        "detail": "A valid DMARC policy is published." if passed else "Publish one DMARC TXT record with a valid p= policy.",
    }


def _check_ptr(resolver, mail_ipv4: str, mail_hostname: str) -> dict[str, Any]:
    if not mail_ipv4:
        return {
            "status": "skip",
            "required": False,
            "expected": mail_hostname or "mail host",
            "observed": [],
            "detail": "Set MAILFORGE_MAIL_IPV4 in production to enforce PTR/rDNS readiness.",
        }
    if not mail_hostname:
        return {
            "status": "fail",
            "required": True,
            "expected": "Configure MAILFORGE_MAIL_HOSTNAME",
            "observed": [],
            "detail": "A mail hostname is required before PTR can be validated.",
        }

    try:
        reverse_name = dns.reversename.from_address(mail_ipv4)
    except ValueError:
        return {
            "status": "fail",
            "required": True,
            "expected": mail_hostname,
            "observed": [mail_ipv4],
            "detail": "MAILFORGE_MAIL_IPV4 is not a valid IP address.",
        }

    answer = _resolve(resolver, str(reverse_name), "PTR")
    if answer is None:
        return {
            "status": "warn",
            "required": True,
            "expected": mail_hostname,
            "observed": [],
            "detail": "PTR lookup temporarily failed.",
        }

    observed = sorted({str(record.target).rstrip(".").lower() for record in answer})
    target = mail_hostname.rstrip(".").lower()
    passed = target in observed
    return {
        "status": "pass" if passed else "fail",
        "required": True,
        "expected": target,
        "observed": observed,
        "detail": "PTR/rDNS matches the MailForge mail host." if passed else "Ask the VPS provider to set PTR/rDNS to the MailForge mail hostname.",
    }


def _refresh_dns_zone_file(domain: Domain, *, backend=None) -> str:
    if not domain.backend_identifier:
        return domain.dns_zone_file
    try:
        backend = backend or get_mail_backend()
    except (MailBackendConfigurationError, UnsupportedMailBackend):
        return domain.dns_zone_file

    getter = getattr(backend, "get_domain", None)
    if getter is None:
        return domain.dns_zone_file
    try:
        snapshot = getter(domain.backend_identifier)
    except StalwartAPIError:
        return domain.dns_zone_file

    fresh_zone = str(snapshot.get("dnsZoneFile") or "")
    if fresh_zone and fresh_zone != domain.dns_zone_file:
        Domain.objects.filter(pk=domain.pk).update(dns_zone_file=fresh_zone)
        domain.dns_zone_file = fresh_zone
    return domain.dns_zone_file


def inspect_domain_dns(
    domain_name: str,
    *,
    resolver=None,
    dkim_records: list[dict[str, str]] | None = None,
) -> DNSReadinessResult:
    resolver = resolver or dns.resolver.Resolver()
    mail_hostname = settings.MAILFORGE_MAIL_HOSTNAME.strip().rstrip(".").lower()
    mail_ipv4 = settings.MAILFORGE_MAIL_IPV4.strip()

    checks = {
        "mx": _check_mx(resolver, domain_name, mail_hostname),
        "spf": _check_spf(resolver, domain_name),
        "dkim": _check_dkim(resolver, dkim_records),
        "dmarc": _check_dmarc(resolver, domain_name),
        "ptr": _check_ptr(resolver, mail_ipv4, mail_hostname),
    }
    ready = all(
        check["status"] == "pass"
        for check in checks.values()
        if check["required"]
    )
    return DNSReadinessResult(ready=ready, checks=checks)


def check_domain_dns(
    domain_id: int,
    *,
    actor=None,
    resolver=None,
    backend=None,
) -> DNSReadinessResult:
    domain = Domain.objects.select_related("tenant").get(pk=domain_id)
    zone_file = _refresh_dns_zone_file(domain, backend=backend)
    dkim_records = extract_dkim_records(zone_file, domain.name)
    result = inspect_domain_dns(
        domain.name,
        resolver=resolver,
        dkim_records=dkim_records,
    )
    now = timezone.now()

    with transaction.atomic():
        locked = Domain.objects.select_for_update().select_related("tenant").get(pk=domain_id)
        previous_sending = locked.sending_enabled
        can_send = bool(
            result.ready
            and locked.verified_at
            and locked.backend_identifier
            and locked.status not in {Domain.Status.SUSPENDED, Domain.Status.DECOMMISSIONED}
        )
        locked.dns_checks = result.checks
        locked.dns_checked_at = now
        locked.sending_enabled = can_send
        update_fields = ["dns_checks", "dns_checked_at", "sending_enabled"]

        if locked.status not in {Domain.Status.SUSPENDED, Domain.Status.DECOMMISSIONED}:
            next_status = Domain.Status.ACTIVE if can_send else (
                Domain.Status.DNS_CONFIGURATION if locked.backend_identifier else locked.status
            )
            if next_status != locked.status:
                locked.status = next_status
                update_fields.append("status")

        locked.save(update_fields=update_fields)

        if previous_sending != can_send:
            AuditEvent.objects.create(
                tenant=locked.tenant,
                actor=actor,
                action="domain.sending_readiness_changed",
                target_type="domain",
                target_id=str(locked.pk),
                metadata={
                    "domain": locked.name,
                    "sending_enabled": can_send,
                    "checks": result.checks,
                },
            )

    return result
