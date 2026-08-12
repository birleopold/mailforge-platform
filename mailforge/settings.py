import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.tenants",
    "apps.domains",
    "apps.mailboxes",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "mailforge.urls"
WSGI_APPLICATION = "mailforge.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

database_url = os.environ.get("DATABASE_URL") or "sqlite:///db.sqlite3"
DATABASES = {
    "default": dj_database_url.parse(
        database_url,
        conn_max_age=60,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MAILFORGE_DEFAULT_MAX_MAILBOXES = int(os.environ.get("MAILFORGE_DEFAULT_MAX_MAILBOXES", "25"))
MAILFORGE_DEFAULT_DOMAIN_QUOTA_MB = int(
    os.environ.get("MAILFORGE_DEFAULT_DOMAIN_QUOTA_MB", "102400")
)
MAILFORGE_DEFAULT_MAILBOX_QUOTA_MB = int(
    os.environ.get("MAILFORGE_DEFAULT_MAILBOX_QUOTA_MB", "5120")
)
MAILFORGE_MAX_MAILBOX_QUOTA_MB = int(
    os.environ.get("MAILFORGE_MAX_MAILBOX_QUOTA_MB", "51200")
)
MAILFORGE_MAX_ALIAS_RECIPIENTS = int(
    os.environ.get("MAILFORGE_MAX_ALIAS_RECIPIENTS", "20")
)
MAILFORGE_MAIL_HOSTNAME = os.environ.get("MAILFORGE_MAIL_HOSTNAME", "")
MAILFORGE_MAIL_IPV4 = os.environ.get("MAILFORGE_MAIL_IPV4", "")
MAILFORGE_OAUTH_CLIENT_ID = os.environ.get("MAILFORGE_OAUTH_CLIENT_ID", "mailforge-webmail")
MAILFORGE_OAUTH_CLIENT_SECRET = os.environ.get("MAILFORGE_OAUTH_CLIENT_SECRET", "")
MAILFORGE_OAUTH_SCOPE = os.environ.get("MAILFORGE_OAUTH_SCOPE", "")
MAILFORGE_MAX_ATTACHMENT_MB = int(os.environ.get("MAILFORGE_MAX_ATTACHMENT_MB", "20"))
MAILFORGE_MAX_TOTAL_ATTACHMENT_MB = int(
    os.environ.get("MAILFORGE_MAX_TOTAL_ATTACHMENT_MB", "25")
)
MAILFORGE_DNS_RECONCILE_MINUTES = max(
    1,
    int(os.environ.get("MAILFORGE_DNS_RECONCILE_MINUTES", "15")),
)

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_BEAT_SCHEDULE = {
    "mailforge-domain-readiness-reconciliation": {
        "task": "apps.domains.tasks.reconcile_all_domain_readiness",
        "schedule": MAILFORGE_DNS_RECONCILE_MINUTES * 60.0,
    }
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
