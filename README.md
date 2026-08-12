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
- Stalwart-generated DNS zone discovery and refresh;
- MX validation against the configured MailForge mail hostname;
- SPF presence and duplicate-SPF detection;
- exact DKIM validation against Stalwart's current generated `_domainkey` TXT records, including rotated selectors and split TXT chunks;
- DMARC validation;
- optional production PTR/rDNS enforcement when the server public IPv4 is configured;
- automatic transition between DNS configuration and active states;
- backend-enforced sending gate using Stalwart's per-account `emailSend` permission;
- new mailboxes created with sending already disabled when their domain is not ready;
- existing MailForge-managed mailboxes synchronized whenever readiness is checked;
- periodic Celery readiness reconciliation, configurable with `MAILFORGE_DNS_RECONCILE_MINUTES` (15 minutes by default);
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
- reply, reply-all and forward with recipient de-duplication and self-address exclusion;
- JMAP `In-Reply-To`/`References` threading metadata and answered-state updates;
- attachment upload through the JMAP upload endpoint with per-file and total limits;
- authenticated attachment download resolved from message metadata rather than arbitrary blob ids;
- original attachment reuse when forwarding;
- plain-text draft creation through `Email/set`;
- delivery through `EmailSubmission/set`;
- successful submissions moved from Drafts to Sent;
- compose blocked when the identity domain has not passed the MailForge DNS readiness gate.

### Native deployment

- native Stalwart Ubuntu installer helper;
- native Gunicorn, Celery worker and Celery beat systemd service examples;
- Nginx reverse-proxy example;
- Windows and Ubuntu no-Docker quick start;
- GitHub Actions lint, Django checks, migration-drift check and pytest suite.

## Current security boundary

MailForge now enforces sending readiness in both the webmail UI and Stalwart-managed mailbox accounts. If required DNS health is not ready, MailForge applies an explicit Stalwart `emailSend` denial to active MailForge-managed users; when readiness becomes healthy again, the user-role sending permission is restored. The periodic Celery reconciliation repeats these checks so DNS degradation does not depend only on a manual portal action.

This backend policy still needs live validation against the exact Stalwart version used on the production VPS before public onboarding. Abuse rate limits, anomaly detection and emergency suspension workflows also remain required before open signup.

## Domain onboarding

1. Add a domain to a MailForge organization.
2. Publish the displayed `_mailforge-verify` TXT challenge in DNS.
3. Verify ownership from the portal/API.
4. Provision the verified domain in Stalwart.
5. Configure the public mail hostname/IP in MailForge production settings.
6. Publish the MX, SPF, Stalwart-generated DKIM and DMARC records plus provider-managed PTR/rDNS.
7. Run **Check DNS readiness** from the domain screen.
8. Create mailboxes and forwarders. Mailboxes created before readiness remain unable to send.
9. Connect a mailbox to MailForge Webmail through Stalwart OAuth.
10. Sending becomes available only after the required DNS checks and Stalwart mailbox-policy synchronization succeed.

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
- Celery worker — background domain/mail operations;
- Celery beat — periodic DNS/readiness and Stalwart send-policy reconciliation;
- Nginx — reverse proxy for the Django portal;
- systemd — process management.

Examples are under `deploy/systemd/` and `deploy/nginx/`.

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md).

The next major milestone is a real Ubuntu/Stalwart VPS integration with a real domain, followed by MTA-STS/TLS-RPT, mailbox lifecycle controls, safe HTML rendering, abuse/rate controls and real deliverability tests to major providers.

## Security warning

Self-hosted email is reputation-sensitive infrastructure. Do not open unrestricted public registration or bulk sending before rate limits, backend-enforced abuse controls, monitoring, backup/restore drills and real-domain deliverability checks are complete.
