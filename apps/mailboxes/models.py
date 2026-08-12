from django.db import models
from apps.domains.models import Domain

class Mailbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROVISIONING = "provisioning", "Provisioning"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DELETED = "deleted", "Deleted"

    domain = models.ForeignKey(Domain, on_delete=models.PROTECT, related_name="mailboxes")
    local_part = models.CharField(max_length=64)
    display_name = models.CharField(max_length=200, blank=True)
    quota_mb = models.PositiveIntegerField(default=5120)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    backend_identifier = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "local_part"],
                name="uniq_mailbox_localpart_per_domain",
            ),
        ]

    @property
    def email_address(self):
        return f"{self.local_part}@{self.domain.name}"

    def __str__(self):
        return self.email_address

class Alias(models.Model):
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="aliases")
    local_part = models.CharField(max_length=64)
    destinations = models.JSONField(default=list)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "local_part"],
                name="uniq_alias_localpart_per_domain",
            ),
        ]
