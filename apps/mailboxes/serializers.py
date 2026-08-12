from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.mailboxes.models import Mailbox, normalize_local_part


class MailboxSerializer(serializers.ModelSerializer):
    email_address = serializers.CharField(read_only=True)

    class Meta:
        model = Mailbox
        fields = (
            "id",
            "email_address",
            "local_part",
            "display_name",
            "quota_mb",
            "status",
            "created_at",
        )
        read_only_fields = fields


class MailboxCreateSerializer(serializers.Serializer):
    local_part = serializers.CharField(max_length=64)
    display_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    quota_mb = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=settings.MAILFORGE_MAX_MAILBOX_QUOTA_MB,
    )
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_local_part(self, value):
        try:
            return normalize_local_part(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value
