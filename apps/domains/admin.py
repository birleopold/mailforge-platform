from django.contrib import admin

from apps.domains.models import Domain


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "tenant",
        "status",
        "backend",
        "sending_enabled",
        "verified_at",
        "created_at",
    )
    list_filter = ("status", "backend", "sending_enabled")
    search_fields = ("name", "tenant__name", "tenant__slug")
    readonly_fields = (
        "ownership_token",
        "verification_record_name",
        "verification_record_value",
        "verified_at",
        "backend_identifier",
        "created_at",
    )
