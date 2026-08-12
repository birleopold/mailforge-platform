import re

from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

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
