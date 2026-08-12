# Security

Mail hosting is a high-value target. Security is part of the product, not a final deployment step.

## Control plane

- require MFA/passkeys for operator accounts;
- use least-privilege tenant roles;
- enforce tenant-scoped querysets and object checks;
- rate-limit authentication, password reset and provisioning endpoints;
- keep append-only audit events for privileged changes;
- store secrets outside Git;
- separate development, staging and production credentials.

## Stalwart management access

Customers must never receive the Stalwart administrator/service credential.

MailForge uses a dedicated API credential over HTTPS/JMAP. Restrict that credential to only the permissions MailForge requires and, where possible, restrict its source IP/network. Rotate it periodically and log all privileged provisioning operations.

Stalwart Community Edition's native Tenant object is not available, so Django is the customer-facing authorization boundary in the free deployment. High-isolation customers should later receive a dedicated Stalwart instance/host or an Enterprise-backed deployment.

## Domain takeover prevention

Before provisioning a customer domain:

1. generate a random ownership token;
2. require a DNS TXT record;
3. compare the exact token value;
4. enforce global uniqueness of the domain in MailForge;
5. record verification time and audit event;
6. periodically detect DNS/routing drift.

## Abuse prevention

Before public paid signup:

- per-mailbox and per-tenant sending limits;
- burst and recipient-count limits;
- new-account probation;
- anomaly and queue monitoring;
- rapid tenant/mailbox suspension;
- acceptable-use policy and abuse contact;
- review of hard bounces and reputation blocks.

A shared outbound IP creates shared reputation risk.

## Mailbox security

- TLS for HTTP/JMAP, IMAP and SMTP submission;
- strong password policy;
- app passwords for legacy clients where appropriate;
- 2FA for portal and privileged accounts;
- no open relay;
- disable unnecessary legacy protocols.

## Backups

Encrypt off-site backups, keep several generations, protect backup keys separately and perform scheduled restore tests. Back up both MailForge application data and Stalwart's data/configuration stores.
