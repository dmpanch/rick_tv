import hashlib
from pathlib import Path

import httpx

from rick_tv_pi.channels import Channel
from rick_tv_pi.config import PiSettings
import rick_tv_pi.poller as poller_module
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


def test_download_validate_atomic_move_then_ack(tmp_path, monkeypatch):
    media_bytes = b"ready mp4 bytes"
    item_id = "delivery-123"
    channel_id = "01_Citadel"
    filename = "episode.mp4"
    destination = tmp_path / channel_id / filename
    temp_path = tmp_path / ".downloads" / f"{item_id}.tmp"
    requests = []
    replace_calls = []
    original_replace = Path.replace

    def validate_ready_profile(path):
        assert path == temp_path
        assert path.read_bytes() == media_bytes
        return True

    def replace_spy(self, target):
        replace_calls.append((self, Path(target)))
        assert self == temp_path
        assert Path(target) == destination
        assert self.exists()
        assert self.read_bytes() == media_bytes
        return original_replace(self, target)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-token"

        if request.method == "GET" and request.url.path == "/api/v1/ready":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": item_id,
                            "channel_id": channel_id,
                            "filename": filename,
                            "download_url": "https://server.example/downloads/episode.mp4",
                            "sha256": hashlib.sha256(media_bytes).hexdigest(),
                        }
                    ]
                },
            )

        if request.method == "GET" and request.url.path == "/downloads/episode.mp4":
            assert not destination.exists()
            return httpx.Response(200, content=media_bytes)

        if request.method == "POST" and request.url.path == f"/api/v1/ack/{item_id}":
            assert destination.exists()
            assert destination.read_bytes() == media_bytes
            assert not temp_path.exists()
            return httpx.Response(204)

        return httpx.Response(404)

    monkeypatch.setattr(
        poller_module,
        "validate_ready_profile",
        validate_ready_profile,
        raising=False,
    )
    monkeypatch.setattr(Path, "replace", replace_spy)
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
            id=channel_id,
            number=1,
            display_name=None,
            path=tmp_path / channel_id,
        )
    ]

    Poller(settings, http_client).poll_once(channels)

    assert destination.exists()
    assert replace_calls == [(temp_path, destination)]
    assert [request.url.path for request in requests] == [
        "/api/v1/ready",
        "/downloads/episode.mp4",
        f"/api/v1/ack/{item_id}",
    ]
