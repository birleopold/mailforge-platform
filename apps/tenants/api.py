from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import Tenant, TenantInvitation, TenantMembership
from apps.tenants.services import (
    INVITABLE_ROLES,
    MEMBERSHIP_MANAGE_ROLES,
    TenantMembershipError,
    change_membership_role,
    create_tenant,
    create_tenant_invitation,
    remove_tenant_membership,
    revoke_tenant_invitation,
    send_tenant_invitation_email,
)
from django.conf import settings


class TenantSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = (
            "id",
            "name",
            "slug",
            "kind",
            "status",
            "plan_code",
            "role",
            "created_at",
        )
        read_only_fields = (
            "id",
            "slug",
            "kind",
            "status",
            "plan_code",
            "role",
            "created_at",
        )

    def get_role(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        return obj.memberships.filter(user=request.user).values_list("role", flat=True).first()

    def create(self, validated_data):
        request = self.context["request"]
        return create_tenant(name=validated_data["name"], owner=request.user)


class TenantMembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.get_username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = TenantMembership
        fields = ("id", "username", "email", "role")
        read_only_fields = fields


class TenantInvitationSerializer(serializers.ModelSerializer):
    invited_by = serializers.CharField(source="invited_by.get_username", read_only=True)

    class Meta:
        model = TenantInvitation
        fields = (
            "id",
            "email",
            "role",
            "invited_by",
            "expires_at",
            "accepted_at",
            "revoked_at",
            "created_at",
        )
        read_only_fields = fields


class TenantInvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=sorted(INVITABLE_ROLES))

    def validate_email(self, value):
        return value.strip().lower()


class TenantMembershipRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=sorted(INVITABLE_ROLES))


def tenant_and_membership(request, tenant_slug):
    tenant = get_object_or_404(
        Tenant.objects.filter(memberships__user=request.user).distinct(),
        slug=tenant_slug,
    )
    membership = get_object_or_404(TenantMembership, tenant=tenant, user=request.user)
    return tenant, membership


class TenantListCreateView(generics.ListCreateAPIView):
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Tenant.objects.filter(memberships__user=self.request.user).distinct().order_by("name")


class TenantDetailView(generics.RetrieveAPIView):
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return Tenant.objects.filter(memberships__user=self.request.user).distinct()


class TenantMemberListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug):
        tenant, _ = tenant_and_membership(request, tenant_slug)
        members = tenant.memberships.select_related("user").order_by("role", "user__username")
        return Response(TenantMembershipSerializer(members, many=True).data)


class TenantMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, tenant_slug, pk):
        tenant, actor_membership = tenant_and_membership(request, tenant_slug)
        if actor_membership.role != TenantMembership.Role.OWNER:
            raise PermissionDenied("Only the organization owner can change member roles.")
        target = get_object_or_404(TenantMembership, tenant=tenant, pk=pk)
        serializer = TenantMembershipRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = change_membership_role(
                target.pk,
                role=serializer.validated_data["role"],
                actor=request.user,
            )
        except TenantMembershipError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TenantMembershipSerializer(updated).data)

    def delete(self, request, tenant_slug, pk):
        tenant, actor_membership = tenant_and_membership(request, tenant_slug)
        if actor_membership.role != TenantMembership.Role.OWNER:
            raise PermissionDenied("Only the organization owner can remove members.")
        target = get_object_or_404(TenantMembership, tenant=tenant, pk=pk)
        try:
            remove_tenant_membership(target.pk, actor=request.user)
        except TenantMembershipError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TenantInvitationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_slug):
        tenant, _ = tenant_and_membership(request, tenant_slug)
        invitations = tenant.invitations.filter(
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).select_related("invited_by")
        return Response(TenantInvitationSerializer(invitations, many=True).data)

    def post(self, request, tenant_slug):
        tenant, membership = tenant_and_membership(request, tenant_slug)
        if membership.role not in MEMBERSHIP_MANAGE_ROLES:
            raise PermissionDenied("Only owners and administrators can invite members.")
        serializer = TenantInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = create_tenant_invitation(
                tenant.pk,
                email=serializer.validated_data["email"],
                role=serializer.validated_data["role"],
                actor=request.user,
                expires_hours=settings.MAILFORGE_INVITATION_HOURS,
            )
        except TenantMembershipError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        accept_path = reverse("tenant-invitation", kwargs={"token": result.token})
        accept_url = request.build_absolute_uri(accept_path)
        try:
            send_tenant_invitation_email(result.invitation, accept_url=accept_url)
        except Exception:
            revoke_tenant_invitation(result.invitation.pk, actor=request.user)
            return Response(
                {"detail": "The invitation email could not be delivered and the invitation was revoked."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        data = TenantInvitationSerializer(result.invitation).data
        data["accept_url"] = accept_url
        return Response(data, status=status.HTTP_201_CREATED)


class TenantInvitationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, tenant_slug, pk):
        tenant, membership = tenant_and_membership(request, tenant_slug)
        if membership.role not in MEMBERSHIP_MANAGE_ROLES:
            raise PermissionDenied("Only owners and administrators can revoke invitations.")
        invitation = get_object_or_404(TenantInvitation, tenant=tenant, pk=pk)
        try:
            revoke_tenant_invitation(invitation.pk, actor=request.user)
        except TenantMembershipError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)
