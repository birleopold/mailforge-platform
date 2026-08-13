from django.template import Context, Template

from mailforge.webmail_html import extract_html_body, sanitize_email_html


def test_extract_html_body_joins_jmap_html_parts():
    email = {
        "htmlBody": [{"partId": "1"}, {"partId": "2"}],
        "bodyValues": {
            "1": {"value": "<p>Hello</p>"},
            "2": {"value": "<p>World</p>"},
        },
    }

    assert extract_html_body(email) == "<p>Hello</p>\n<p>World</p>"


def test_sanitizer_removes_script_embeds_styles_and_remote_images():
    result = sanitize_email_html(
        """
        <style>body { display: none }</style>
        <script>alert('xss')</script>
        <iframe src="https://evil.example/frame"></iframe>
        <p style="position:fixed" onclick="alert(1)">Hello <strong>world</strong></p>
        <img src="https://tracker.example/pixel.gif" onerror="alert(1)">
        """
    )

    assert result.remote_images_blocked is True
    assert "script" not in result.html.lower()
    assert "alert" not in result.html.lower()
    assert "iframe" not in result.html.lower()
    assert "style=" not in result.html.lower()
    assert "onclick" not in result.html.lower()
    assert "<img" not in result.html.lower()
    assert "<strong>world</strong>" in result.html


def test_sanitizer_blocks_javascript_and_relative_urls_but_keeps_safe_links():
    result = sanitize_email_html(
        """
        <a href="javascript:alert(1)">bad</a>
        <a href="/relative/path">relative</a>
        <a href="https://example.com/path">safe</a>
        <a href="mailto:person@example.com">mail</a>
        """
    )

    assert "javascript:" not in result.html
    assert 'href="/relative/path"' not in result.html
    assert 'href="https://example.com/path"' in result.html
    assert 'href="mailto:person@example.com"' in result.html
    assert 'target="_blank"' in result.html
    assert "noopener" in result.html
    assert "noreferrer" in result.html
    assert "nofollow" in result.html


def test_sanitizer_preserves_basic_email_formatting_and_tables():
    result = sanitize_email_html(
        "<h2>Invoice</h2><table><tr><th>Item</th><td colspan='2'>Hosting</td></tr></table>"
    )

    assert "<h2>Invoice</h2>" in result.html
    assert "<table>" in result.html
    assert 'colspan="2"' in result.html


def test_message_body_template_tag_renders_sanitized_html_not_raw_attack():
    template = Template(
        "{% load webmail_html %}{% sanitized_email_body email plain_text_body %}"
    )
    rendered = template.render(
        Context(
            {
                "email": {
                    "htmlBody": [{"partId": "html"}],
                    "bodyValues": {
                        "html": {
                            "value": (
                                '<p>Safe</p><img src="https://tracker.example/pixel">'
                                '<script>alert("x")</script>'
                            )
                        }
                    },
                },
                "plain_text_body": "Safe plain text",
            }
        )
    )

    assert "<p>Safe</p>" in rendered
    assert "Remote images blocked for privacy" in rendered
    assert "tracker.example" not in rendered
    assert "<script" not in rendered
    assert "Safe plain text" in rendered
