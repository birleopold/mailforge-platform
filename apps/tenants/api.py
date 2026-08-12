from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from apps.tenants.models import Tenant
from apps.tenants.services import create_tenant


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
        request = self.context["request"]
        return create_tenant(name=validated_data["name"], owner=request.user)


class TenantListCreateView(generics.ListCreateAPIView):
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Tenant.objects.filter(memberships__user=self.request.user)
            .distinct()
            .order_by("name")
        )


class TenantDetailView(generics.RetrieveAPIView):
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return Tenant.objects.filter(memberships__user=self.request.user).distinct()
