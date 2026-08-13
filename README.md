# MailForge Platform

MailForge is a Django-based, multi-domain email hosting platform designed to run directly on Ubuntu without Docker.

## Goal

Host independent custom email domains such as:

- `you@personal-domain.com`
- `sales@company-a.com`
- `support@company-b.ug`

Each customer/domain stays logically separated in MailForge, while the actual mail protocols and storage are handled by **Stalwart Mail Server**.

## Why Stalwart

Stalwart runs as a native Linux service and provides SMTP, IMAP, JMAP, CalDAV, CardDAV, WebDAV, filtering, DKIM and modern account/domain management APIs. MailForge uses Django as the customer-facing control plane and builds its own webmail experience over user-scoped JMAP access.

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
- isolated organizations/tenants with owner, administrator, billing and viewer roles;
- tenant-scoped REST API;
- expiring tenant invitations with one-time tokens whose raw values are never stored in the database;
- invited-only portal account creation and invitation acceptance bound to the invited email address;
- invitation revocation, member role changes and member removal with owner protections;
- domain normalization and global uniqueness;
- DNS TXT ownership verification;
- retry-safe Celery verification jobs;
- verified-domain provisioning into Stalwart through management JMAP;
- mailbox list/create service and API with configurable quotas;
- mailbox passwords treated as write-only provisioning input and not stored in Django models;
- browser/API mailbox suspend and reactivate controls;
- targeted mailbox password reset that does not persist the password in MailForge;
- permanent mailbox backend deletion with an inactive MailForge tombstone so the old address remains reserved;
- forwarding addresses backed by Stalwart mailing lists;
- forwarder destination update and confirmed deletion through both REST and the browser portal;
- deleted forwarder addresses retained as inactive MailForge tombstones rather than silently recycled;
- emergency tenant/domain suspension and rollback-safe reactivation controls;
- protection against mailbox/forwarder address collisions and self-forwarding loops;
- audit events for privileged provisioning, membership and lifecycle actions;
- Django admin operator console.

### DNS, transport security and sending readiness

- persisted DNS readiness snapshots per domain;
- Stalwart-generated DNS zone discovery and refresh;
- MX validation against the configured MailForge mail hostname;
- SPF presence and duplicate-SPF detection;
- exact DKIM validation against Stalwart's current generated `_domainkey` TXT records, including rotated selectors and split TXT chunks;
- DMARC validation;
- optional production PTR/rDNS enforcement when the server public IPv4 is configured;
- MTA-STS TXT and HTTPS policy validation, including policy syntax and public-MX coverage;
- TLS-RPT TXT/report-endpoint validation;
- MTA-STS and TLS-RPT are currently recommended, non-gating checks;
- automatic transition between DNS configuration and active states;
- backend-enforced sending gate using Stalwart's per-account `emailSend` permission;
- new mailboxes created with sending already disabled when their domain is not ready;
- existing MailForge-managed mailboxes synchronized whenever readiness is checked;
- periodic Celery readiness reconciliation, configurable with `MAILFORGE_DNS_RECONCILE_MINUTES` (15 minutes by default);
- emergency-suspended domains use the stronger full Stalwart mailbox-permission revocation during periodic reconciliation rather than the normal send-only block;
- audit events when sending readiness changes.

### MailForge webmail

- separate user-scoped Stalwart OAuth Authorization Code + PKCE connection flow;
- OAuth access/refresh tokens encrypted before storage in the Django session;
- JMAP session discovery and primary mail-account selection;
- mailbox/folder sidebar and unread counts;
- recent message list;
- server-side mail search;
- safe plain-text message reader;
- sanitized HTML email rendering using a strict allowlist;
- scripts, iframes, embedded objects, SVG, forms, inline styles, event handlers and unsafe URL schemes removed from HTML mail;
- remote images are not loaded, preventing ordinary tracking-pixel requests, and MailForge displays a privacy notice when images were blocked;
- plain-text alternatives remain available when supplied by the message;
- automatic mark-as-read when a message is opened;
- mark-unread action;
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
- configurable SMTP delivery for tenant invitation emails;
- Nginx reverse-proxy example;
- Windows and Ubuntu no-Docker quick start;
- GitHub Actions lint, Django checks, migration-drift check and pytest suite.

## Current security boundary

MailForge enforces normal sending readiness in both the webmail UI and Stalwart-managed mailbox accounts. If required DNS health is not ready, MailForge applies an explicit Stalwart `emailSend` denial to active MailForge-managed users; when readiness becomes healthy again, the user-role sending permission is restored. Periodic Celery reconciliation repeats these checks so DNS degradation does not depend on a manual portal action.

Emergency domain suspension is intentionally stronger: MailForge marks the domain fail-closed, disables sending and attempts to replace all active Stalwart mailbox permissions with an empty permission set. Organization suspension cascades the same protection across its domains. Periodic reconciliation re-applies this full suspension, and reactivation restores mailbox access with sending disabled before normal DNS readiness can restore `emailSend`.

Tenant invitation tokens are stored only as SHA-256 digests, expire automatically and are accepted only by the invited email identity. New portal account creation is not open signup; it is available only through a valid invitation.

HTML mail is sanitized before it reaches a template-safe boundary. Remote image elements are removed rather than fetched, and risky active/embedded content is stripped.

These controls still need live validation against the exact Stalwart version used on the production VPS before public onboarding. Per-mailbox/per-tenant rate limits, abuse/anomaly detection, backup/restore drills, queue/reputation monitoring and real-domain deliverability tests remain required before open signup.

## Domain onboarding

1. Add a domain to a MailForge organization.
2. Publish the displayed `_mailforge-verify` TXT challenge in DNS.
3. Verify ownership from the portal/API.
4. Provision the verified domain in Stalwart.
5. Configure the public mail hostname/IP in MailForge production settings.
6. Publish the MX, SPF, Stalwart-generated DKIM and DMARC records plus provider-managed PTR/rDNS.
7. Run **Check DNS readiness** from the domain screen.
8. Optionally publish MTA-STS and TLS-RPT; MailForge validates them as recommended transport-security checks.
9. Create mailboxes and forwarders. Mailboxes created before readiness remain unable to send.
10. Connect a mailbox to MailForge Webmail through Stalwart OAuth.
11. Sending becomes available only after the required DNS checks and Stalwart mailbox-policy synchronization succeed.

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

The next major production milestone is a real Ubuntu/Stalwart VPS integration with a real domain, followed by queue/reputation monitoring, per-mailbox/per-tenant abuse limits, real deliverability tests and the remaining webmail workflow features such as conversation view, draft autosave and message filing actions.

## Security warning

Self-hosted email is reputation-sensitive infrastructure. Do not open unrestricted public registration or bulk sending before rate limits, backend-enforced abuse controls, monitoring, backup/restore drills and real-domain deliverability checks are complete.
