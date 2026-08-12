# Roadmap

## Phase 0 — Foundation
- [x] Define architecture.
- [x] Define MailForge tenant model.
- [x] Create Django starter scaffold.
- [x] Remove Docker dependency from the design.
- [x] Select native Stalwart backend.
- [ ] Build a non-production Stalwart lab on Ubuntu.
- [ ] Confirm VPS outbound port 25 and PTR/rDNS support.
- [ ] Connect a test domain.

## Phase 1 — Core control plane
- [ ] Portal authentication and tenant-scoped API.
- [ ] Tenant and membership CRUD.
- [x] Domain ownership TXT verification core.
- [x] Retry-safe verification task.
- [x] Audit event for verified ownership.
- [x] Stalwart JMAP adapter foundation.
- [ ] Idempotent domain provisioning.
- [ ] Mailbox CRUD and lifecycle.
- [ ] Alias CRUD.
- [ ] Quota enforcement.
- [ ] Emergency suspend controls.

## Phase 2 — DNS and deliverability
- [ ] DNS status dashboard.
- [ ] MX/SPF/DKIM/DMARC checks.
- [ ] PTR/rDNS check.
- [ ] MTA-STS/TLS-RPT guidance.
- [ ] Sending activation gate.
- [ ] Queue/reputation monitoring.

## Phase 3 — MailForge Webmail
- [ ] JMAP session/authentication integration.
- [ ] Inbox/message list.
- [ ] Conversation/thread view.
- [ ] Compose/reply/forward.
- [ ] Attachments.
- [ ] Search.
- [ ] Folders/labels and spam/trash.
- [ ] Draft autosave.
- [ ] Real-time JMAP updates.

## Phase 4 — Collaboration
- [ ] Contacts UI over JMAP for Contacts.
- [ ] Calendar UI over JMAP for Calendars.
- [ ] File storage UI over JMAP/WebDAV.
- [ ] Sharing and permissions.

## Phase 5 — Billing
- [ ] Plan/entitlement engine.
- [ ] Provider-neutral payment abstraction.
- [ ] Subscriptions and payment history.
- [ ] Grace periods and reactivation.
- [ ] Operator-owned free plan.

## Phase 6 — Security and abuse readiness
- [ ] MFA/passkeys for operator accounts.
- [ ] Tenant admin MFA policy.
- [ ] Per-mailbox and per-tenant send limits.
- [ ] New-tenant probation.
- [ ] Abuse/anomaly detection.
- [ ] Backup automation and restore drill.
- [ ] Incident runbooks.
- [ ] External security review before open signup.

## Phase 7 — Reliability and scale
- [ ] Separate mail and control-plane VPSs.
- [ ] Encrypted off-site backups.
- [ ] External monitoring.
- [ ] Automated restore verification.
- [ ] Warm/cold standby strategy.
- [ ] Dedicated outbound routes/IP pools for trusted customers.
- [ ] Dedicated Stalwart instances for high-isolation plans.
