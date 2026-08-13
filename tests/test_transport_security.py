from apps.domains.transport_security import check_mta_sts, check_tls_reporting


class FakeTXT:
    def __init__(self, value: str):
        self.strings = [value.encode()]


class FakeMX:
    def __init__(self, exchange: str):
        self.exchange = exchange


class FakeResolver:
    def __init__(self, records):
        self.records = records

    def resolve(self, name, record_type, **kwargs):
        return self.records.get((str(name), record_type), [])


class FakeResponse:
    def __init__(self, text, *, status_code=200, content_type="text/plain"):
        self.text = text
        self.content = text.encode()
        self.status_code = status_code
        self.headers = {"content-type": content_type}


def test_valid_mta_sts_policy_covers_public_mx_hosts():
    resolver = FakeResolver(
        {
            ("_mta-sts.example.com", "TXT"): [FakeTXT("v=STSv1; id=20260813;")],
            ("example.com", "MX"): [
                FakeMX("mail.example.com."),
                FakeMX("backup.example.net."),
            ],
        }
    )
    requested = []

    def get(url, **kwargs):
        requested.append((url, kwargs))
        return FakeResponse(
            "version: STSv1\n"
            "mode: enforce\n"
            "mx: mail.example.com\n"
            "mx: *.example.net\n"
            "max_age: 604800\n"
        )

    result = check_mta_sts(resolver, "example.com", http_get=get)

    assert result["status"] == "pass"
    assert result["required"] is False
    assert "enforce" in result["detail"]
    assert requested[0][0] == "https://mta-sts.example.com/.well-known/mta-sts.txt"
    assert requested[0][1]["follow_redirects"] is False


def test_mta_sts_redirect_is_rejected():
    resolver = FakeResolver(
        {
            ("_mta-sts.example.com", "TXT"): [FakeTXT("v=STSv1; id=abc123;")],
        }
    )

    result = check_mta_sts(
        resolver,
        "example.com",
        http_get=lambda *args, **kwargs: FakeResponse(
            "",
            status_code=301,
            content_type="text/plain",
        ),
    )

    assert result["status"] == "fail"
    assert "redirects" in result["detail"].lower()


def test_mta_sts_requires_plain_text_policy():
    resolver = FakeResolver(
        {
            ("_mta-sts.example.com", "TXT"): [FakeTXT("v=STSv1; id=abc123;")],
        }
    )

    result = check_mta_sts(
        resolver,
        "example.com",
        http_get=lambda *args, **kwargs: FakeResponse(
            "<html>not a policy</html>",
            content_type="text/html",
        ),
    )

    assert result["status"] == "fail"
    assert result["expected"] == "Content-Type: text/plain"


def test_mta_sts_fails_when_policy_does_not_cover_published_mx():
    resolver = FakeResolver(
        {
            ("_mta-sts.example.com", "TXT"): [FakeTXT("v=STSv1; id=abc123;")],
            ("example.com", "MX"): [FakeMX("deep.mail.example.net.")],
        }
    )

    result = check_mta_sts(
        resolver,
        "example.com",
        http_get=lambda *args, **kwargs: FakeResponse(
            "version: STSv1\n"
            "mode: enforce\n"
            "mx: *.example.net\n"
            "max_age: 604800\n"
        ),
    )

    assert result["status"] == "fail"
    assert "deep.mail.example.net" in result["detail"]


def test_testing_mode_is_valid_and_non_gating():
    resolver = FakeResolver(
        {
            ("_mta-sts.example.com", "TXT"): [FakeTXT("v=STSv1; id=test1;")],
            ("example.com", "MX"): [FakeMX("mail.example.com.")],
        }
    )

    result = check_mta_sts(
        resolver,
        "example.com",
        http_get=lambda *args, **kwargs: FakeResponse(
            "version: STSv1\n"
            "mode: testing\n"
            "mx: mail.example.com\n"
            "max_age: 86400\n"
        ),
    )

    assert result["status"] == "pass"
    assert result["required"] is False
    assert "testing" in result["detail"]


def test_valid_tls_reporting_mailto_and_https_endpoints():
    resolver = FakeResolver(
        {
            ("_smtp._tls.example.com", "TXT"): [
                FakeTXT(
                    "v=TLSRPTv1; rua=mailto:tls@example.com,https://reports.example.net/tls"
                )
            ]
        }
    )

    result = check_tls_reporting(resolver, "example.com")

    assert result["status"] == "pass"
    assert result["required"] is False
    assert result["observed"] == [
        "mailto:tls@example.com",
        "https://reports.example.net/tls",
    ]


def test_tls_reporting_rejects_unsupported_rua_scheme():
    resolver = FakeResolver(
        {
            ("_smtp._tls.example.com", "TXT"): [
                FakeTXT("v=TLSRPTv1; rua=ftp://reports.example.com/tls")
            ]
        }
    )

    result = check_tls_reporting(resolver, "example.com")

    assert result["status"] == "fail"
    assert "mailto" in result["detail"]
    assert "https" in result["detail"]
