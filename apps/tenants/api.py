from uuid import uuid4

from django.db import transaction
from django.utils.text import slugify
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from apps.tenants.models import Tenant, TenantMembership


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
        return (
            obj.memberships.filter(user=request.user)
            .values_list("role", flat=True)
            .first()
        )

    def create(self, validated_data):
        base = slugify(validated_data["name"])[:45] or "tenant"
        slug = base
        while Tenant.objects.filter(slug=slug).exists():
            slug = f"{base}-{uuid4().hex[:6]}"
        validated_data["slug"] = slug
        validated_data["kind"] = Tenant.Kind.CUSTOMER
        validated_data["status"] = Tenant.Status.ACTIVE
        validated_data["plan_code"] = "free"
        return super().create(validated_data)


class TenantListCreateView(generics.ListCreateAPIView):
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Tenant.objects.filter(memberships__user=self.request.user)
            .distinct()
            .order_by("name")
        )

    @transaction.atomic
    def perform_create(self, serializer):
        tenant = serializer.save()
        TenantMembership.objects.create(
            tenant=tenant,
            user=self.request.user,
            role=TenantMembership.Role.OWNER,
        )


class TenantDetailView(generics.RetrieveAPIView):
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return Tenant.objects.filter(memberships__user=self.request.user).distinct()
