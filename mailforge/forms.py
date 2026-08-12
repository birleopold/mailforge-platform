import re

from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.domains.models import normalize_domain_name
from apps.mailboxes.forwarders import normalize_destinations
from apps.mailboxes.models import normalize_local_part


class TenantCreateForm(forms.Form):
    name = forms.CharField(max_length=200, label="Organization name")


class DomainCreateForm(forms.Form):
    name = forms.CharField(max_length=253, label="Domain name", help_text="Example: company.com")

    def clean_name(self):
        return normalize_domain_name(self.cleaned_data["name"])


class MailboxCreateForm(forms.Form):
    local_part = forms.CharField(max_length=64, label="Mailbox name")
    display_name = forms.CharField(max_length=200, required=False)
    quota_mb = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=settings.MAILFORGE_MAX_MAILBOX_QUOTA_MB,
        help_text="Leave blank to use the default quota.",
    )
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=False),
        strip=False,
        help_text="The password is sent to Stalwart and is not stored in MailForge.",
    )

    def clean_local_part(self):
        return normalize_local_part(self.cleaned_data["local_part"])

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password


class ForwarderCreateForm(forms.Form):
    local_part = forms.CharField(max_length=64, label="Forwarder name")
    destinations = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Separate destination addresses with commas or new lines.",
    )

    def clean_local_part(self):
        return normalize_local_part(self.cleaned_data["local_part"])

    def clean_destinations(self):
        raw = self.cleaned_data["destinations"]
        values = [item for item in re.split(r"[\s,;]+", raw) if item]
        try:
            return normalize_destinations(values)
        except RuntimeError as exc:
            raise ValidationError(str(exc)) from exc


def _parse_compose_addresses(value: str) -> list[dict[str, str]]:
    addresses = []
    seen = set()
    for raw in re.split(r"[\s,;]+", value.strip()):
        email = raw.strip().lower()
        if not email:
            continue
        try:
            validate_email(email)
        except ValidationError as exc:
            raise ValidationError(f"Invalid email address: {email}") from exc
        if email not in seen:
            addresses.append({"email": email})
            seen.add(email)
    return addresses


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return [single_file_clean(data, initial)]


class ComposeForm(forms.Form):
    identity_id = forms.ChoiceField(label="From")
    to = forms.CharField(label="To", help_text="Separate multiple addresses with commas.")
    cc = forms.CharField(label="Cc", required=False)
    bcc = forms.CharField(label="Bcc", required=False)
    subject = forms.CharField(max_length=998, required=False)
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 14}), required=False)
    attachments = MultipleFileField(
        required=False,
        label="Attachments",
        help_text=(
            f"Up to {settings.MAILFORGE_MAX_ATTACHMENT_MB} MB per file and "
            f"{settings.MAILFORGE_MAX_TOTAL_ATTACHMENT_MB} MB total."
        ),
    )

    def __init__(self, *args, identities=None, **kwargs):
        super().__init__(*args, **kwargs)
        identities = identities or []
        self.fields["identity_id"].choices = [
            (identity["id"], f"{identity.get('name') or identity['email']} <{identity['email']}>")
            for identity in identities
        ]

    def clean_to(self):
        addresses = _parse_compose_addresses(self.cleaned_data["to"])
        if not addresses:
            raise ValidationError("Enter at least one recipient.")
        return addresses

    def clean_cc(self):
        return _parse_compose_addresses(self.cleaned_data.get("cc", ""))

    def clean_bcc(self):
        return _parse_compose_addresses(self.cleaned_data.get("bcc", ""))

    def clean_attachments(self):
        files = self.cleaned_data.get("attachments") or []
        max_file_bytes = settings.MAILFORGE_MAX_ATTACHMENT_MB * 1024 * 1024
        max_total_bytes = settings.MAILFORGE_MAX_TOTAL_ATTACHMENT_MB * 1024 * 1024
        total = 0
        for uploaded in files:
            if uploaded.size > max_file_bytes:
                raise ValidationError(
                    f"{uploaded.name} exceeds the {settings.MAILFORGE_MAX_ATTACHMENT_MB} MB per-file limit."
                )
            total += uploaded.size
        if total > max_total_bytes:
            raise ValidationError(
                f"Attachments exceed the {settings.MAILFORGE_MAX_TOTAL_ATTACHMENT_MB} MB total limit."
            )
        return files
