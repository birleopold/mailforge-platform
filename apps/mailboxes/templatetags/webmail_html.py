from django import template
from django.utils.safestring import mark_safe

from mailforge.webmail_html import extract_html_body, sanitize_email_html


register = template.Library()


@register.inclusion_tag("webmail/_message_body.html")
def sanitized_email_body(email, plain_text_body):
    raw_html = extract_html_body(email)
    sanitized = sanitize_email_html(raw_html)
    return {
        "sanitized_html": mark_safe(sanitized.html),
        "plain_text_body": plain_text_body,
        "has_html": bool(sanitized.html),
        "remote_images_blocked": sanitized.remote_images_blocked,
    }
