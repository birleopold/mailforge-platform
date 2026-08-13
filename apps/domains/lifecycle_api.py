from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.domains.api import MANAGE_ROLES, DomainSerializer, tenant_membership_for_request
from apps.domains.lifecycle import DomainLifecycleError, reactivate_domain, suspend_domain
from apps.domains.models import Domain


def _domain_and_membership(request, tenant_slug, pk):
    tenant, membership = tenant_membership_for_request(request, tenant_slug)
    try:
        domain = tenant.domains.get(pk=pk)
    except Domain.DoesNotExist:
        return None, membership
    return domain, membership


class TenantDomainEmergencySuspendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug, pk):
        domain, membership = _domain_and_membership(request, tenant_slug, pk)
        if domain is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if membership.role not in MANAGE_ROLES:
            raise PermissionDenied("Only owners and administrators can suspend domains.")
        try:
            result = suspend_domain(domain.pk, actor=request.user)
        except DomainLifecycleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        data = DomainSerializer(result.domain).data
        data["backend_enforced"] = result.success
        data["failed_addresses"] = list(result.failed_addresses)
        return Response(
            data,
            status=status.HTTP_200_OK if result.success else status.HTTP_502_BAD_GATEWAY,
        )


class TenantDomainEmergencyReactivateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug, pk):
        domain, membership = _domain_and_membership(request, tenant_slug, pk)
        if domain is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if membership.role not in MANAGE_ROLES:
            raise PermissionDenied("Only owners and administrators can reactivate domains.")
        try:
            result = reactivate_domain(domain.pk, actor=request.user)
        except DomainLifecycleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        data = DomainSerializer(result.domain).data
        data["backend_restored"] = result.success
        data["failed_addresses"] = list(result.failed_addresses)
        return Response(
            data,
            status=status.HTTP_200_OK if result.success else status.HTTP_502_BAD_GATEWAY,
        )
