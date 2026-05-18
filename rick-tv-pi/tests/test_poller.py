from pathlib import Path

import httpx

from rick_tv_pi.channels import Channel
from rick_tv_pi.config import PiSettings
from rick_tv_pi.poller import Poller


def test_poll_sends_authenticated_known_channels(tmp_path):
    seen_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, json={"items": []})

    http_client = httpx.Client(
        base_url="https://server.example",
        transport=httpx.MockTransport(handler),
    )
    settings = PiSettings(
        server_base_url="https://server.example",
        api_token="test-token",
        media_root=tmp_path,
    )
    channels = [
        Channel(
            id="01_Citadel",
            number=1,
            display_name=None,
            path=Path("/media/01_Citadel"),
        ),
        Channel(
            id="Garage",
            number=2,
            display_name=None,
            path=Path("/media/Garage"),
        ),
    ]

    result = Poller(settings, http_client).poll_once(channels)

    assert result == []
    assert len(seen_requests) == 1
    request = seen_requests[0]
    assert request.method == "GET"
    assert request.url.path == "/api/v1/ready"
    assert request.url.query == b"channels=01_Citadel,Garage"
    assert request.headers["Authorization"] == "Bearer test-token"
