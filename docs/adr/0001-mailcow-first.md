# ADR 0001: Use mailcow as the first mail backend

## Status

Proposed / accepted for initial implementation.

## Context

MailForge needs a reliable mail engine with multi-domain hosting, mailbox management, quotas, spam filtering, webmail, calendar/contacts, and automation while keeping the core deployable without a mandatory per-mailbox commercial license.

## Decision

Use mailcow: dockerized as the first mail backend and keep all backend access behind a `MailBackend` abstraction.

## Reasons

- free/open-source mail stack;
- supports many domains and mailboxes;
- domain administrator and ACL model;
- REST API;
- SOGo collaboration interface;
- mature Postfix/Dovecot/Rspamd components;
- documented DNS and backup workflows.

## Stalwart

Stalwart remains technically attractive, especially for JMAP and modern architecture. However, native tenant objects/isolation are currently an Enterprise feature. Because the initial requirement prioritizes a free core, it will not be the v1 dependency.

## Consequences

MailForge must provide the higher-level Tenant abstraction itself and carefully map tenants to mailcow domains/domain administrators.

A future Stalwart adapter remains possible.
