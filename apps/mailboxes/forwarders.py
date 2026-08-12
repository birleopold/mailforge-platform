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


class ForwarderLifecycleError(RuntimeError):
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
            raise ForwarderProvisioningError("That forwarder already exists or is reserved.") from exc

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


def _active_forwarder(alias_id: int) -> Alias:
    alias = Alias.objects.select_related("domain__tenant").get(pk=alias_id)
    if not alias.active:
        raise ForwarderLifecycleError("This forwarder has already been deleted.")
    if not alias.backend_identifier:
        raise ForwarderLifecycleError("This forwarder is not provisioned in the mail backend.")
    return alias


def update_forwarder(
    alias_id: int,
    *,
    destinations,
    backend=None,
    actor=None,
) -> Alias:
    alias = _active_forwarder(alias_id)
    try:
        destinations = normalize_destinations(destinations)
    except ForwarderProvisioningError as exc:
        raise ForwarderLifecycleError(str(exc)) from exc
    if alias.email_address in destinations:
        raise ForwarderLifecycleError("A forwarder cannot forward to itself.")

    resolved_backend = backend or get_mail_backend()
    resolved_backend.update_alias(
        alias_id=alias.backend_identifier,
        destinations=destinations,
    )
    Alias.objects.filter(pk=alias.pk, active=True).update(destinations=destinations)
    alias.refresh_from_db()
    AuditEvent.objects.create(
        tenant=alias.domain.tenant,
        actor=actor,
        action="forwarder.updated",
        target_type="alias",
        target_id=str(alias.pk),
        metadata={
            "address": alias.email_address,
            "destinations": destinations,
            "backend_identifier": alias.backend_identifier,
        },
    )
    return alias


def delete_forwarder(alias_id: int, *, backend=None, actor=None) -> Alias:
    alias = _active_forwarder(alias_id)
    resolved_backend = backend or get_mail_backend()
    resolved_backend.delete_alias(alias_id=alias.backend_identifier)
    Alias.objects.filter(pk=alias.pk, active=True).update(active=False)
    alias.refresh_from_db()
    AuditEvent.objects.create(
        tenant=alias.domain.tenant,
        actor=actor,
        action="forwarder.deleted",
        target_type="alias",
        target_id=str(alias.pk),
        metadata={
            "address": alias.email_address,
            "destinations": alias.destinations,
            "backend_identifier": alias.backend_identifier,
        },
    )
    return alias
