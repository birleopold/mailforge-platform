# MailForge Platform

A Django-based control plane for operating a secure, multi-domain email hosting service on top of **mailcow: dockerized**.

> Status: architecture + starter scaffold. Do not expose this to production users until the security, deliverability, backup, and abuse-prevention milestones in `docs/ROADMAP.md` are completed.

## Vision

MailForge is intended to let one operator host many independent organizations and domains on Ubuntu infrastructure while keeping management, quotas, billing, and access logically separated.

Examples:

- `alice@domain-a.com`
- `support@domain-b.org`
- `admin@my-personal-domain.net`

MailForge does **not** implement SMTP or IMAP itself. Django acts as the control plane while mailcow handles mail transport, mailbox storage, spam filtering, DKIM signing, IMAP/SMTP, SOGo webmail, calendars, and contacts.

## High-level architecture

```text
                         Internet
                            |
          +-----------------+-----------------+
          |                                   |
      HTTPS 443                         SMTP / IMAP
          |                                   |
+--------------------+               +----------------------+
| MailForge Django   |               | mailcow              |
| Control Plane      |  REST API     | Mail Plane           |
|                    +-------------->|                      |
| - tenants          |               | - Postfix            |
| - domains          |               | - Dovecot            |
| - mailboxes        |               | - Rspamd             |
| - billing          |               | - SOGo               |
| - quotas           |               | - DKIM               |
| - DNS checks       |               | - mailbox storage    |
| - audit logs       |               +----------------------+
| - provisioning     |
+---------+----------+
          |
     +----+-----+
     | PostgreSQL
     +----------+
          |
     +----+-----+
     | Redis /   |
     | Celery    |
     +----------+
```

## Why mailcow for v1

The project is intentionally backend-agnostic, but the first adapter targets mailcow because the free stack already supports:

- many hosted mail domains;
- domain administrators and ACLs;
- mailbox/domain quotas;
- REST API access;
- SOGo webmail, calendars, and contacts;
- Rspamd spam filtering and DKIM;
- backup/restore tooling;
- autoconfig/autodiscover and standard mail clients.

Stalwart remains a possible future backend adapter, but its native multi-tenancy feature currently belongs to its Enterprise edition.

## Tenant model

MailForge treats a **Tenant** as the commercial/security ownership boundary.

A tenant can own one or more domains. Every domain can contain multiple mailboxes and aliases.

```text
Tenant: Acme Ltd
  +- acme.com
  |    +- jane@acme.com
  |    +- sales@acme.com
  |
  +- acme.ug
       +- info@acme.ug

Tenant: Personal
  +- mydomain.com
       +- me@mydomain.com
```

A domain name is globally unique in the MailForge database. A domain cannot belong to two tenants.

## Domain onboarding flow

1. Customer enters a domain.
2. MailForge generates a unique DNS TXT ownership token.
3. Customer publishes the TXT record.
4. A Celery task verifies domain ownership.
5. MailForge provisions the domain in mailcow.
6. MailForge obtains the required DKIM value and presents the DNS checklist.
7. Customer configures MX, SPF, DKIM, DMARC, autoconfig/autodiscover and optional MTA-STS/TLS-RPT.
8. MailForge continuously checks DNS health.
9. Outbound sending is enabled only after required checks pass.

## Planned products

### Personal
For operator-owned domains. No billing, but still uses quotas and security policies.

### Hosted Mail
Paid tenant with custom domains, mailboxes, aliases, webmail, calendar, contacts, quotas, migration tools and support.

### Managed Business
Adds tenant/domain administrators, higher quotas, retention controls, custom branding, migration assistance, audit exports, and optional dedicated outbound routing.

## Important product rule

Do **not** launch as an unrestricted public bulk-mail platform.

A single abusive account can damage the reputation of the shared sending IP and affect every hosted domain. New tenants should have conservative limits, verified domains, authenticated submission, anomaly detection, and a clear acceptable-use policy.

## Repository layout

```text
mailforge-platform/
├── apps/
│   ├── tenants/
│   ├── domains/
│   ├── mailboxes/
│   ├── billing/
│   ├── provisioning/
│   └── audit/
├── mailforge/
├── integrations/
│   └── mailcow/
├── docs/
├── .github/workflows/
├── docker-compose.dev.yml
├── pyproject.toml
└── .env.example
```

## Development

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Then open the Django development server on port `8000`.

The mailcow server is intentionally **not** bundled into the development compose file. Treat the control plane and mail plane as separate systems.

## Production principles

- Ubuntu LTS host(s)
- a VPS/provider that permits SMTP port 25 and supports PTR/rDNS
- dedicated mail hostname such as `mx1.example.net`
- TLS everywhere
- Mailcow API reachable only from trusted control-plane addresses
- encrypted off-site backups
- tested recovery procedures
- monitoring of disk, queues, DNS, certificates, SMTP/IMAP, backups and IP reputation
- no secrets in Git
- admin interfaces protected by MFA and preferably VPN/IP restriction
- rate limiting and abuse controls before paid public signup

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Tenant model](docs/TENANCY.md)
- [Security](docs/SECURITY.md)
- [Deliverability](docs/DELIVERABILITY.md)
- [Domain onboarding](docs/DOMAIN_ONBOARDING.md)
- [Operations](docs/OPERATIONS.md)
- [Roadmap](docs/ROADMAP.md)
- [ADR 0001: Mailcow first](docs/adr/0001-mailcow-first.md)

## Upstream references

- mailcow documentation: https://docs.mailcow.email/
- mailcow DNS prerequisites: https://docs.mailcow.email/getstarted/prerequisite-dns/
- mailcow backup/restore: https://docs.mailcow.email/backup_restore/b_n_r-backup/
- Django supported versions: https://www.djangoproject.com/download/
- Stalwart licensing: https://stalw.art/docs/server/enterprise/

## License

A project license has intentionally not been selected yet. Decide whether you want a permissive license (for example Apache-2.0) or a copyleft/SaaS-oriented license before accepting outside contributions.
