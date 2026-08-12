# Security

Mail hosting is a high-value target. Treat security as a product feature, not a final deployment step.

## Control plane

- MFA/passkeys for operator accounts.
- Least-privilege tenant roles.
- CSRF protection and secure session cookies.
- Strict tenant-scoped querysets.
- Rate limits on authentication, provisioning and password reset.
- Immutable audit logs for domain/mailbox/admin changes.
- Secrets only in environment/secret storage.
- Separate development/staging/production credentials.
- Regular dependency and container patching.

## Mailcow API

- Do not publish the API openly if avoidable.
- Restrict access by source IP/network.
- Use a dedicated API credential for MailForge.
- Do not expose super-admin credentials to Django users.
- Rotate API keys.
- Log every provisioning operation.
- Use timeout/retry/circuit-breaker behavior.

## Mail server

- No open relay.
- Authenticated submission only.
- TLS on submission and IMAP.
- Disable legacy protocols that are not needed.
- Conservative brute-force protection.
- Strong mailbox password policy.
- App passwords for mail clients when supported.
- Protect admin UI with MFA and preferably VPN/IP allowlisting.

## Domain takeover prevention

Before provisioning a customer domain:

1. generate a random ownership token;
2. require a DNS TXT record;
3. verify the exact value;
4. enforce global uniqueness of the domain;
5. store who verified it and when;
6. re-check ownership/routing periodically where appropriate.

## Abuse prevention

This is mandatory before public signup.

- per-mailbox and per-tenant sending limits;
- hourly burst limits;
- recipient-count limits;
- new-account probation;
- block obvious bulk-mail behavior by default;
- monitor bounce rates and queue growth;
- rapid suspend controls;
- manual review for anomalous tenants;
- acceptable-use policy;
- abuse contact and response procedure.

A shared IP means shared reputation.

## Backups

- encrypt off-site backups;
- use a separate credential/account from production;
- keep multiple generations;
- protect backup encryption keys;
- test restores on a schedule;
- document RPO and RTO targets.

A backup that has never been restored is not yet proven.
