# Architecture

## 1. Core rule: separate control plane from mail plane

MailForge is the control plane. It stores business ownership and orchestration state.

Mailcow is the mail plane. It stores and transports actual mail.

The Django application must never become a general SMTP relay and should never process raw inbound mail unless a narrow feature explicitly requires it.

## 2. Components

### Django API / portal
Responsibilities:

- authentication for portal users;
- tenant membership and roles;
- domain ownership;
- mailbox/alias requests;
- plan entitlements;
- billing state;
- DNS verification;
- provisioning state;
- usage snapshots;
- audit logs;
- support/admin workflows.

### PostgreSQL
Source of truth for MailForge business state.

Mailcow remains authoritative for mailbox runtime state. Synchronization jobs reconcile drift.

### Celery + Redis/Valkey
Used for:

- domain verification;
- provisioning;
- mailbox operations;
- periodic DNS checks;
- quota/usage synchronization;
- billing webhooks;
- backup status checks;
- reputation/health checks.

### Mailcow
Handles SMTP, IMAP, mailbox storage, filtering, SOGo, DKIM, and mail protocols.

## 3. Isolation model

The v1 system uses logical tenant isolation:

- every Domain belongs to exactly one Tenant;
- every Mailbox belongs to a Domain and therefore one Tenant;
- every request is authorized against TenantMembership;
- API serializers/querysets must always be tenant-scoped;
- background jobs receive immutable tenant/domain identifiers;
- provisioning actions are idempotent;
- mailcow domain administrators are assigned only the domains they should manage.

For very high-assurance customers, a later tier can provision a dedicated mailcow instance or dedicated mail cluster.

## 4. Mailcow adapter

Never scatter direct HTTP calls through Django views.

Use an adapter interface:

```python
class MailBackend:
    def create_domain(...): ...
    def delete_domain(...): ...
    def create_mailbox(...): ...
    def suspend_mailbox(...): ...
    def create_alias(...): ...
    def get_usage(...): ...
```

`integrations/mailcow/client.py` implements the adapter.

This makes a future Stalwart or other backend possible without rewriting billing and tenant logic.

## 5. State machines

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

Provisioning jobs must be retryable and idempotent.

## 6. Reliability path

### v1
One production mail VPS + one control-plane VPS is preferable to putting everything on one machine.

### v1.5
Encrypted off-site backups + cold standby.

### v2
Separate database/storage concerns, dedicated monitoring, and warm standby.

### v3
Multiple mail nodes, dedicated outbound routing/IP pools, and larger-scale storage if demand justifies it.

A second MX server alone does not make mailbox access highly available. It can queue inbound mail, but mailbox replication is a separate problem.
