import secrets
from django.db import models
from apps.tenants.models import Tenant

def verification_token():
    return secrets.token_urlsafe(32)

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
    backend = models.CharField(max_length=32, default="mailcow")
    backend_identifier = models.CharField(max_length=255, blank=True)
    sending_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def verification_record_name(self):
        return f"_mailforge-verify.{self.name}"
