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


def test_health_endpoint_is_public(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    client = TestClient(create_app(settings, store))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
        ],
        "deletions": [],
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
    store.cancel_pending_item("canceled-item")
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


def test_download_and_ack_see_items_created_by_separate_store_instance(tmp_path: Path):
    settings = make_settings(tmp_path)
    api_store = DeliveryStateStore(settings)
    bot_store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"
    media_bytes = b"converted media bytes"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(media_bytes)
    bot_store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1-source.mp4",
    )
    bot_store.mark_converting("item-1")
    bot_store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
    )
    client = TestClient(create_app(settings, api_store))

    download_response = client.get(
        "/api/v1/download/item-1",
        headers={"Authorization": "Bearer test-token"},
    )
    ack_response = client.post(
        "/api/v1/ack/item-1",
        headers={"Authorization": "Bearer test-token"},
    )
    reloaded = DeliveryStateStore(settings)

    assert download_response.status_code == 200
    assert download_response.content == media_bytes
    assert ack_response.status_code == 204
    assert reloaded.items["item-1"].status == "archived"


def test_channels_yml_requires_bearer_token_and_returns_registry(tmp_path: Path):
    settings = make_settings(tmp_path)
    settings.config_dir.mkdir(parents=True)
    channels_path = settings.config_dir / "channels.yml"
    channels_path.write_text(
        """
channels:
  01_Citadel:
    display_name: Citadel TV
""".lstrip(),
        encoding="utf-8",
    )
    store = DeliveryStateStore(settings)
    client = TestClient(create_app(settings, store))

    unauthenticated_response = client.get("/api/v1/channels.yml")
    authenticated_response = client.get(
        "/api/v1/channels.yml",
        headers={"Authorization": "Bearer test-token"},
    )

    assert unauthenticated_response.status_code == 401
    assert authenticated_response.status_code == 200
    assert authenticated_response.headers["content-type"].startswith("application/yaml")
    assert authenticated_response.text == channels_path.read_text(encoding="utf-8")


def test_channels_yml_missing_registry_returns_empty_channels_document(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    client = TestClient(create_app(settings, store))

    response = client.get(
        "/api/v1/channels.yml",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.text == "channels: {}\n"


def test_ready_endpoint_returns_device_deletions_for_deleted_server_side_items(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    pending_path = settings.media_dir / "converted" / "pending.mp4"
    pending_path.parent.mkdir(parents=True)
    pending_bytes = b"pending media bytes"
    pending_path.write_bytes(pending_bytes)
    pending_original_path = settings.media_dir / "uploads" / "pending.mov"
    pending_original_path.parent.mkdir(parents=True)
    pending_original_path.write_bytes(b"pending original bytes")
    deleted_path = settings.media_dir / "converted" / "deleted.mp4"
    deleted_path.write_bytes(b"deleted media bytes")
    deleted_original_path = settings.media_dir / "uploads" / "deleted.mov"
    deleted_original_path.write_bytes(b"deleted original bytes")

    store.create_uploaded_item(
        item_id="pending-item",
        user_id="user-1",
        original_path=pending_original_path,
    )
    store.mark_converting("pending-item")
    store.mark_pending(
        "pending-item",
        converted_path=pending_path,
        channel_id="01_Citadel",
        filename="pending.mp4",
    )
    store.create_uploaded_item(
        item_id="deleted-item",
        user_id="user-1",
        original_path=deleted_original_path,
    )
    store.mark_converting("deleted-item")
    store.mark_pending(
        "deleted-item",
        converted_path=deleted_path,
        channel_id="01_Citadel",
        filename="deleted.mp4",
    )
    store.ack_item("deleted-item")
    store.delete_item_from_channel("deleted-item")
    client = TestClient(create_app(settings, store))

    response = client.get(
        "/api/v1/ready?channels=01_Citadel",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "pending-item",
                "channel_id": "01_Citadel",
                "filename": "pending.mp4",
                "download_url": "https://example.test/api/v1/download/pending-item",
                "sha256": hashlib.sha256(pending_bytes).hexdigest(),
            }
        ],
        "deletions": [
            {
                "id": "deleted-item",
                "channel_id": "01_Citadel",
                "filename": "deleted.mp4",
            }
        ],
    }


def test_delete_ack_requires_bearer_token_and_completes_device_deletion(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    original_path = settings.media_dir / "uploads" / "deleted.mov"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"deleted original bytes")
    converted_path = settings.media_dir / "converted" / "deleted.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"deleted media bytes")
    store.create_uploaded_item(
        item_id="deleted-item",
        user_id="user-1",
        original_path=original_path,
    )
    store.mark_converting("deleted-item")
    store.mark_pending(
        "deleted-item",
        converted_path=converted_path,
        channel_id="01_Citadel",
        filename="deleted.mp4",
    )
    store.ack_item("deleted-item")
    store.delete_item_from_channel("deleted-item")
    client = TestClient(create_app(settings, store))

    unauthenticated_response = client.post("/api/v1/delete-ack/deleted-item")
    authenticated_response = client.post(
        "/api/v1/delete-ack/deleted-item",
        headers={"Authorization": "Bearer test-token"},
    )
    reloaded = DeliveryStateStore(settings)

    assert unauthenticated_response.status_code == 401
    assert authenticated_response.status_code == 204
    assert authenticated_response.content == b""
    assert reloaded.items["deleted-item"].status == "deleted_from_library"
    assert reloaded.device_delete_items_for_channels(["01_Citadel"]) == []
