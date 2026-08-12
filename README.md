# MailForge Platform

MailForge is a Django-based, multi-domain email hosting platform designed to run directly on Ubuntu without Docker.

## Goal

Host independent custom email domains such as:

- `you@personal-domain.com`
- `sales@company-a.com`
- `support@company-b.ug`

Each customer/domain stays logically separated in MailForge, while the actual mail protocols and storage are handled by **Stalwart Mail Server**.

## Why Stalwart

Stalwart runs as a native Linux service and provides SMTP, IMAP, JMAP, CalDAV, CardDAV, WebDAV, filtering, DKIM and modern account/domain management APIs. MailForge uses Django as the customer-facing control plane and is building its own webmail experience over user-scoped JMAP access.

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
| DNS/readiness gate        |
| OAuth-backed webmail      |
| Tenants / domains         |
| Mailboxes / forwarders    |
| Audit / quotas            |
+------------+--------------+
             |
             | HTTPS / JMAP
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

Stalwart Community Edition can host multiple domains and accounts, but MailForge owns customer authorization for the community deployment: customers do not receive the Stalwart management credential; management actions are tenant-scoped in Django and executed through a service credential.

Mailbox webmail access is deliberately separate from the management credential. A mailbox user connects through Stalwart OAuth and receives a user-scoped JMAP access token for that browser session.

For customers that later require hard infrastructure isolation, MailForge can support a dedicated Stalwart instance/host or an Enterprise-backed tenant mode.

## What works now

The current `main` branch includes:

### Control plane

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
- Django admin operator console.

### DNS and sending readiness

- persisted DNS readiness snapshots per domain;
- MX validation against the configured MailForge mail hostname;
- SPF presence and duplicate-SPF detection;
- DMARC validation;
- optional production PTR/rDNS enforcement when the server public IPv4 is configured;
- automatic transition between DNS configuration and active states;
- application-level sending gate that disables MailForge webmail sending when required DNS health is lost;
- audit events when sending readiness changes.

### MailForge webmail MVP

- separate user-scoped Stalwart OAuth Authorization Code + PKCE connection flow;
- OAuth access/refresh tokens encrypted before storage in the Django session;
- JMAP session discovery and primary mail-account selection;
- mailbox/folder sidebar and unread counts;
- recent message list;
- safe plain-text message reader;
- raw HTML email deliberately not rendered yet;
- automatic mark-as-read when a message is opened;
- mark-unread action;
- server-side JMAP mail search;
- validated compose form with To/Cc/Bcc;
- sending identity restricted to identities returned by Stalwart;
- plain-text draft creation through `Email/set`;
- delivery through `EmailSubmission/set`;
- successful submissions moved from Drafts to Sent;
- compose blocked when the identity domain has not passed the MailForge DNS readiness gate.

### Native deployment

- native Stalwart Ubuntu installer helper;
- native Gunicorn/Celery systemd service examples;
- Nginx reverse-proxy example;
- Windows and Ubuntu no-Docker quick start;
- GitHub Actions lint, Django checks, migration-drift check and pytest suite.

## Current security boundary

The MailForge webmail and control-plane sending path is gated by MailForge's DNS readiness state. **Direct authenticated SMTP submission to Stalwart is not yet synchronized with that Django-side gate.** Before public onboarding, Stalwart-side submission permissions/rules and abuse-rate controls must be wired to the same suspension/readiness decisions so customers cannot bypass the control plane by using SMTP directly.

## Domain onboarding

1. Add a domain to a MailForge organization.
2. Publish the displayed `_mailforge-verify` TXT challenge in DNS.
3. Verify ownership from the portal/API.
4. Provision the verified domain in Stalwart.
5. Configure the public mail hostname/IP in MailForge production settings.
6. Publish the required MX, SPF and DMARC records plus provider-managed PTR/rDNS.
7. Run **Check DNS readiness** from the domain screen.
8. Create mailboxes and forwarders.
9. Connect a mailbox to MailForge Webmail through Stalwart OAuth.
10. Sending from MailForge becomes available only when the domain is active and the readiness gate is healthy.

DKIM discovery/validation and stronger backend-level sending enforcement are still upcoming deliverability work.

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
- Django + Gunicorn — MailForge control plane and webmail;
- PostgreSQL — application database;
- Redis — Celery broker/cache;
- Celery — background verification/provisioning work;
- Nginx — reverse proxy for the Django portal;
- systemd — process management.

Examples are under `deploy/systemd/` and `deploy/nginx/`.

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md).

The next major milestone is a real Ubuntu/Stalwart VPS integration with a real domain, followed by DKIM/deliverability hardening, attachment handling, reply/forward, HTML sanitization and SMTP-side enforcement of MailForge suspension/readiness policies.

## Security warning

Self-hosted email is reputation-sensitive infrastructure. Do not open unrestricted public registration or bulk sending before rate limits, backend-enforced abuse controls, monitoring, backup/restore drills and deliverability checks are complete.
