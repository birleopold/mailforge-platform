from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.mailboxes.models import Alias, Mailbox, normalize_local_part


def _validate_password(value):
    try:
        validate_password(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from exc
    return value


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
        return _validate_password(value)


class MailboxPasswordResetSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_password(self, value):
        return _validate_password(value)


class ForwarderSerializer(serializers.ModelSerializer):
    email_address = serializers.CharField(read_only=True)

    class Meta:
        model = Alias
        fields = (
            "id",
            "email_address",
            "local_part",
            "destinations",
            "active",
            "created_at",
        )
        read_only_fields = fields


class ForwarderCreateSerializer(serializers.Serializer):
    local_part = serializers.CharField(max_length=64)
    destinations = serializers.ListField(
        child=serializers.EmailField(),
        allow_empty=False,
        max_length=settings.MAILFORGE_MAX_ALIAS_RECIPIENTS,
    )

    def validate_local_part(self, value):
        try:
            return normalize_local_part(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class ForwarderUpdateSerializer(serializers.Serializer):
    destinations = serializers.ListField(
        child=serializers.EmailField(),
        allow_empty=False,
        max_length=settings.MAILFORGE_MAX_ALIAS_RECIPIENTS,
    )
