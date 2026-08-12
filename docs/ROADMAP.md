# Roadmap

## Phase 0 — Foundation
- [x] Define architecture.
- [x] Define MailForge tenant model.
- [x] Create Django starter scaffold.
- [x] Remove Docker dependency from the design.
- [x] Select native Stalwart backend.
- [x] Add native Windows/Ubuntu quick-start and service examples.
- [ ] Build a non-production Stalwart lab on an actual Ubuntu VPS.
- [ ] Confirm VPS outbound port 25 and PTR/rDNS support.
- [ ] Connect a real test domain end-to-end.

## Phase 1 — Core control plane
- [x] Portal authentication and tenant-scoped API foundation.
- [x] Tenant create/list/detail with owner membership and audit.
- [x] Domain create/list/detail with tenant isolation.
- [x] Domain ownership TXT verification core.
- [x] Retry-safe verification task.
- [x] Audit events for domain/tenant provisioning actions.
- [x] Stalwart management JMAP adapter foundation.
- [x] Idempotent domain provisioning service and API/portal action.
- [x] Mailbox list/create foundation with quotas and tenant isolation.
- [x] Forwarder list/create foundation using Stalwart mailing lists.
- [x] Browser management portal for organizations/domains/forwarders.
- [ ] Mailbox suspend/delete/password-reset lifecycle.
- [ ] Forwarder update/delete lifecycle.
- [ ] Tenant membership invitation/role-management UI.
- [ ] Plan-specific quota/entitlement engine.
- [ ] Emergency suspend controls.

## Phase 2 — DNS and deliverability
- [ ] Read Stalwart DNS recommendations for each provisioned domain.
- [ ] DNS status dashboard.
- [ ] MX/SPF/DKIM/DMARC checks.
- [ ] PTR/rDNS check.
- [ ] MTA-STS/TLS-RPT guidance.
- [ ] Sending activation gate.
- [ ] Queue/reputation monitoring.

## Phase 3 — MailForge Webmail
- [ ] Design mailbox-user authentication/SSO without storing mailbox passwords in Django.
- [ ] JMAP session discovery and authenticated mailbox access.
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
