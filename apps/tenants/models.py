from django.conf import settings
from django.db import models

class Tenant(models.Model):
    class Kind(models.TextChoices):
        PERSONAL = "personal", "Personal"
        CUSTOMER = "customer", "Customer"
        INTERNAL = "internal", "Internal"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CUSTOMER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    plan_code = models.CharField(max_length=50, default="personal")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class TenantMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        BILLING = "billing", "Billing"
        VIEWER = "viewer", "Viewer"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="uniq_tenant_user"),
        ]
