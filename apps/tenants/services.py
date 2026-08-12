from uuid import uuid4

from django.db import transaction
from django.utils.text import slugify

from apps.audit.models import AuditEvent
from apps.tenants.models import Tenant, TenantMembership


@transaction.atomic
def create_tenant(*, name: str, owner) -> Tenant:
    clean_name = name.strip()
    base = slugify(clean_name)[:45] or "tenant"
    slug = base
    while Tenant.objects.filter(slug=slug).exists():
        slug = f"{base}-{uuid4().hex[:6]}"

    tenant = Tenant.objects.create(
        name=clean_name,
        slug=slug,
        kind=Tenant.Kind.CUSTOMER,
        status=Tenant.Status.ACTIVE,
        plan_code="free",
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=owner,
        role=TenantMembership.Role.OWNER,
    )
    AuditEvent.objects.create(
        tenant=tenant,
        actor=owner,
        action="tenant.created",
        target_type="tenant",
        target_id=str(tenant.pk),
        metadata={"name": tenant.name, "slug": tenant.slug},
    )
    return tenant
