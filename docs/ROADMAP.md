# Roadmap

## Phase 0 — Repository and lab
- [x] Define architecture.
- [x] Define tenant model.
- [x] Create Django starter scaffold.
- [ ] Build a non-production mailcow lab.
- [ ] Confirm VPS port 25 and PTR capability.
- [ ] Create test domain.

## Phase 1 — Core control plane
- [ ] Portal authentication.
- [ ] Tenant and membership CRUD.
- [ ] Domain ownership verification.
- [ ] Mailcow API adapter.
- [ ] Idempotent domain provisioning.
- [ ] Mailbox CRUD.
- [ ] Alias CRUD.
- [ ] Quotas.
- [ ] Audit events.
- [ ] Admin emergency suspend.

## Phase 2 — DNS and deliverability
- [ ] DNS status dashboard.
- [ ] MX/SPF/DKIM/DMARC checks.
- [ ] PTR check.
- [ ] MTA-STS/TLS-RPT guidance.
- [ ] Sending activation gate.
- [ ] Queue/reputation metrics.

## Phase 3 — Customer experience
- [ ] SOGo branding.
- [ ] Webmail launch links.
- [ ] Mail client setup instructions.
- [ ] Autoconfig/autodiscover.
- [ ] IMAP migration assistant.
- [ ] Password/app-password workflows.
- [ ] Storage usage dashboard.

## Phase 4 — Billing
- [ ] Plan/entitlement engine.
- [ ] Provider-neutral payment abstraction.
- [ ] Subscriptions.
- [ ] Invoice/payment history.
- [ ] Grace periods.
- [ ] Suspension/reactivation.
- [ ] Operator-owned free plan.

## Phase 5 — Security and abuse readiness
- [ ] MFA/passkeys for operator.
- [ ] Tenant admin MFA policy.
- [ ] Outbound rate limits.
- [ ] New-tenant probation.
- [ ] Abuse detection.
- [ ] Backup automation.
- [ ] Restore drill.
- [ ] Incident runbooks.
- [ ] External security review before open signup.

## Phase 6 — Reliability
- [ ] Cold standby.
- [ ] Off-site encrypted backups.
- [ ] External monitoring.
- [ ] Automated restore verification.
- [ ] Upgrade/rollback runbook.

## Phase 7 — Premium capabilities
- [ ] Custom tenant branding.
- [ ] Custom webmail hostname.
- [ ] Dedicated outbound routes/IP pools.
- [ ] Retention/archive options.
- [ ] SSO/OIDC.
- [ ] Additional mail backend adapter.
- [ ] API for resellers.
