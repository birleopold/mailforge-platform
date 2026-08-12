from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from apps.domains.models import Domain
from apps.mailboxes.models import Alias, Mailbox, normalize_local_part
from integrations.factory import get_mail_backend


class ForwarderProvisioningError(RuntimeError):
    pass


@dataclass(frozen=True)
class ForwarderProvisioningResult:
    alias: Alias


def normalize_destinations(destinations) -> list[str]:
    normalized = []
    seen = set()
    for raw in destinations:
        value = str(raw).strip().lower()
        try:
            validate_email(value)
        except ValidationError as exc:
            raise ForwarderProvisioningError(f"Invalid destination address: {value}") from exc
        if value not in seen:
            normalized.append(value)
            seen.add(value)

    if not normalized:
        raise ForwarderProvisioningError("At least one destination address is required.")
    if len(normalized) > settings.MAILFORGE_MAX_ALIAS_RECIPIENTS:
        raise ForwarderProvisioningError("This forwarder has too many destination addresses.")
    return normalized


def provision_forwarder(
    domain_id: int,
    *,
    local_part: str,
    destinations,
    backend=None,
    actor=None,
) -> ForwarderProvisioningResult:
    domain = Domain.objects.select_related("tenant").get(pk=domain_id)
    if not domain.backend_identifier:
        raise ForwarderProvisioningError("The domain must be provisioned before forwarders are created.")
    if domain.status not in {Domain.Status.DNS_CONFIGURATION, Domain.Status.ACTIVE}:
        raise ForwarderProvisioningError("The domain is not ready for forwarder provisioning.")

    local_part = normalize_local_part(local_part)
    destinations = normalize_destinations(destinations)
    address = f"{local_part}@{domain.name}"
    if address in destinations:
        raise ForwarderProvisioningError("A forwarder cannot forward to itself.")

    with transaction.atomic():
        locked_domain = Domain.objects.select_for_update().get(pk=domain_id)
        if Mailbox.objects.filter(
            domain=locked_domain,
            local_part=local_part,
        ).exclude(status=Mailbox.Status.DELETED).exists():
            raise ForwarderProvisioningError("That address is already used by a mailbox.")
        try:
            alias = Alias.objects.create(
                domain=locked_domain,
                local_part=local_part,
                destinations=destinations,
                active=False,
            )
        except IntegrityError as exc:
            raise ForwarderProvisioningError("That forwarder already exists.") from exc

    try:
        resolved_backend = backend or get_mail_backend()
        created = resolved_backend.create_alias(
            address=alias.email_address,
            destinations=destinations,
        )
        backend_identifier = str(created["id"])
    except Exception:
        alias.delete()
        raise

    alias.backend_identifier = backend_identifier
    alias.active = True
    alias.save(update_fields=["backend_identifier", "active"])
    AuditEvent.objects.create(
        tenant=domain.tenant,
        actor=actor,
        action="forwarder.provisioned",
        target_type="alias",
        target_id=str(alias.pk),
        metadata={
            "address": alias.email_address,
            "destinations": destinations,
            "backend_identifier": backend_identifier,
        },
    )
    return ForwarderProvisioningResult(alias=alias)
