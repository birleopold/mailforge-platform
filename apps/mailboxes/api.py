from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.domains.api import MANAGE_ROLES, tenant_membership_for_request
from apps.mailboxes.forwarders import ForwarderProvisioningError, provision_forwarder
from apps.mailboxes.models import Mailbox
from apps.mailboxes.serializers import (
    ForwarderCreateSerializer,
    ForwarderSerializer,
    MailboxCreateSerializer,
    MailboxPasswordResetSerializer,
    MailboxSerializer,
)
from apps.mailboxes.services import (
    MailboxLifecycleError,
    MailboxProvisioningError,
    delete_mailbox,
    provision_mailbox,
    reactivate_mailbox,
    reset_mailbox_password,
    suspend_mailbox,
)
from integrations.factory import MailBackendConfigurationError, UnsupportedMailBackend
from integrations.stalwart.client import StalwartAPIError


BACKEND_ERRORS = (MailBackendConfigurationError, UnsupportedMailBackend, StalwartAPIError)


def domain_and_membership(request, tenant_slug, domain_pk):
    tenant, membership = tenant_membership_for_request(request, tenant_slug)
    domain = get_object_or_404(tenant.domains, pk=domain_pk)
    return domain, membership


def _require_manager(membership, message):
    if membership.role not in MANAGE_ROLES:
        raise PermissionDenied(message)


def _mailbox_or_404(domain, pk):
    return get_object_or_404(
        domain.mailboxes.exclude(status=Mailbox.Status.DELETED),
        pk=pk,
    )


def _lifecycle_error_response(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)


def _backend_error_response():
    return Response(
        {"detail": "The mail backend is currently unavailable or not configured."},
        status=status.HTTP_502_BAD_GATEWAY,
    )


class TenantMailboxListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug, domain_pk):
        domain, _ = domain_and_membership(request, tenant_slug, domain_pk)
        mailboxes = domain.mailboxes.exclude(status=Mailbox.Status.DELETED).order_by("local_part")
        return Response(MailboxSerializer(mailboxes, many=True).data)

    def post(self, request, tenant_slug, domain_pk):
        domain, membership = domain_and_membership(request, tenant_slug, domain_pk)
        _require_manager(
            membership,
            "Only tenant owners and administrators can create mailboxes.",
        )

        serializer = MailboxCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = provision_mailbox(
                domain.pk,
                local_part=data["local_part"],
                password=data["password"],
                display_name=data.get("display_name", ""),
                quota_mb=data.get("quota_mb"),
                actor=request.user,
            )
        except MailboxProvisioningError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except BACKEND_ERRORS:
            return _backend_error_response()

        return Response(MailboxSerializer(result.mailbox).data, status=status.HTTP_201_CREATED)


class TenantMailboxDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug, domain_pk, pk):
        domain, _ = domain_and_membership(request, tenant_slug, domain_pk)
        mailbox = _mailbox_or_404(domain, pk)
        return Response(MailboxSerializer(mailbox).data)

    def delete(self, request, tenant_slug, domain_pk, pk):
        domain, membership = domain_and_membership(request, tenant_slug, domain_pk)
        _require_manager(
            membership,
            "Only tenant owners and administrators can delete mailboxes.",
        )
        mailbox = _mailbox_or_404(domain, pk)
        try:
            delete_mailbox(mailbox.pk, actor=request.user)
        except MailboxLifecycleError as exc:
            return _lifecycle_error_response(exc)
        except BACKEND_ERRORS:
            return _backend_error_response()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TenantMailboxSuspendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug, domain_pk, pk):
        domain, membership = domain_and_membership(request, tenant_slug, domain_pk)
        _require_manager(
            membership,
            "Only tenant owners and administrators can suspend mailboxes.",
        )
        mailbox = _mailbox_or_404(domain, pk)
        try:
            mailbox = suspend_mailbox(mailbox.pk, actor=request.user)
        except MailboxLifecycleError as exc:
            return _lifecycle_error_response(exc)
        except BACKEND_ERRORS:
            return _backend_error_response()
        return Response(MailboxSerializer(mailbox).data)


class TenantMailboxReactivateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug, domain_pk, pk):
        domain, membership = domain_and_membership(request, tenant_slug, domain_pk)
        _require_manager(
            membership,
            "Only tenant owners and administrators can reactivate mailboxes.",
        )
        mailbox = _mailbox_or_404(domain, pk)
        try:
            mailbox = reactivate_mailbox(mailbox.pk, actor=request.user)
        except MailboxLifecycleError as exc:
            return _lifecycle_error_response(exc)
        except BACKEND_ERRORS:
            return _backend_error_response()
        return Response(MailboxSerializer(mailbox).data)


class TenantMailboxPasswordResetView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug, domain_pk, pk):
        domain, membership = domain_and_membership(request, tenant_slug, domain_pk)
        _require_manager(
            membership,
            "Only tenant owners and administrators can reset mailbox passwords.",
        )
        mailbox = _mailbox_or_404(domain, pk)
        serializer = MailboxPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            mailbox = reset_mailbox_password(
                mailbox.pk,
                password=serializer.validated_data["password"],
                actor=request.user,
            )
        except MailboxLifecycleError as exc:
            return _lifecycle_error_response(exc)
        except BACKEND_ERRORS:
            return _backend_error_response()
        return Response(MailboxSerializer(mailbox).data)


class TenantForwarderListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug, domain_pk):
        domain, _ = domain_and_membership(request, tenant_slug, domain_pk)
        forwarders = domain.aliases.filter(active=True).order_by("local_part")
        return Response(ForwarderSerializer(forwarders, many=True).data)

    def post(self, request, tenant_slug, domain_pk):
        domain, membership = domain_and_membership(request, tenant_slug, domain_pk)
        if membership.role not in MANAGE_ROLES:
            raise PermissionDenied("Only tenant owners and administrators can create forwarders.")

        serializer = ForwarderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = provision_forwarder(
                domain.pk,
                local_part=data["local_part"],
                destinations=data["destinations"],
                actor=request.user,
            )
        except ForwarderProvisioningError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except BACKEND_ERRORS:
            return _backend_error_response()

        return Response(ForwarderSerializer(result.alias).data, status=status.HTTP_201_CREATED)


class TenantForwarderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug, domain_pk, pk):
        domain, _ = domain_and_membership(request, tenant_slug, domain_pk)
        forwarder = get_object_or_404(domain.aliases.filter(active=True), pk=pk)
        return Response(ForwarderSerializer(forwarder).data)
