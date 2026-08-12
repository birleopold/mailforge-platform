from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.domains.dns_readiness import check_domain_dns
from apps.domains.models import Domain, normalize_domain_name
from apps.domains.provisioning import DomainProvisioningError, provision_domain
from apps.domains.services import (
    DomainVerificationTemporaryError,
    verify_domain_and_record,
)
from apps.tenants.models import Tenant, TenantMembership
from integrations.factory import MailBackendConfigurationError, UnsupportedMailBackend
from integrations.stalwart.client import StalwartAPIError


MANAGE_ROLES = {TenantMembership.Role.OWNER, TenantMembership.Role.ADMIN}


def tenant_membership_for_request(request, tenant_slug):
    tenant = get_object_or_404(
        Tenant.objects.filter(memberships__user=request.user).distinct(),
        slug=tenant_slug,
    )
    membership = get_object_or_404(
        TenantMembership,
        tenant=tenant,
        user=request.user,
    )
    return tenant, membership


class DomainSerializer(serializers.ModelSerializer):
    verification_record_name = serializers.CharField(read_only=True)
    verification_record_value = serializers.CharField(read_only=True)

    class Meta:
        model = Domain
        fields = (
            "id",
            "name",
            "status",
            "backend",
            "backend_identifier",
            "sending_enabled",
            "verification_record_name",
            "verification_record_value",
            "verified_at",
            "dns_checks",
            "dns_checked_at",
            "created_at",
        )
        read_only_fields = (
            "id",
            "status",
            "backend",
            "backend_identifier",
            "sending_enabled",
            "verification_record_name",
            "verification_record_value",
            "verified_at",
            "dns_checks",
            "dns_checked_at",
            "created_at",
        )

    def validate_name(self, value):
        normalized = normalize_domain_name(value)
        if Domain.objects.filter(name=normalized).exists():
            raise serializers.ValidationError("This domain cannot be added.")
        return normalized


class TenantDomainListCreateView(generics.ListCreateAPIView):
    serializer_class = DomainSerializer
    permission_classes = [IsAuthenticated]

    def get_tenant_and_membership(self):
        if not hasattr(self, "_tenant_membership"):
            self._tenant_membership = tenant_membership_for_request(
                self.request,
                self.kwargs["tenant_slug"],
            )
        return self._tenant_membership

    def get_queryset(self):
        tenant, _ = self.get_tenant_and_membership()
        return tenant.domains.order_by("name")

    def perform_create(self, serializer):
        tenant, membership = self.get_tenant_and_membership()
        if membership.role not in MANAGE_ROLES:
            raise PermissionDenied("Only tenant owners and administrators can add domains.")
        domain = serializer.save(tenant=tenant, backend="stalwart")
        AuditEvent.objects.create(
            tenant=tenant,
            actor=self.request.user,
            action="domain.created",
            target_type="domain",
            target_id=str(domain.pk),
            metadata={"domain": domain.name},
        )


class TenantDomainDetailView(generics.RetrieveAPIView):
    serializer_class = DomainSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant, _ = tenant_membership_for_request(
            self.request,
            self.kwargs["tenant_slug"],
        )
        return tenant.domains.all()


class TenantDomainVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug, pk):
        tenant, membership = tenant_membership_for_request(request, tenant_slug)
        if membership.role not in MANAGE_ROLES:
            raise PermissionDenied("Only tenant owners and administrators can verify domains.")

        domain = get_object_or_404(tenant.domains, pk=pk)
        try:
            result = verify_domain_and_record(domain.pk)
        except DomainVerificationTemporaryError:
            return Response(
                {"detail": "DNS verification is temporarily unavailable. Try again shortly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        domain.refresh_from_db()
        return Response(
            {
                "verified": result.verified,
                "already_verified": result.already_verified,
                "observed_values": list(result.observed_values),
                "domain": DomainSerializer(domain, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


class TenantDomainProvisionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug, pk):
        tenant, membership = tenant_membership_for_request(request, tenant_slug)
        if membership.role not in MANAGE_ROLES:
            raise PermissionDenied("Only tenant owners and administrators can provision domains.")

        domain = get_object_or_404(tenant.domains, pk=pk)
        try:
            result = provision_domain(domain.pk, actor=request.user)
        except DomainProvisioningError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except (MailBackendConfigurationError, UnsupportedMailBackend, StalwartAPIError):
            return Response(
                {"detail": "The mail backend is currently unavailable or not configured."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        domain.refresh_from_db()
        return Response(
            {
                "provisioned": True,
                "already_provisioned": result.already_provisioned,
                "domain": DomainSerializer(domain, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


class TenantDomainDNSCheckView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, tenant_slug, pk):
        tenant, membership = tenant_membership_for_request(request, tenant_slug)
        if membership.role not in MANAGE_ROLES:
            raise PermissionDenied("Only tenant owners and administrators can run DNS readiness checks.")

        domain = get_object_or_404(tenant.domains, pk=pk)
        result = check_domain_dns(domain.pk, actor=request.user)
        domain.refresh_from_db()
        return Response(
            {
                "ready": result.ready,
                "checks": result.checks,
                "domain": DomainSerializer(domain, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )
