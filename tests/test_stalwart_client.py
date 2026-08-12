import json

import httpx
import pytest

from integrations.stalwart.client import StalwartAPIError, StalwartClient


def _mock_httpx(monkeypatch, handler):
    transport = httpx.MockTransport(handler)

    class MockClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", MockClient)


def test_create_domain_uses_management_jmap(monkeypatch):
    def handler(request):
        payload = request.read().decode()
        assert request.url.path == "/api"
        assert request.headers["authorization"] == "Bearer test-token"
        assert '"x:Domain/set"' in payload
        assert '"example.com"' in payload
        return httpx.Response(
            200,
            json={
                "methodResponses": [
                    [
                        "x:Domain/set",
                        {"created": {"mailforge": {"id": "domain-1"}}},
                        "c1",
                    ]
                ]
            },
        )

    _mock_httpx(monkeypatch, handler)
    client = StalwartClient(base_url="https://mail.example.com", token="test-token")
    created = client.create_domain(domain="example.com", max_mailboxes=5, quota_mb=10240)

    assert created["id"] == "domain-1"


def test_get_domain_requests_dns_zone_and_dkim_management(monkeypatch):
    zone_file = '$ORIGIN example.com.\nselector._domainkey TXT "v=DKIM1; p=ABC"\n'

    def handler(request):
        payload = json.loads(request.content)
        method, args, call_id = payload["methodCalls"][0]
        assert method == "x:Domain/get"
        assert args == {
            "ids": ["domain-1"],
            "properties": ["id", "name", "dnsZoneFile", "dkimManagement"],
        }
        return httpx.Response(
            200,
            json={
                "methodResponses": [
                    [
                        method,
                        {
                            "list": [
                                {
                                    "id": "domain-1",
                                    "name": "example.com",
                                    "dnsZoneFile": zone_file,
                                    "dkimManagement": {"@type": "Automatic"},
                                }
                            ]
                        },
                        call_id,
                    ]
                ]
            },
        )

    _mock_httpx(monkeypatch, handler)
    client = StalwartClient(base_url="https://mail.example.com", token="test-token")

    domain = client.get_domain("domain-1")

    assert domain["name"] == "example.com"
    assert domain["dnsZoneFile"] == zone_file
    assert domain["dkimManagement"] == {"@type": "Automatic"}


def test_jmap_error_is_raised(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={"methodResponses": [["error", {"type": "forbidden"}, "c1"]]},
        )

    _mock_httpx(monkeypatch, handler)
    client = StalwartClient(base_url="https://mail.example.com", token="test-token")

    with pytest.raises(StalwartAPIError):
        client.create_domain(domain="example.com", max_mailboxes=5, quota_mb=10240)
