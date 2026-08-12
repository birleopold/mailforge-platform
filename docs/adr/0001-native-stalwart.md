# ADR 0001: Native Stalwart backend

## Status

Accepted.

## Context

MailForge needs a reliable mail/collaboration backend that can run directly on Ubuntu without Docker while supporting multiple custom domains, SMTP, IMAP, modern APIs, calendars, contacts, files and filtering.

The operator prefers not to depend on Docker.

## Decision

Use Stalwart Mail Server as the first backend and install it natively as a Linux/systemd service.

Django remains the customer-facing control plane and will build its own Gmail-style client over JMAP.

## Tenancy note

Stalwart Community Edition can host domains/accounts, but Stalwart's native Tenant object is an Enterprise feature. MailForge therefore implements customer/organization tenancy and authorization in Django for the free deployment. Customers do not receive Stalwart administrator access.

Higher-assurance tiers can later use a dedicated Stalwart instance or Stalwart Enterprise tenancy.

## Consequences

- no Docker is required;
- Mailcow is removed from the v1 architecture;
- backend automation uses Stalwart JMAP;
- Django can progressively expose email, calendars, contacts and files through one product UI;
- tenant-isolation tests in Django become a critical security requirement.
