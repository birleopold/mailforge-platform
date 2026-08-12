# MailForge Platform

MailForge is a Django-based, multi-domain email hosting platform designed to run directly on Ubuntu without Docker.

## Goal

Host independent custom email domains such as:

- `you@personal-domain.com`
- `sales@company-a.com`
- `support@company-b.ug`

Each customer/domain stays logically separated in MailForge, while the actual mail protocols and storage are handled by **Stalwart Mail Server**.

## Why Stalwart

Stalwart runs as a native Linux service and provides SMTP, IMAP, JMAP, CalDAV, CardDAV, WebDAV, filtering, DKIM and modern account/domain management APIs. MailForge uses Django as the customer-facing control plane and will progressively build its own Gmail-style web client over JMAP.

**Docker is not required by this project.**

## Architecture

```text
Browser / Mobile
      |
      v
+---------------------------+
| MailForge Django          |
|                           |
| Browser control portal    |
| Tenant-scoped REST API    |
| Tenants / domains         |
| Mailboxes / forwarders    |
| DNS verification          |
| Audit / quotas            |
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

Stalwart Community Edition can host multiple domains and accounts, but its native **Tenant** object is an Enterprise feature. MailForge therefore owns customer authorization in Django for the free/community deployment: customers do not receive Stalwart administrator access; management actions are tenant-scoped in Django and executed through a service credential.

For customers that later require hard infrastructure isolation, MailForge can support a dedicated Stalwart instance/host or an Enterprise-backed tenant mode.

## What works now

The current `main` branch includes:

- Django login and browser management portal;
- isolated organizations/tenants and owner memberships;
- tenant-scoped REST API;
- domain normalization and global uniqueness;
- DNS TXT ownership verification;
- retry-safe Celery verification jobs;
- verified-domain provisioning into Stalwart through management JMAP;
- mailbox list/create service and API with configurable quotas;
- mailbox passwords treated as write-only provisioning input and not stored in Django models;
- forwarding addresses backed by Stalwart mailing lists;
- protection against mailbox/forwarder address collisions and self-forwarding loops;
- audit events for privileged provisioning actions;
- Django admin operator console;
- native Stalwart Ubuntu installer helper;
- native Gunicorn/Celery systemd service examples and Nginx reverse-proxy example;
- GitHub Actions lint, Django checks, migration-drift check and pytest suite.

The full Gmail-style inbox, compose UI, search, contacts, calendar and file interface are **future phases**, not completed features yet.

## Domain onboarding

1. Add a domain to a MailForge organization.
2. Publish the displayed `_mailforge-verify` TXT challenge in DNS.
3. Verify ownership from the portal/API.
4. Provision the verified domain in Stalwart.
5. Configure the actual mail DNS records (MX, SPF, DKIM, DMARC and mail hostname records).
6. Create mailboxes and forwarders.
7. Keep sending restricted until deliverability and abuse checks are complete.

## Quick local start on Windows

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/` and sign in with the superuser you created.

Local development falls back to SQLite when `DATABASE_URL` is empty. Production should use PostgreSQL.

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for the no-Docker Windows/Ubuntu walkthrough.

## Production Ubuntu services

Recommended native services:

- Stalwart Mail Server — mail and collaboration backend;
- Django + Gunicorn — MailForge control plane;
- PostgreSQL — application database;
- Redis — Celery broker/cache;
- Celery — background verification/provisioning work;
- Nginx — reverse proxy for the Django portal;
- systemd — process management.

Examples are under `deploy/systemd/` and `deploy/nginx/`.

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md).

The next major product milestone is **live VPS integration and deliverability/DNS health**, followed by safe mailbox-user authentication and the JMAP-based Gmail-style inbox.

## Security warning

Self-hosted email is reputation-sensitive infrastructure. Do not open unrestricted public registration or bulk sending before rate limits, abuse handling, monitoring, backup/restore drills and deliverability checks are complete.
