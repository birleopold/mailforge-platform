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
- [x] Persist per-domain DNS readiness snapshots.
- [x] Browser/API DNS status checks.
- [x] MX/SPF/DMARC checks.
- [x] PTR/rDNS check when production server IPv4 is configured.
- [x] Application-level sending activation gate.
- [ ] Read and surface Stalwart-generated DKIM recommendations/keys.
- [ ] DKIM validation.
- [ ] MTA-STS/TLS-RPT guidance and validation.
- [ ] Synchronize MailForge readiness/suspension state with Stalwart SMTP submission permissions.
- [ ] Queue/reputation monitoring.
- [ ] Real-domain deliverability tests to Gmail/Outlook/Yahoo.

## Phase 3 — MailForge Webmail
- [x] Mailbox-user OAuth design without storing mailbox passwords in Django.
- [x] Authorization Code + PKCE integration with encrypted session token storage.
- [x] JMAP session discovery and authenticated mailbox access.
- [x] Mailbox/folder sidebar and unread counts.
- [x] Inbox/message list.
- [x] Safe plain-text message reader.
- [x] Server-side mail search.
- [x] Mark read on open and mark-unread action.
- [x] Compose with validated To/Cc/Bcc and Stalwart sending identities.
- [x] Draft creation and `EmailSubmission/set` delivery.
- [x] Move successfully submitted messages from Drafts to Sent.
- [x] Block webmail compose when the identity domain is not sending-ready.
- [ ] Conversation/thread view.
- [ ] Reply/reply-all/forward.
- [ ] Attachment upload/download.
- [ ] Safe HTML mail sanitization/rendering.
- [ ] Draft autosave/edit existing drafts.
- [ ] Move/archive/delete/spam actions.
- [ ] Pagination/infinite scroll.
- [ ] Real-time JMAP updates.
- [ ] OAuth logout/revocation and stronger token lifecycle policy.

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
- [ ] Backend-enforced suspension and sending restrictions.
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
