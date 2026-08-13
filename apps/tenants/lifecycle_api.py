from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.api import TenantSerializer, tenant_and_membership
from apps.tenants.lifecycle import reactivate_tenant, suspend_tenant
from apps.tenants.models import TenantMembership
from apps.tenants.services import TenantMembershipError


class TenantEmergencySuspendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug):
        tenant, membership = tenant_and_membership(request, tenant_slug)
        if membership.role != TenantMembership.Role.OWNER:
            raise PermissionDenied("Only the organization owner can use emergency suspension controls.")
        try:
            result = suspend_tenant(tenant.pk, actor=request.user)
        except TenantMembershipError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        data = TenantSerializer(result.tenant, context={"request": request}).data
        data["backend_enforced"] = result.success
        data["failed_domains"] = list(result.failed_domains)
        return Response(
            data,
            status=status.HTTP_200_OK if result.success else status.HTTP_502_BAD_GATEWAY,
        )


class TenantEmergencyReactivateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug):
        tenant, membership = tenant_and_membership(request, tenant_slug)
        if membership.role != TenantMembership.Role.OWNER:
            raise PermissionDenied("Only the organization owner can use emergency suspension controls.")
        try:
            result = reactivate_tenant(tenant.pk, actor=request.user)
        except TenantMembershipError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        data = TenantSerializer(result.tenant, context={"request": request}).data
        data["backend_restored"] = result.success
        data["failed_domains"] = list(result.failed_domains)
        return Response(
            data,
            status=status.HTTP_200_OK if result.success else status.HTTP_502_BAD_GATEWAY,
        )
