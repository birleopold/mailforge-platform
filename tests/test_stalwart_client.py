import httpx
import pytest

from integrations.stalwart.client import StalwartAPIError, StalwartClient


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

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    class MockClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", MockClient)
    client = StalwartClient(base_url="https://mail.example.com", token="test-token")
    created = client.create_domain(domain="example.com", max_mailboxes=5, quota_mb=10240)

    assert created["id"] == "domain-1"
    monkeypatch.setattr(httpx, "Client", original_client)


def test_jmap_error_is_raised(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={"methodResponses": [["error", {"type": "forbidden"}, "c1"]]},
        )

    transport = httpx.MockTransport(handler)

    class MockClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", MockClient)
    client = StalwartClient(base_url="https://mail.example.com", token="test-token")

    with pytest.raises(StalwartAPIError):
        client.create_domain(domain="example.com", max_mailboxes=5, quota_mb=10240)
