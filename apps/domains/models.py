import re
import secrets

from django.core.exceptions import ValidationError
from django.db import models

from apps.tenants.models import Tenant


_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def verification_token():
    return secrets.token_urlsafe(32)


def normalize_domain_name(value: str) -> str:
    value = value.strip().rstrip(".").lower()
    if not value or value.startswith("*."):
        raise ValidationError("Enter a valid domain name.")

    try:
        ascii_name = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationError("Enter a valid domain name.") from exc

    if len(ascii_name) > 253:
        raise ValidationError("Domain name is too long.")

    labels = ascii_name.split(".")
    if len(labels) < 2 or any(not _DOMAIN_LABEL_RE.fullmatch(label) for label in labels):
        raise ValidationError("Enter a fully-qualified domain name.")

    return ascii_name


class Domain(models.Model):
    class Status(models.TextChoices):
        PENDING_VERIFICATION = "pending_verification", "Pending verification"
        VERIFIED = "verified", "Verified"
        PROVISIONING = "provisioning", "Provisioning"
        DNS_CONFIGURATION = "dns_configuration", "DNS configuration"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DECOMMISSIONED = "decommissioned", "Decommissioned"

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="domains")
    name = models.CharField(max_length=253, unique=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_VERIFICATION,
    )
    ownership_token = models.CharField(max_length=128, default=verification_token, editable=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    backend = models.CharField(max_length=32, default="stalwart")
    backend_identifier = models.CharField(max_length=255, blank=True)
    sending_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        self.name = normalize_domain_name(self.name)

    def save(self, *args, **kwargs):
        self.name = normalize_domain_name(self.name)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def verification_record_name(self):
        return f"_mailforge-verify.{self.name}"

    @property
    def verification_record_value(self):
        return f"mailforge-verification={self.ownership_token}"
