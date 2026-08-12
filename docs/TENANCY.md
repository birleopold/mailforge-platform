# Tenant model

## Entities

### Tenant
Represents one customer, organization, or the operator's own personal account.

Recommended fields:

- `id`
- `name`
- `slug`
- `kind` (`personal`, `customer`, `internal`)
- `status`
- `plan_code`
- `created_at`

### TenantMembership
Links portal users to tenants.

Roles:

- owner
- admin
- billing
- support/read-only

### Domain
Globally unique domain belonging to exactly one tenant.

Important fields:

- `tenant`
- `name`
- `status`
- `ownership_token`
- `verified_at`
- `mail_backend`
- `backend_identifier`
- `sending_enabled`
- `created_at`

### Mailbox
Belongs to one domain.

Fields:

- `domain`
- `local_part`
- `display_name`
- `quota_mb`
- `status`
- `backend_identifier`

Use a uniqueness constraint on `(domain, local_part)`.

### Alias
Maps one address to one or more destinations, always enforcing tenant/domain authorization rules.

### Plan
Defines limits:

- maximum domains;
- maximum mailboxes;
- storage per mailbox;
- aggregate tenant storage;
- aliases;
- daily send allowance;
- custom branding;
- dedicated route eligibility;
- retention features.

### UsageSnapshot
Periodic copy of backend usage for dashboards and billing/alerts.

### AuditEvent
Append-only record of sensitive actions.

## Personal domains

Operator-owned tenants can be assigned a plan with `price = 0` while still retaining explicit quotas and policies. Avoid implementing "unlimited" internally; use large explicit limits.
