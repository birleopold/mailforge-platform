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

Sign in with the superuser you created. You can then create an organization, add a domain and see the DNS ownership record MailForge expects.

Local development uses SQLite unless `DATABASE_URL` is configured.

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
```

Never commit the real `.env` file or API token.

For production, also configure PostgreSQL:

```text
DATABASE_URL=postgresql://mailforge:strong-password@127.0.0.1:5432/mailforge
```

## 4. Domain workflow

For each organization/domain:

1. Add the domain in MailForge.
2. Copy the displayed `_mailforge-verify` TXT record into the domain's DNS.
3. Click **Verify domain** after DNS propagates.
4. Click **Provision in Stalwart**.
5. Configure the real mail DNS records (MX, SPF, DKIM, DMARC and mail host records).
6. Create mailboxes using the authenticated API and forwarders through the portal/API.

Do not enable public paid signup until outbound abuse limits, backups, monitoring and deliverability checks are complete.

## 5. Important VPS checks

Before relying on the VPS for public email:

- the provider must allow outbound TCP port 25;
- the server must have a stable public IP;
- the provider must allow PTR/reverse-DNS configuration;
- the mail hostname must resolve correctly;
- TLS must be valid;
- storage and backups must be monitored.

A VPS that blocks outbound port 25 cannot directly deliver normal internet email to other mail servers.
