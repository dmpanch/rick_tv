from pathlib import Path

import pytest

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
