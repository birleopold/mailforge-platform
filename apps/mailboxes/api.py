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
    MailboxSerializer,
)
from apps.mailboxes.services import MailboxProvisioningError, provision_mailbox
from integrations.factory import MailBackendConfigurationError, UnsupportedMailBackend
from integrations.stalwart.client import StalwartAPIError


BACKEND_ERRORS = (MailBackendConfigurationError, UnsupportedMailBackend, StalwartAPIError)


def domain_and_membership(request, tenant_slug, domain_pk):
    tenant, membership = tenant_membership_for_request(request, tenant_slug)
    domain = get_object_or_404(tenant.domains, pk=domain_pk)
    return domain, membership


class TenantMailboxListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug, domain_pk):
        domain, _ = domain_and_membership(request, tenant_slug, domain_pk)
        mailboxes = domain.mailboxes.exclude(status=Mailbox.Status.DELETED).order_by("local_part")
        return Response(MailboxSerializer(mailboxes, many=True).data)

    def post(self, request, tenant_slug, domain_pk):
        domain, membership = domain_and_membership(request, tenant_slug, domain_pk)
        if membership.role not in MANAGE_ROLES:
            raise PermissionDenied("Only tenant owners and administrators can create mailboxes.")

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
            return Response(
                {"detail": "The mail backend is currently unavailable or not configured."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(MailboxSerializer(result.mailbox).data, status=status.HTTP_201_CREATED)


class TenantMailboxDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug, domain_pk, pk):
        domain, _ = domain_and_membership(request, tenant_slug, domain_pk)
        mailbox = get_object_or_404(
            domain.mailboxes.exclude(status=Mailbox.Status.DELETED),
            pk=pk,
        )
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
            return Response(
                {"detail": "The mail backend is currently unavailable or not configured."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(ForwarderSerializer(result.alias).data, status=status.HTTP_201_CREATED)


class TenantForwarderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug, domain_pk, pk):
        domain, _ = domain_and_membership(request, tenant_slug, domain_pk)
        forwarder = get_object_or_404(domain.aliases.filter(active=True), pk=pk)
        return Response(ForwarderSerializer(forwarder).data)
