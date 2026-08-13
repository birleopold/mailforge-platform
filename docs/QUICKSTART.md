# MailForge Quick Start

MailForge does not require Docker.

## 1. Run the Django control plane on Windows

From the repository folder in Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

Sign in with the superuser you created. You can then create an organization, add a domain, invite organization members and see the DNS ownership record MailForge expects.

Local development uses SQLite unless `DATABASE_URL` is configured. The default development email backend writes invitation emails to the console.

## 2. Install Stalwart natively on Ubuntu

On the Ubuntu VPS, clone MailForge and use the included native helper:

```bash
sudo bash scripts/install_stalwart_ubuntu.sh
```

The helper uses Stalwart's official native Linux installer and systemd service. It does not install Docker.

Retrieve the one-time Stalwart bootstrap administrator details from the service logs, then complete the Stalwart setup before connecting MailForge.

## 3. Configure MailForge for Stalwart

In `.env`, replace the placeholders:

```text
MAIL_BACKEND=stalwart
STALWART_BASE_URL=https://mail.example.com
STALWART_API_TOKEN=replace-with-a-restricted-service-token
STALWART_VERIFY_TLS=1
MAILFORGE_MAIL_HOSTNAME=mail.example.com
MAILFORGE_MAIL_IPV4=203.0.113.10
MAILFORGE_DNS_RECONCILE_MINUTES=15
MAILFORGE_INVITATION_HOURS=72
```

The Stalwart service credential must have the management permissions needed for MailForge's domain/account operations, including reading domain DNS zone metadata and updating MailForge-managed account permissions. Never commit the real `.env` file or API token.

For production, also configure PostgreSQL:

```text
DATABASE_URL=postgresql://mailforge:strong-password@127.0.0.1:5432/mailforge
```

For organization invitation emails, configure a real SMTP sender in production:

```text
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=mailforge@example.com
EMAIL_HOST_PASSWORD=replace-with-a-secret
EMAIL_USE_TLS=1
DEFAULT_FROM_EMAIL=mailforge@example.com
```

Invitation links are one-time, expire after `MAILFORGE_INVITATION_HOURS`, and MailForge stores only a SHA-256 digest of the invitation token.

After every deployment that includes model or dependency changes, run:

```bash
/opt/mailforge-platform/.venv/bin/pip install -e ".[dev]"
/opt/mailforge-platform/.venv/bin/python /opt/mailforge-platform/manage.py migrate
```

The dependency refresh is required for deployments that include new runtime packages such as the HTML sanitizer.

## 4. Domain workflow

For each organization/domain:

1. Add the domain in MailForge.
2. Copy the displayed `_mailforge-verify` TXT record into the domain's DNS.
3. Click **Verify domain** after DNS propagates.
4. Click **Provision in Stalwart**.
5. Publish the required MX, SPF, Stalwart-generated DKIM and DMARC records, plus the mail-host A/AAAA records as appropriate.
6. Configure PTR/reverse DNS for the VPS public IP at the hosting provider.
7. Click **Check DNS readiness**. MailForge compares public DKIM against Stalwart's current generated DNS zone and synchronizes the Stalwart `emailSend` permission for MailForge-managed mailboxes.
8. Optionally publish MTA-STS and TLS-RPT. MailForge validates the MTA-STS TXT record, HTTPS policy and MX coverage, plus the TLS-RPT reporting record. These checks are recommended and do not currently gate sending.
9. Create mailboxes and forwarders. A mailbox created before readiness can receive/login but is created without outbound sending permission.
10. Configure and run Celery worker + Celery beat so readiness is rechecked automatically.
11. Connect mailbox users to MailForge Webmail through Stalwart OAuth.

MailForge Webmail sanitizes HTML email before rendering. Scripts, embedded content, inline styling, unsafe links and remote images are blocked; a plain-text version remains available when supplied by the message.

Do not enable public paid signup until outbound abuse limits, backups, monitoring and real deliverability checks are complete.

## 5. Emergency suspension

Organization owners can emergency-suspend an entire organization. Owners and administrators can emergency-suspend an individual domain.

Emergency suspension is fail-closed in MailForge: sending is disabled immediately, and MailForge attempts to replace all active Stalwart mailbox permissions with an empty permission set. Periodic readiness reconciliation re-applies the stronger emergency suspension instead of downgrading it to the normal send-only restriction.

Reactivation restores mailbox access with outbound sending still disabled first. Normal DNS readiness must pass before `emailSend` is restored. Tenant reactivation rolls restored domains back to suspended if another domain cannot be restored safely.

## 6. Run the native MailForge services on Ubuntu

Examples are provided under `deploy/systemd/` for:

```text
mailforge-web.service.example
mailforge-worker.service.example
mailforge-beat.service.example
```

Copy/adapt them into `/etc/systemd/system/`, then enable the web app, worker and scheduler:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mailforge-web
sudo systemctl enable --now mailforge-worker
sudo systemctl enable --now mailforge-beat
```

The worker executes background checks. Celery beat schedules domain readiness reconciliation every `MAILFORGE_DNS_RECONCILE_MINUTES` and fans work out to the worker.

## 7. Important VPS checks

Before relying on the VPS for public email:

- the provider must allow outbound TCP port 25;
- the server must have a stable public IP;
- the provider must allow PTR/reverse-DNS configuration;
- the mail hostname must resolve correctly;
- TLS must be valid;
- Stalwart's generated DKIM record must be published exactly;
- the Celery worker and beat services must be running;
- invitation-email SMTP settings must work if tenant invitations are used;
- storage and backups must be monitored.

A VPS that blocks outbound port 25 cannot directly deliver normal internet email to other mail servers.
