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
        original_path=tmp_path / "media" / "uploads" / "item-1.mp4",
    )
    assert item.status == "uploaded"

    converting = store.mark_converting("item-1")
    assert converting.status == "converting"

    pending = store.mark_pending(
        "item-1",
        converted_path=tmp_path / "media" / "converted" / "item-1.mp4",
        channel_id="channel-1",
    )
    assert pending.status == "pending_delivery"

    reloaded = DeliveryStateStore(settings)

    assert settings.state_dir.joinpath("rick-tv.sqlite3").exists()
    assert reloaded.items["item-1"].status == "pending_delivery"
    assert reloaded.items["item-1"].original_path == tmp_path / "media" / "uploads" / "item-1.mp4"
    assert reloaded.items["item-1"].converted_path == tmp_path / "media" / "converted" / "item-1.mp4"
    assert reloaded.last_channel_by_user == {}


def test_pending_remains_ready_until_ack(tmp_path: Path):
    store = DeliveryStateStore(make_settings(tmp_path))
    store.create_uploaded_item(
        item_id="item-1",
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
    assert delivered.status == "available"
    assert store.items["item-1"].status == "available"
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
        original_path=tmp_path / "media" / "uploads" / "item-1.mp4",
    )

    with pytest.raises(ValueError, match="item-1"):
        store.create_uploaded_item(
            item_id="item-1",
            original_path=tmp_path / "media" / "uploads" / "replacement.mp4",
        )

    assert store.items["item-1"].original_path == tmp_path / "media" / "uploads" / "item-1.mp4"


def test_mark_converting_requires_uploaded_item(tmp_path: Path):
    store = DeliveryStateStore(make_settings(tmp_path))
    store.create_uploaded_item(
        item_id="item-1",
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
    assert ready_response.json() == {"items": [], "deletions": []}
    assert download_response.status_code == 404


def test_store_instance_sees_pending_items_created_by_separate_instance(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    api_store = DeliveryStateStore(settings)
    bot_store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"

    bot_store.create_uploaded_item(
        item_id="item-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mov",
    )
    bot_store.mark_converting("item-1")
    bot_store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
    )

    assert [item.item_id for item in api_store.list_pending_items()] == ["item-1"]


def test_sequential_store_instances_preserve_both_updates(tmp_path: Path):
    settings = make_settings(tmp_path)
    first_store = DeliveryStateStore(settings)
    second_store = DeliveryStateStore(settings)

    first_store.create_uploaded_item(
        item_id="item-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mov",
    )
    second_store.create_uploaded_item(
        item_id="item-2",
        original_path=tmp_path / "media" / "uploads" / "item-2.mov",
    )

    reloaded = DeliveryStateStore(settings)
    assert sorted(reloaded.items) == ["item-1", "item-2"]


def test_restore_all_available_items_requeues_available_items_without_duplicate_files(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    converted_paths = {}
    for item_id in ("item-1", "item-2", "item-3"):
        original_path = tmp_path / "media" / "uploads" / f"{item_id}.mov"
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_bytes(f"original {item_id}".encode())
        converted_path = tmp_path / "media" / "converted" / f"{item_id}.mp4"
        converted_path.parent.mkdir(parents=True, exist_ok=True)
        converted_path.write_bytes(f"converted {item_id}".encode())
        converted_paths[item_id] = converted_path
        store.create_uploaded_item(
            item_id=item_id,
            original_path=original_path,
        )
        store.mark_converting(item_id)
        store.mark_pending(
            item_id,
            converted_path=converted_path,
            channel_id="01_Citadel",
        )
        store.ack_item(item_id)
    store.delete_item_from_channel("item-3")
    store.ack_device_delete("item-3")

    restored = store.restore_all_available()
    reloaded = DeliveryStateStore(settings)

    assert [item.item_id for item in restored] == ["item-1", "item-2"]
    assert reloaded.items["item-1"].status == "pending_delivery"
    assert reloaded.items["item-2"].status == "pending_delivery"
    assert reloaded.items["item-3"].status == "deleted"
    assert [converted_paths[item_id].exists() for item_id in ("item-1", "item-2")] == [
        True,
        True,
    ]
    assert not converted_paths["item-3"].exists()


def test_list_active_items_for_channel_returns_pending_and_available_media(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    for item_id, channel_id in [
        ("pending-1", "01_Citadel"),
        ("available-1", "01_Citadel"),
        ("other-channel", "02_Interdimensional_Cable"),
        ("canceled-1", "01_Citadel"),
    ]:
        original_path = settings.media_dir / "uploads" / f"{item_id}.mov"
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_bytes(f"original {item_id}".encode())
        converted_path = settings.media_dir / "converted" / f"{item_id}.mp4"
        converted_path.parent.mkdir(parents=True, exist_ok=True)
        converted_path.write_bytes(f"converted {item_id}".encode())
        store.create_uploaded_item(
            item_id=item_id,
            original_path=original_path,
        )
        store.mark_converting(item_id)
        store.mark_pending(
            item_id,
            converted_path=converted_path,
            channel_id=channel_id,
            filename=f"{item_id}.mp4",
        )
    store.ack_item("available-1")
    store.cancel_pending_item("canceled-1")

    active_items = store.list_active_items_for_channel("01_Citadel")

    assert {item.item_id for item in active_items} == {"pending-1", "available-1"}


def test_delete_item_from_channel_removes_server_files_and_waits_for_device_ack(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    original_path = settings.media_dir / "uploads" / "item-1.mov"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"original media bytes")
    converted_path = settings.media_dir / "converted" / "episode.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted media bytes")
    store.create_uploaded_item(
        item_id="item-1",
        original_path=original_path,
    )
    store.mark_converting("item-1")
    store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
        filename="episode.mp4",
    )
    store.ack_item("item-1")

    deleted = store.delete_item_from_channel("item-1")
    reloaded_after_delete = DeliveryStateStore(settings)

    assert deleted.status == "pending_device_delete"
    assert reloaded_after_delete.items["item-1"].status == "pending_device_delete"
    assert not original_path.exists()
    assert not converted_path.exists()
    assert store.list_active_items_for_channel("01_Citadel") == []
    device_deletions = reloaded_after_delete.device_delete_items_for_channels(
        ["01_Citadel"]
    )
    assert [(item.item_id, item.channel_id, item.filename) for item in device_deletions] == [
        ("item-1", "01_Citadel", "episode.mp4")
    ]

    acked = reloaded_after_delete.ack_device_delete("item-1")
    reloaded_after_ack = DeliveryStateStore(settings)

    assert acked.status == "deleted"
    assert reloaded_after_ack.items["item-1"].status == "deleted"
    assert reloaded_after_ack.device_delete_items_for_channels(["01_Citadel"]) == []


def test_delete_item_from_channel_restore_files_when_persist_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    original_path = settings.media_dir / "uploads" / "item-1.mov"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"original media bytes")
    converted_path = settings.media_dir / "converted" / "episode.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted media bytes")
    store.create_uploaded_item(
        item_id="item-1",
        original_path=original_path,
    )
    store.mark_converting("item-1")
    store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
        filename="episode.mp4",
    )
    store.ack_item("item-1")

    def fail_update_status(_item_id: str, _status: str) -> None:
        raise RuntimeError("status update failed")

    monkeypatch.setattr(store, "_update_item_status", fail_update_status)

    with pytest.raises(RuntimeError, match="status update failed"):
        store.delete_item_from_channel("item-1")

    reloaded = DeliveryStateStore(settings)
    assert store.items["item-1"].status == "available"
    assert reloaded.items["item-1"].status == "available"
    assert original_path.exists()
    assert converted_path.exists()
