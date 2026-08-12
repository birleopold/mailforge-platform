# Native Ubuntu Operations

MailForge is designed to run without Docker.

## Recommended services

On Ubuntu, manage components with systemd:

- `stalwart.service` — mail/collaboration server;
- PostgreSQL — MailForge application database;
- Redis — Celery broker/cache;
- `mailforge-web.service` — Gunicorn serving Django;
- `mailforge-worker.service` — Celery worker;
- Nginx — optional public reverse proxy for Django.

## Stalwart installation

Use the official native Linux installer and run Stalwart under its generated service account/systemd unit. Do not install a parallel SMTP server such as Postfix on the same ports.

Before public mail is enabled, confirm the VPS provider allows outbound TCP port 25 and can configure PTR/rDNS for the server IP.

## Monitoring

Alert on:

- Stalwart SMTP/JMAP/IMAP availability;
- Django health endpoint;
- disk usage and inode pressure;
- mail queue size and age;
- TLS certificate expiry;
- DNS drift;
- Redis/PostgreSQL health;
- Celery failures;
- backup age/failure;
- unusual outbound volume and authentication failures.

## Backups

Back up both systems independently:

1. MailForge PostgreSQL data;
2. Stalwart configuration/data store;
3. required encryption/secrets material.

Keep encrypted copies off the production VPS and test restores regularly.

## Upgrade policy

- pin/test releases before production rollout;
- take backups before mail-server upgrades;
- stage changes when possible;
- retain rollback instructions;
- never treat automatic package updates as a complete mail-stack upgrade strategy.

## Production topology

A first private deployment can run on one adequately sized VPS. Before selling the service broadly, separate MailForge and Stalwart onto different hosts so a portal problem does not compete with the mail plane for CPU/RAM/disk.
