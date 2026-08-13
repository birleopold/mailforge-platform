from __future__ import annotations

import re
from dataclasses import dataclass

import nh3


ALLOWED_EMAIL_TAGS = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "code",
    "del",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "ins",
    "li",
    "ol",
    "p",
    "pre",
    "q",
    "s",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}

ALLOWED_EMAIL_ATTRIBUTES = {
    "a": {"href", "title"},
    "abbr": {"title"},
    "blockquote": {"cite"},
    "q": {"cite"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}

CLEAN_CONTENT_TAGS = {
    "applet",
    "audio",
    "canvas",
    "embed",
    "iframe",
    "math",
    "object",
    "script",
    "style",
    "svg",
    "template",
    "video",
}

SAFE_URL_SCHEMES = {"http", "https", "mailto"}
_REMOTE_IMAGE_RE = re.compile(r"<\s*img\b", re.IGNORECASE)


@dataclass(frozen=True)
class SanitizedEmailHTML:
    html: str
    remote_images_blocked: bool


def extract_html_body(email: dict) -> str:
    body_values = email.get("bodyValues") or {}
    chunks = []
    for part in email.get("htmlBody") or []:
        part_id = part.get("partId")
        if not part_id:
            continue
        value = body_values.get(part_id, {}).get("value")
        if value:
            chunks.append(str(value))
    return "\n".join(chunks).strip()


def sanitize_email_html(raw_html: str) -> SanitizedEmailHTML:
    raw_html = raw_html or ""
    if not raw_html.strip():
        return SanitizedEmailHTML(html="", remote_images_blocked=False)

    remote_images_blocked = bool(_REMOTE_IMAGE_RE.search(raw_html))
    cleaned = nh3.clean(
        raw_html,
        tags=ALLOWED_EMAIL_TAGS,
        clean_content_tags=CLEAN_CONTENT_TAGS,
        attributes=ALLOWED_EMAIL_ATTRIBUTES,
        strip_comments=True,
        link_rel="noopener noreferrer nofollow",
        set_tag_attribute_values={"a": {"target": "_blank"}},
        url_schemes=SAFE_URL_SCHEMES,
        url_relative="deny",
    )
    return SanitizedEmailHTML(
        html=cleaned.strip(),
        remote_images_blocked=remote_images_blocked,
    )
