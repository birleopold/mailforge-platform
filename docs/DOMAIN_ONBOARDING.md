# Domain onboarding

## Step 1 — Add domain

Customer enters a fully-qualified domain such as `example.com`.

MailForge normalizes the name, rejects invalid values and enforces global uniqueness.

## Step 2 — Prove ownership

MailForge generates a TXT challenge:

```text
Type: TXT
Name: _mailforge-verify.example.com
Value: mailforge-verification=<random-token>
```

A Celery task checks DNS asynchronously. Missing records are treated as not-yet-verified; temporary DNS resolver failures are retried.

## Step 3 — Provision in Stalwart

After verification, MailForge provisions a Stalwart Domain through the management JMAP API and stores the backend identifier.

Customers do not receive Stalwart administrator access.

## Step 4 — DNS checklist

MailForge should display required/observed values for:

- MX;
- SPF;
- DKIM;
- DMARC;
- mail host A/AAAA;
- PTR/rDNS guidance;
- autoconfig/autodiscover;
- MTA-STS and TLS-RPT when enabled.

## Step 5 — Activate mailboxes

Mailbox creation is allowed after domain ownership is verified. Outbound sending may be held until required deliverability/safety checks are satisfied.

## Step 6 — Continuous health

Periodically re-check DNS and certificate/routing state. Temporary DNS failures should create warnings rather than immediately deleting or disabling customer data.
