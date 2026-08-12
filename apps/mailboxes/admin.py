from django.contrib import admin

from apps.mailboxes.models import Alias, Mailbox


@admin.register(Mailbox)
class MailboxAdmin(admin.ModelAdmin):
    list_display = ("email_address", "domain", "status", "quota_mb", "created_at")
    list_filter = ("status", "domain__tenant")
    search_fields = ("local_part", "display_name", "domain__name")
    readonly_fields = ("backend_identifier", "created_at")


@admin.register(Alias)
class AliasAdmin(admin.ModelAdmin):
    list_display = ("local_part", "domain", "active")
    list_filter = ("active", "domain__tenant")
    search_fields = ("local_part", "domain__name")
