# Operations

## Suggested production topology

Prefer:

- VPS A: Django control plane, PostgreSQL, Celery/Redis (or split DB later)
- VPS B: mailcow mail plane
- Backup destination: separate provider/account/location
- Optional VPS C: cold standby / recovery target

Do not assume "one big VPS" is high availability.

## Monitoring

Alert on:

- SMTP service availability;
- IMAP service availability;
- webmail availability;
- mail queue size/age;
- disk usage and inode usage;
- RAM/CPU pressure;
- TLS certificate expiry;
- DNS drift;
- backup failure;
- backup age;
- restore-test failure;
- spam/filter service failure;
- unusual outbound volume;
- authentication attack spikes.

## Deployment

- pin tested versions;
- stage upgrades;
- back up before mail stack upgrades;
- use maintenance windows;
- document rollback;
- do not auto-upgrade critical mail components without a tested path.

## Recovery targets

Define before launch:

- RPO: how much mail/data loss is acceptable?
- RTO: how long can service be unavailable?
- recovery owner;
- exact restore procedure;
- backup locations and keys.

## Logging

Keep security and provisioning logs separate from message content.

Avoid storing email bodies in Django logs.
