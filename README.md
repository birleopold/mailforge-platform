# MailForge Platform

MailForge is a Django-based, multi-domain email hosting platform designed to run directly on Ubuntu without Docker.

## Goal

Host independent custom email domains such as:

- `you@personal-domain.com`
- `sales@company-a.com`
- `support@company-b.ug`

Each customer/domain stays logically separated in MailForge, while the actual mail protocols and storage are handled by **Stalwart Mail Server**.

## Why Stalwart

Stalwart runs as a native Linux service and provides SMTP, IMAP, JMAP, CalDAV, CardDAV, WebDAV, spam/phishing filtering, DKIM and modern account/domain management APIs. MailForge uses Django as the customer-facing control plane and will progressively build its own Gmail-style web client over JMAP.

Docker is not required by this project.

## Architecture

```text
Browser / Mobile
      |
      v
+---------------------------+
| MailForge Django          |
|                           |
| Customer portal           |
| Gmail-style web UI        |
| Tenants / domains         |
| Billing / plans           |
| DNS verification          |
| Audit / abuse controls    |
+------------+--------------+
             |
             | JMAP / HTTPS
             v
+---------------------------+
| Stalwart Mail Server      |
| native Ubuntu service     |
|                           |
| SMTP / IMAP / JMAP        |
| Calendars / contacts      |
| Files / filtering         |
| DKIM / mail storage       |
+---------------------------+
```

## Important tenancy rule

Stalwart Community Edition can host multiple domains and accounts, but its native **Tenant** object is an Enterprise feature. MailForge therefore owns tenant authorization in Django for the free/community deployment: customers do not receive Stalwart administrator access; every management action is checked in Django and executed through a restricted service API credential.

For customers that later require hard infrastructure isolation, MailForge can support a dedicated Stalwart instance/host or an Enterprise-backed tenant mode.

## Domain onboarding

1. Customer adds a domain to MailForge.
2. MailForge generates a unique TXT ownership token.
3. Customer publishes the TXT record in DNS.
4. MailForge verifies ownership asynchronously.
5. MailForge provisions the domain in Stalwart through JMAP.
6. The dashboard displays MX, SPF, DKIM, DMARC and other DNS records.
7. Mailboxes and aliases can then be created.
8. Sending remains subject to abuse and deliverability policies.

## Local development on Windows or Linux

No Docker is needed.

```bash
python -m venv .venv
```

Windows:

```bat
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
copy .env.example .env
python manage.py migrate
python manage.py runserver
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Development falls back to SQLite when `DATABASE_URL` is not configured. Production should use PostgreSQL.

## Production Ubuntu services

Recommended native services:

- Stalwart Mail Server — mail and collaboration backend
- Django + Gunicorn — MailForge application
- PostgreSQL — application database
- Redis — Celery queue/cache
- Celery — provisioning and DNS jobs
- Nginx — reverse proxy for the Django portal if required
- systemd — service management

## Current implementation

- tenant and membership data model;
- domain ownership token model;
- DNS TXT ownership verifier;
- retry-safe Celery verification task;
- audit event for successful verification;
- initial Django migrations;
- Stalwart JMAP adapter foundation;
- mailbox/domain backend methods;
- no-Docker deployment direction.

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md).

The next product-facing milestone is the tenant/domain REST API and dashboard, followed by mailbox lifecycle management and the JMAP-based inbox UI.

## Security warning

Self-hosted email is reputation-sensitive infrastructure. Do not open unrestricted public registration or bulk sending before rate limits, abuse handling, monitoring, backup/restore drills and DNS/deliverability checks are complete.
