# Architecture

## 1. Control plane and mail plane

MailForge is the control plane. Django owns customers, tenant membership, domain ownership, billing, plans, quotas, provisioning state, abuse policy and the future Gmail-style interface.

Stalwart is the mail plane. It runs natively on Ubuntu under systemd and handles SMTP, IMAP, JMAP, mail storage, calendars, contacts, files, filtering and DKIM.

Django must never become an SMTP relay. It talks to Stalwart over HTTPS/JMAP.

## 2. Components

### Django

- authentication and tenant membership;
- domain and mailbox management;
- DNS verification;
- plan entitlements and billing;
- audit logs and support workflows;
- future webmail/calendar/contact/file UI using JMAP.

### PostgreSQL

Source of truth for MailForge business and tenancy state.

### Celery + Redis

Used for DNS verification, provisioning, usage reconciliation, billing events, health checks and scheduled jobs.

### Stalwart

Installed as a native Linux service. Stalwart is authoritative for mailbox runtime data and mail/collaboration objects.

## 3. Community-edition tenancy model

Stalwart's native Tenant object is an Enterprise feature. The free/community deployment therefore uses MailForge logical tenancy:

- each Domain belongs to exactly one MailForge Tenant;
- each Mailbox belongs to a Domain;
- all portal queries and actions are tenant-scoped;
- customers never receive Stalwart admin credentials;
- only the MailForge service credential can perform management calls;
- background jobs carry explicit MailForge tenant/domain identifiers;
- audit events record privileged changes.

For high-assurance customers, later tiers can use a dedicated Stalwart instance/host or Stalwart Enterprise tenancy.

## 4. Backend adapter

Backend calls stay behind `MailBackend`.

`integrations/stalwart/client.py` implements the first backend using Stalwart's management JMAP API.

This keeps billing and tenant logic independent from the mail server implementation.

## 5. Product UI direction

MailForge will not depend permanently on Stalwart's admin UI. The customer experience is built in Django and progressively consumes JMAP for:

- inbox/message lists;
- compose/send;
- search and folders;
- contacts;
- calendars;
- file storage and sharing.

## 6. State machines

Domain:

```text
PENDING_VERIFICATION
 -> VERIFIED
 -> PROVISIONING
 -> DNS_CONFIGURATION
 -> ACTIVE
 -> SUSPENDED
 -> DECOMMISSIONED
```

Mailbox:

```text
PENDING -> PROVISIONING -> ACTIVE -> SUSPENDED -> DELETED
```

Provisioning jobs must be idempotent and retry-safe.

## 7. Production topology

Start with separate concerns even if they share one VPS initially:

```text
systemd
 |- stalwart.service
 |- mailforge-web.service (Gunicorn)
 |- mailforge-worker.service (Celery)
 |- postgresql.service
 |- redis-server.service
```

A safer public deployment later separates the mail plane and Django control plane onto different VPSs and keeps encrypted off-site backups.
