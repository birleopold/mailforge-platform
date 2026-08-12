import json

import httpx

from integrations.stalwart.client import StalwartClient


def test_forwarder_lifecycle_uses_mailing_list_update_and_destroy(monkeypatch):
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        method, args, call_id = payload["methodCalls"][0]
        assert method == "x:MailingList/set"
        calls.append(args)
        if "destroy" in args:
            data = {"destroyed": ["list-1"]}
        else:
            data = {"updated": {"list-1": None}}
        return httpx.Response(200, json={"methodResponses": [[method, data, call_id]]})

    transport = httpx.MockTransport(handler)

    class MockClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", MockClient)
    client = StalwartClient(base_url="https://mail.example.com", token="test-token")

    client.update_alias(
        alias_id="list-1",
        destinations=["first@example.net", "second@example.org"],
    )
    client.delete_alias(alias_id="list-1")

    assert calls == [
        {
            "update": {
                "list-1": {
                    "recipients": ["first@example.net", "second@example.org"]
                }
            }
        },
        {"destroy": ["list-1"]},
    ]
