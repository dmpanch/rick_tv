from pathlib import Path

import pytest
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


def test_state_persists_delivery_lifecycle(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)

    item = store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mp4",
        source_message_id=123,
    )
    assert item.status == "uploaded"

    converting = store.mark_converting("item-1")
    assert converting.status == "converting"

    pending = store.mark_pending(
        "item-1",
        converted_path=tmp_path / "media" / "converted" / "item-1.mp4",
        channel_id="channel-1",
    )
    assert pending.status == "pending"

    reloaded = DeliveryStateStore(settings)

    assert settings.state_dir.joinpath("queue.json").exists()
    assert reloaded.items["item-1"].status == "pending"
    assert reloaded.items["item-1"].user_id == "user-1"
    assert reloaded.items["item-1"].original_path == tmp_path / "media" / "uploads" / "item-1.mp4"
    assert reloaded.items["item-1"].converted_path == tmp_path / "media" / "converted" / "item-1.mp4"
    assert reloaded.last_channel_by_user == {"user-1": "channel-1"}
    assert reloaded.acknowledgements == {}
    assert reloaded.archive_index == {}


def test_pending_remains_ready_until_ack(tmp_path: Path):
    store = DeliveryStateStore(make_settings(tmp_path))
    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mp4",
    )
    store.mark_converting("item-1")
    store.mark_pending(
        "item-1",
        converted_path=tmp_path / "media" / "converted" / "item-1.mp4",
        channel_id="01_Citadel",
    )

    first_ready = store.ready_items_for_channels(["01_Citadel"])
    second_ready = store.ready_items_for_channels(["01_Citadel"])

    assert [item.item_id for item in first_ready] == ["item-1"]
    assert [item.item_id for item in second_ready] == ["item-1"]

    delivered = store.ack_item("item-1")
    assert delivered.status == "delivered"
    assert store.items["item-1"].status == "archived"
    assert store.acknowledgements["item-1"] == {"status": "delivered"}
    assert store.archive_index["item-1"] == {
        "status": "archived",
        "channel_id": "01_Citadel",
        "user_id": "user-1",
    }
    assert store.ready_items_for_channels(["01_Citadel"]) == []


def test_remember_user_channel_persists_last_channel(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)

    store.remember_user_channel("user-1", "Garage")

    reloaded = DeliveryStateStore(settings)
    assert reloaded.last_channel_by_user == {"user-1": "Garage"}


def test_create_uploaded_item_rejects_duplicate_item_id(tmp_path: Path):
    store = DeliveryStateStore(make_settings(tmp_path))
    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mp4",
    )

    with pytest.raises(ValueError, match="item-1"):
        store.create_uploaded_item(
            item_id="item-1",
            user_id="user-2",
            original_path=tmp_path / "media" / "uploads" / "replacement.mp4",
        )

    assert store.items["item-1"].user_id == "user-1"


def test_mark_converting_requires_uploaded_item(tmp_path: Path):
    store = DeliveryStateStore(make_settings(tmp_path))
    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mp4",
    )
    store.mark_converting("item-1")

    with pytest.raises(ValueError, match="uploaded"):
        store.mark_converting("item-1")

    assert store.items["item-1"].status == "converting"


def test_mark_pending_requires_converting_item(tmp_path: Path):
    store = DeliveryStateStore(make_settings(tmp_path))
    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mp4",
    )

    with pytest.raises(ValueError, match="converting"):
        store.mark_pending(
            "item-1",
            converted_path=tmp_path / "media" / "converted" / "item-1.mp4",
            channel_id="channel-1",
        )

    assert store.items["item-1"].status == "uploaded"
    assert store.items["item-1"].converted_path is None
    assert store.last_channel_by_user == {}


def test_canceled_pending_is_not_ready(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted media bytes")
    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mov",
    )
    store.mark_converting("item-1")
    store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
    )
    client = TestClient(create_app(settings, store))

    canceled = store.cancel_pending_item("item-1")

    assert canceled.status == "canceled"
    assert converted_path.exists()
    assert store.ready_items_for_channels(["01_Citadel"]) == []
    ready_response = client.get(
        "/api/v1/ready?channels=01_Citadel",
        headers={"Authorization": "Bearer test-token"},
    )
    download_response = client.get(
        "/api/v1/download/item-1",
        headers={"Authorization": "Bearer test-token"},
    )
    assert ready_response.status_code == 200
    assert ready_response.json() == {"items": []}
    assert download_response.status_code == 404


def test_confirm_archive_delete_is_server_side_only(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted media bytes")
    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mov",
    )
    store.mark_converting("item-1")
    store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
    )
    store.ack_item("item-1")

    requested = store.request_archive_delete("item-1")

    assert requested.status == "archived"
    assert [item.item_id for item in store.list_archived_items()] == ["item-1"]
    assert converted_path.exists()

    deleted = store.confirm_archive_delete("item-1")
    reloaded = DeliveryStateStore(settings)

    assert deleted.status == "deleted_server_side"
    assert not converted_path.exists()
    assert store.archive_index == {}
    assert store.acknowledgements == {"item-1": {"status": "delivered"}}
    assert reloaded.items["item-1"].status == "deleted_server_side"
    assert reloaded.archive_index == {}
