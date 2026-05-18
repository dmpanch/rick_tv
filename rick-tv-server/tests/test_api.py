from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from rick_tv_server.api import create_app
from rick_tv_server.config import ServerSettings
from rick_tv_server.state import DeliveryStateStore


def make_settings(tmp_path: Path) -> ServerSettings:
    return ServerSettings(
        media_dir=tmp_path / "media",
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        api_token="test-token",
        public_base_url="https://example.test",
    )


def test_ready_endpoint_requires_bearer_token(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"
    media_bytes = b"ready mp4 bytes"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(media_bytes)
    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1-source.mp4",
    )
    store.mark_converting("item-1")
    store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
    )
    client = TestClient(create_app(settings, store))

    unauthenticated_response = client.get("/api/v1/ready?channels=01_Citadel")
    authenticated_response = client.get(
        "/api/v1/ready?channels=01_Citadel",
        headers={"Authorization": "Bearer test-token"},
    )

    assert unauthenticated_response.status_code == 401
    assert authenticated_response.status_code == 200
    assert authenticated_response.json() == {
        "items": [
            {
                "id": "item-1",
                "channel_id": "01_Citadel",
                "filename": "item-1.mp4",
                "download_url": "https://example.test/api/v1/download/item-1",
                "sha256": hashlib.sha256(media_bytes).hexdigest(),
            }
        ]
    }


def test_ready_endpoint_hashes_media_without_reading_entire_file(
    tmp_path: Path,
    monkeypatch,
):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"
    media_bytes = b"ready mp4 bytes"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(media_bytes)
    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1-source.mp4",
    )
    store.mark_converting("item-1")
    store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
    )
    client = TestClient(create_app(settings, store))

    def fail_read_bytes(self):
        raise AssertionError("ready endpoint must not load whole media files")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

    response = client.get(
        "/api/v1/ready?channels=01_Citadel",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["sha256"] == hashlib.sha256(media_bytes).hexdigest()


def test_download_does_not_deliver_ack_does(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"
    media_bytes = b"converted media bytes"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(media_bytes)
    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1-source.mp4",
    )
    store.mark_converting("item-1")
    store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
    )
    client = TestClient(create_app(settings, store))

    download_response = client.get(
        "/api/v1/download/item-1",
        headers={"Authorization": "Bearer test-token"},
    )

    assert download_response.status_code == 200
    assert download_response.content == media_bytes
    assert store.items["item-1"].status == "pending"

    ack_response = client.post(
        "/api/v1/ack/item-1",
        headers={"Authorization": "Bearer test-token"},
    )

    assert ack_response.status_code == 204
    assert ack_response.content == b""
    assert store.items["item-1"].status == "archived"
    assert store.acknowledgements["item-1"] == {"status": "delivered"}
    assert store.archive_index["item-1"]["status"] == "archived"


def test_download_and_ack_require_bearer_token(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    client = TestClient(create_app(settings, store))

    download_response = client.get("/api/v1/download/item-1")
    ack_response = client.post("/api/v1/ack/item-1")

    assert download_response.status_code == 401
    assert ack_response.status_code == 401


def test_download_returns_404_for_missing_canceled_and_non_pending_items(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted media bytes")
    store.create_uploaded_item(
        item_id="uploaded-item",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "uploaded-source.mp4",
    )
    store.create_uploaded_item(
        item_id="canceled-item",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "canceled-source.mp4",
    )
    store.mark_converting("canceled-item")
    store.mark_pending(
        "canceled-item",
        converted_path=converted_path,
        channel_id="01_Citadel",
    )
    store.items["canceled-item"].status = "canceled"
    client = TestClient(create_app(settings, store))

    missing_response = client.get(
        "/api/v1/download/missing-item",
        headers={"Authorization": "Bearer test-token"},
    )
    uploaded_response = client.get(
        "/api/v1/download/uploaded-item",
        headers={"Authorization": "Bearer test-token"},
    )
    canceled_response = client.get(
        "/api/v1/download/canceled-item",
        headers={"Authorization": "Bearer test-token"},
    )

    assert missing_response.status_code == 404
    assert uploaded_response.status_code == 404
    assert canceled_response.status_code == 404


def test_ack_is_idempotent_for_archived_items(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted media bytes")
    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1-source.mp4",
    )
    store.mark_converting("item-1")
    store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
    )
    store.ack_item("item-1")
    client = TestClient(create_app(settings, store))

    ack_response = client.post(
        "/api/v1/ack/item-1",
        headers={"Authorization": "Bearer test-token"},
    )

    assert ack_response.status_code == 204
    assert ack_response.content == b""
    assert store.items["item-1"].status == "archived"
