import hashlib
import logging
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


def test_failed_validation_does_not_ack(tmp_path, monkeypatch):
    media_bytes = b"invalid mp4 bytes"
    item_id = "delivery-invalid"
    channel_id = "01_Citadel"
    filename = "episode.mp4"
    destination = tmp_path / channel_id / filename
    temp_path = tmp_path / ".downloads" / f"{item_id}.tmp"
    requests = []
    validated_paths = []
    validated_bytes = []

    def validate_ready_profile(path):
        validated_paths.append(path)
        validated_bytes.append(path.read_bytes())
        return False

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

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
            return httpx.Response(200, content=media_bytes)

        if request.method == "POST" and request.url.path == f"/api/v1/ack/{item_id}":
            return httpx.Response(204)

        return httpx.Response(404)

    monkeypatch.setattr(
        poller_module,
        "validate_ready_profile",
        validate_ready_profile,
        raising=False,
    )
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

    assert not destination.exists()
    assert not temp_path.exists()
    assert validated_paths == [temp_path]
    assert validated_bytes == [media_bytes]
    assert [request.url.path for request in requests] == [
        "/api/v1/ready",
        "/downloads/episode.mp4",
    ]


def test_failed_download_does_not_ack(tmp_path, monkeypatch, caplog):
    item_id = "delivery-download-fails"
    channel_id = "01_Citadel"
    filename = "episode.mp4"
    destination = tmp_path / channel_id / filename
    temp_path = tmp_path / ".downloads" / f"{item_id}.tmp"
    requests = []

    def validate_ready_profile(path):
        raise AssertionError("validation should not run after failed download")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

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
                        }
                    ]
                },
            )

        if request.method == "GET" and request.url.path == "/downloads/episode.mp4":
            return httpx.Response(503)

        if request.method == "POST" and request.url.path == f"/api/v1/ack/{item_id}":
            return httpx.Response(204)

        return httpx.Response(404)

    monkeypatch.setattr(
        poller_module,
        "validate_ready_profile",
        validate_ready_profile,
        raising=False,
    )
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

    caplog.set_level(logging.WARNING, logger="rick_tv_pi.poller")

    Poller(settings, http_client).poll_once(channels)

    assert not destination.exists()
    assert not temp_path.exists()
    assert len(caplog.records) == 1
    assert caplog.records[0].message == (
        "Failed to deliver ready item delivery-download-fails "
        "for channel 01_Citadel"
    )
    assert caplog.records[0].exc_info is not None
    assert [request.url.path for request in requests] == [
        "/api/v1/ready",
        "/downloads/episode.mp4",
    ]


def test_redelivery_overwrites_destination_and_acks(tmp_path, monkeypatch):
    first_media_bytes = b"old mp4 bytes"
    redelivered_media_bytes = b"new mp4 bytes"
    item_id = "delivery-redelivered"
    channel_id = "01_Citadel"
    filename = "episode.mp4"
    destination = tmp_path / channel_id / filename
    temp_path = tmp_path / ".downloads" / f"{item_id}.tmp"
    requests = []
    replace_calls = []
    original_replace = Path.replace

    destination.parent.mkdir(parents=True)
    destination.write_bytes(first_media_bytes)

    def validate_ready_profile(path):
        assert path == temp_path
        assert path.read_bytes() == redelivered_media_bytes
        return True

    def replace_spy(self, target):
        replace_calls.append((self, Path(target), Path(target).read_bytes()))
        assert self == temp_path
        assert Path(target) == destination
        return original_replace(self, target)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

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
                            "sha256": hashlib.sha256(
                                redelivered_media_bytes
                            ).hexdigest(),
                        }
                    ]
                },
            )

        if request.method == "GET" and request.url.path == "/downloads/episode.mp4":
            assert destination.read_bytes() == first_media_bytes
            return httpx.Response(200, content=redelivered_media_bytes)

        if request.method == "POST" and request.url.path == f"/api/v1/ack/{item_id}":
            assert destination.read_bytes() == redelivered_media_bytes
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

    assert destination.read_bytes() == redelivered_media_bytes
    assert replace_calls == [(temp_path, destination, first_media_bytes)]
    assert [request.url.path for request in requests] == [
        "/api/v1/ready",
        "/downloads/episode.mp4",
        f"/api/v1/ack/{item_id}",
    ]


def test_failed_item_does_not_block_next_delivery(tmp_path, monkeypatch):
    failed_media_bytes = b"invalid mp4 bytes"
    delivered_media_bytes = b"ready mp4 bytes"
    failed_item_id = "delivery-invalid"
    delivered_item_id = "delivery-ready"
    channel_id = "01_Citadel"
    failed_filename = "invalid.mp4"
    delivered_filename = "ready.mp4"
    failed_destination = tmp_path / channel_id / failed_filename
    delivered_destination = tmp_path / channel_id / delivered_filename
    failed_temp_path = tmp_path / ".downloads" / f"{failed_item_id}.tmp"
    delivered_temp_path = tmp_path / ".downloads" / f"{delivered_item_id}.tmp"
    requests = []
    validated_paths = []

    def validate_ready_profile(path):
        validated_paths.append(path)
        return path == delivered_temp_path

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        if request.method == "GET" and request.url.path == "/api/v1/ready":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": failed_item_id,
                            "channel_id": channel_id,
                            "filename": failed_filename,
                            "download_url": "https://server.example/downloads/invalid.mp4",
                            "sha256": hashlib.sha256(
                                failed_media_bytes
                            ).hexdigest(),
                        },
                        {
                            "id": delivered_item_id,
                            "channel_id": channel_id,
                            "filename": delivered_filename,
                            "download_url": "https://server.example/downloads/ready.mp4",
                            "sha256": hashlib.sha256(
                                delivered_media_bytes
                            ).hexdigest(),
                        },
                    ]
                },
            )

        if request.method == "GET" and request.url.path == "/downloads/invalid.mp4":
            return httpx.Response(200, content=failed_media_bytes)

        if request.method == "GET" and request.url.path == "/downloads/ready.mp4":
            return httpx.Response(200, content=delivered_media_bytes)

        if (
            request.method == "POST"
            and request.url.path == f"/api/v1/ack/{delivered_item_id}"
        ):
            assert delivered_destination.read_bytes() == delivered_media_bytes
            return httpx.Response(204)

        return httpx.Response(404)

    monkeypatch.setattr(
        poller_module,
        "validate_ready_profile",
        validate_ready_profile,
        raising=False,
    )
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

    assert not failed_destination.exists()
    assert not failed_temp_path.exists()
    assert delivered_destination.read_bytes() == delivered_media_bytes
    assert not delivered_temp_path.exists()
    assert validated_paths == [failed_temp_path, delivered_temp_path]
    assert [request.url.path for request in requests] == [
        "/api/v1/ready",
        "/downloads/invalid.mp4",
        "/downloads/ready.mp4",
        f"/api/v1/ack/{delivered_item_id}",
    ]
