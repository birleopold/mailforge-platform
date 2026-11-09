# mailforge-platform: implementation, validation and commercial master plan

**Edition:** 2026-11-09 · **Portfolio decision:** P9 · internal first, external only after reliability proof · **Status:** plan only. Preserve more specific existing engineering roadmaps and verify against the current branch before work.

## Executive product decision
**Target buyer:** Leosoft's own mail domains then SMEs needing managed email hosting.
**Comparative research targets:** Stalwart; Google Workspace; Microsoft 365; Zoho Mail. Collect screenshots of legally accessible workflows, published pricing at dated intervals, interviews and switching-cost notes. External competitor claims require current verification; do not copy code or branding.
**Pricing/viability hypothesis:** Mailbox/domain subscription only if 24/7 support, backups and realistic deliverability costs supported.
**Initial win:** one complete paying-customer journey, not feature count; make adoption, cancellation and support predictable.

## Engineering workstreams
### Gate P0: safety, correctness and operational risks
P0 use own domains first; confirm Stalwart Community vs Enterprise feature/legal boundaries; ensure Django tenant isolation is not misrepresented as Stalwart enterprise-level tenant isolation; secure JMAP OAuth tokens, management credential scopes, secrets and MX records.

### Gate P1: narrow sellable workflow, backend to frontend
P1 test provision→DNS ownership→DKIM/SPF/DMARC→inbox/send→forward→suspend/recover→export/delete; measure reputation, bounce/retry, outbound throttling, queues, spam abuse, cross-tenant isolation and restore; dedicated backup encryption.

### Gate P2: repeatability, integrations, sales and scale
P2 build paid plan and abuse controls, quota warnings, support escalation, uptime monitoring, domain migration, retention and disaster recovery; separate inbound mailbox hosting from mass-marketing email service; no unsolicited bulk sending.

## Implementation contract and acceptance
- Define authoritative records, lifecycle transition diagram, role matrix, input/error rules, race conditions, audit events, security boundaries and diagrams of external providers.
- Use transactional state changes and database constraints for irreversible actions, explicit reversal workflow and retry-safe provider integration; no silent data loss or duplicate payouts/orders.
- Build branded accessible operator flows for laptop, POS-size and phone as applicable; no dead links, inconsistent navigation or old UI escaping design system.
- Test negative cases, disconnections, payment delays, unauthorized access, partial transactions, staging migration and recovery before any customer launch.
- **Specific pilot exit:** Six weeks own-domain operational evidence, DNS/forwarding tests, independent deliverability tests to Gmail/Microsoft, restore and 24/7 incident owner before external sale.

## Commercial execution
1. Interview ten qualified buyers/partners, document current alternative, exact recurring pain, budget authority and willingness to pay; record why prospects reject the proposed product.
2. Sell one clearly scoped offer with a 10–15-minute demonstration, clear terms, support coverage, data export, cancellation and written exclusions.
3. Price using a customer-level margin model: net collected subscriptions or service fees minus infrastructure, provider fees, support, sales commissions, operational liability and taxes. Separate onboarding/hardware from recurring software.
4. Pilot only with signed limitations and measured acceptance; turn successful pilots into referenceable case studies with explicit consent. Use referrals and domain partnerships before untargeted ad spend.
5. Keep client-specific modifications configurable and isolated. Add multi-tenant commercialization only after authorization and data-separation tests.

## Research and external requirements
- https://stalw.art/docs/server/enterprise/
- https://support.google.com/mail/answer/81126

## Execute in controlled, full-stack vertical slices
1. Establish baseline: repo head, existing docs/issues, CI, migrations, dependency and secret scan, deployed version, open failures, affected business workflows. Mark each proposed item Done / Partial / Not started / Blocked with evidence; do not duplicate completed work.
2. Technical design: data and state invariants, API schema, role/tenant matrix, threat model, UI/navigation specification, provider failure states, feature flags and rollback plan before coding.
3. Deliver for every slice: persistence/domain service → API/forms → user/operator/admin UI including errors → audit and observability → API/browser/integration/concurrency tests → install/update/migration → customer docs. Do not approve half-built implementations.
4. Finances: authoritative ledger, deduplicated events and reconciliation; distinguish provider response from confirmed fulfillment. Sensitive actions require privileges, MFA, reason codes and logs where relevant.
5. Release: automated checks, isolated staging, production-shaped PostgreSQL tests, backup and restored backup evidence, peer review, compatibility and accessibility, pin commit and smoke test, monitored rollout and rollback.
6. Support: ownership, SLA, on-call where relevant, diagnostics without credentials, customer data export, deletion/retention, billing/renewal/refund policy, supported OS/browser/device matrix.

## Prioritized 90-day execution
- **Days 1–14:** current-state audit, research and 10 user interviews; record actual market alternatives, customer pricing and top three failure modes. Stop if there is no distinct buyer/problem.
- **Days 15–35:** close P0 blockers; first full-stack MVP slice, reproducible CI and rollback/restore rehearsal.
- **Days 36–60:** end-to-end acceptance test with realistic data; documentation and operator/admin UI, payment and failure-case testing where applicable.
- **Days 61–90:** supervised pilot where authorized; fixed onboarding package, pricing experiment and weekly KPI review. No broad launch while P0 release gates fail.

## Outcome-driven evidence and business administration
Each milestone needs owner, issue ID, pull request, commit, baseline and test transcripts, tested roles/devices, UI screenshots, deployment SHA, rollback, customer acceptance and outstanding risks. Track qualified leads, demos, pilot activation, paid conversion, gross margin after support/hosting/payment fees, churn, severity incidents and restore success. Review **ship / repair / pause** monthly. Avoid custom forks and share services only via explicit APIs.

## Security and law baseline
- NIST SSDF: https://csrc.nist.gov/projects/ssdf
- OWASP ASVS 5.0: https://asvs.owasp.org/
- Uganda personal-data registration: https://doingbusiness.finance.go.ug/licensing/pdpo-data-protection-registration
This is planning guidance; it confers no regulatory approval or completion certificate.
