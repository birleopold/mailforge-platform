from django.contrib import admin

from apps.tenants.models import Tenant, TenantInvitation, TenantMembership


class TenantMembershipInline(admin.TabularInline):
    model = TenantMembership
    extra = 0


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "kind", "status", "plan_code", "created_at")
    list_filter = ("kind", "status", "plan_code")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (TenantMembershipInline,)


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("tenant", "user", "role")
    list_filter = ("role",)
    search_fields = ("tenant__name", "tenant__slug", "user__username", "user__email")


@admin.register(TenantInvitation)
class TenantInvitationAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "tenant",
        "role",
        "invited_by",
        "expires_at",
        "accepted_at",
        "revoked_at",
    )
    list_filter = ("role", "accepted_at", "revoked_at")
    search_fields = ("email", "tenant__name", "tenant__slug")
    readonly_fields = ("token_hash", "created_at", "accepted_at", "revoked_at")
