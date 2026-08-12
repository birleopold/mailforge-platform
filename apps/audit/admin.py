from django.contrib import admin

from apps.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "tenant", "actor", "action", "target_type", "target_id")
    list_filter = ("action", "target_type")
    search_fields = ("action", "target_id", "tenant__name", "actor__username", "actor__email")
    readonly_fields = (
        "tenant",
        "actor",
        "action",
        "target_type",
        "target_id",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
