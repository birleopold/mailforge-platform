from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import dns.exception
import dns.resolver
import httpx


_MTA_STS_ID = re.compile(r"^[A-Za-z0-9]{1,32}$")
_MAX_MTA_STS_POLICY_BYTES = 64 * 1024


def _txt_value(record) -> str:
    strings = getattr(record, "strings", None)
    if strings is not None:
        return b"".join(strings).decode("utf-8", errors="replace")
    return record.to_text().replace('" "', "").strip('"')


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


def _semicolon_tags(value: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for part in value.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, raw_value = part.split("=", 1)
        key = key.strip().lower()
        if key not in tags:
            tags[key] = raw_value.strip()
    return tags


def _mx_matches_pattern(host: str, pattern: str) -> bool:
    host = host.rstrip(".").lower()
    pattern = pattern.rstrip(".").lower()
    if pattern.startswith("*."):
        suffix = pattern[2:]
        if not host.endswith(f".{suffix}"):
            return False
        prefix = host[: -(len(suffix) + 1)]
        return bool(prefix) and "." not in prefix
    return host == pattern


def _parse_mta_sts_policy(text: str) -> tuple[dict[str, str], list[str], list[str]]:
    fields: dict[str, str] = {}
    mx_patterns: list[str] = []
    errors: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            errors.append(f"Invalid policy line: {line}")
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            errors.append(f"Invalid policy line: {line}")
            continue
        if key == "mx":
            mx_patterns.append(value.lower().rstrip("."))
        elif key not in fields:
            fields[key] = value

    if fields.get("version") != "STSv1":
        errors.append("Policy version must be STSv1.")
    if fields.get("mode") not in {"enforce", "testing", "none"}:
        errors.append("Policy mode must be enforce, testing, or none.")
    max_age = fields.get("max_age", "")
    if not max_age.isdigit() or int(max_age) > 31557600:
        errors.append("Policy max_age must be an integer from 0 to 31557600.")
    if fields.get("mode") != "none" and not mx_patterns:
        errors.append("Policy must contain at least one mx entry unless mode is none.")
    for pattern in mx_patterns:
        if pattern.startswith("*."):
            candidate = pattern[2:]
        else:
            candidate = pattern
        if not candidate or "*" in candidate or "." not in candidate:
            errors.append(f"Invalid mx pattern: {pattern}")

    return fields, mx_patterns, errors


def check_mta_sts(resolver, domain_name: str, *, http_get=None) -> dict[str, Any]:
    record_name = f"_mta-sts.{domain_name}"
    expected_policy_url = f"https://mta-sts.{domain_name}/.well-known/mta-sts.txt"
    answer = _resolve(resolver, record_name, "TXT")
    if answer is None:
        return {
            "status": "warn",
            "required": False,
            "expected": [
                f"{record_name} TXT v=STSv1; id=<policy-id>;",
                expected_policy_url,
            ],
            "observed": [],
            "detail": "MTA-STS DNS lookup temporarily failed.",
        }

    values = [_txt_value(record).strip() for record in answer]
    records = [value for value in values if value.startswith("v=STSv1;")]
    if len(records) != 1:
        detail = "Publish one MTA-STS TXT record beginning with v=STSv1;."
        if len(records) > 1:
            detail = "Multiple MTA-STS TXT records were found; publish exactly one usable policy record."
        return {
            "status": "fail",
            "required": False,
            "expected": [
                f"{record_name} TXT v=STSv1; id=<policy-id>;",
                expected_policy_url,
            ],
            "observed": records,
            "detail": detail,
        }

    tags = _semicolon_tags(records[0])
    policy_id = tags.get("id", "")
    if tags.get("v") != "STSv1" or not _MTA_STS_ID.fullmatch(policy_id):
        return {
            "status": "fail",
            "required": False,
            "expected": f"{record_name} TXT v=STSv1; id=<1-32 letters-or-digits>;",
            "observed": records,
            "detail": "The MTA-STS TXT record has an invalid or missing policy id.",
        }

    getter = http_get or httpx.get
    try:
        response = getter(
            expected_policy_url,
            timeout=5.0,
            follow_redirects=False,
            headers={"Accept": "text/plain"},
        )
    except httpx.HTTPError as exc:
        return {
            "status": "warn",
            "required": False,
            "expected": expected_policy_url,
            "observed": records,
            "detail": f"MTA-STS TXT is valid, but the HTTPS policy could not be fetched: {exc}",
        }
    except Exception as exc:
        return {
            "status": "warn",
            "required": False,
            "expected": expected_policy_url,
            "observed": records,
            "detail": f"MTA-STS TXT is valid, but the HTTPS policy could not be fetched: {exc}",
        }

    if response.status_code != 200:
        return {
            "status": "fail",
            "required": False,
            "expected": f"HTTP 200 from {expected_policy_url} without redirects",
            "observed": [f"HTTP {response.status_code}", *records],
            "detail": "The MTA-STS policy endpoint must return HTTP 200; redirects are not valid policy responses.",
        }

    content = response.content
    if len(content) > _MAX_MTA_STS_POLICY_BYTES:
        return {
            "status": "fail",
            "required": False,
            "expected": "MTA-STS policy no larger than 64 KiB",
            "observed": [f"{len(content)} bytes", *records],
            "detail": "The MTA-STS policy is larger than the MailForge validation limit.",
        }

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "text/plain":
        return {
            "status": "fail",
            "required": False,
            "expected": "Content-Type: text/plain",
            "observed": [response.headers.get("content-type", ""), *records],
            "detail": "Serve the MTA-STS policy as text/plain.",
        }

    fields, mx_patterns, errors = _parse_mta_sts_policy(response.text)
    if errors:
        return {
            "status": "fail",
            "required": False,
            "expected": "Valid STSv1 policy with mode, max_age, and mx entries",
            "observed": [*records, *errors],
            "detail": "The HTTPS MTA-STS policy is syntactically invalid.",
        }

    uncovered_mx: list[str] = []
    mx_answer = _resolve(resolver, domain_name, "MX")
    if mx_answer is None:
        return {
            "status": "warn",
            "required": False,
            "expected": mx_patterns,
            "observed": records,
            "detail": "MTA-STS policy is valid, but MX coverage could not be checked temporarily.",
        }
    public_mx = sorted({str(record.exchange).rstrip(".").lower() for record in mx_answer})
    if fields.get("mode") != "none":
        uncovered_mx = [
            host
            for host in public_mx
            if not any(_mx_matches_pattern(host, pattern) for pattern in mx_patterns)
        ]
    if uncovered_mx:
        return {
            "status": "fail",
            "required": False,
            "expected": mx_patterns,
            "observed": public_mx,
            "detail": "MTA-STS policy does not cover these published MX hosts: "
            + ", ".join(uncovered_mx),
        }

    mode = fields.get("mode", "")
    return {
        "status": "pass",
        "required": False,
        "expected": [records[0], expected_policy_url],
        "observed": [
            f"id={policy_id}",
            f"mode={mode}",
            f"max_age={fields.get('max_age')}",
            *(f"mx={item}" for item in mx_patterns),
        ],
        "detail": f"Valid MTA-STS policy published in {mode} mode and covers the public MX set.",
    }


def _valid_tlsrpt_uri(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme == "mailto":
        return bool(parsed.path and "@" in parsed.path)
    if parsed.scheme == "https":
        return bool(parsed.netloc)
    return False


def check_tls_reporting(resolver, domain_name: str) -> dict[str, Any]:
    record_name = f"_smtp._tls.{domain_name}"
    answer = _resolve(resolver, record_name, "TXT")
    if answer is None:
        return {
            "status": "warn",
            "required": False,
            "expected": f"{record_name} TXT v=TLSRPTv1; rua=mailto:tls-reports@{domain_name}",
            "observed": [],
            "detail": "TLS-RPT DNS lookup temporarily failed.",
        }

    values = [_txt_value(record).strip() for record in answer]
    records = [value for value in values if value.startswith("v=TLSRPTv1;")]
    if len(records) != 1:
        detail = "Publish one TLS-RPT TXT record beginning with v=TLSRPTv1;."
        if len(records) > 1:
            detail = "Multiple usable TLS-RPT records were found; publish exactly one."
        return {
            "status": "fail",
            "required": False,
            "expected": f"{record_name} TXT v=TLSRPTv1; rua=mailto:tls-reports@{domain_name}",
            "observed": records,
            "detail": detail,
        }

    tags = _semicolon_tags(records[0])
    rua = [item.strip() for item in tags.get("rua", "").split(",") if item.strip()]
    if tags.get("v") != "TLSRPTv1" or not rua or any(not _valid_tlsrpt_uri(item) for item in rua):
        return {
            "status": "fail",
            "required": False,
            "expected": "v=TLSRPTv1; rua=<mailto: or https: report endpoint>",
            "observed": records,
            "detail": "The TLS-RPT record must contain at least one valid mailto: or https: rua endpoint.",
        }

    return {
        "status": "pass",
        "required": False,
        "expected": records[0],
        "observed": rua,
        "detail": "A valid SMTP TLS reporting policy is published.",
    }
