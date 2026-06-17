from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from rick_tv_pi.channels import Channel
from rick_tv_pi.config import PiSettings
from rick_tv_pi.poller import Poller
from rick_tv_server.api import create_app
from rick_tv_server.config import ServerSettings
from rick_tv_server.state import DeliveryStateStore


def test_pi_poll_downloads_pending_server_media_and_archives_ack(
    tmp_path: Path,
):
    api_token = "contract-token"
    item_id = "contract-item-1"
    channel_id = "01_Citadel"
    filename = "citadel-loop.mp4"
    media_bytes = b"converted mp4 bytes"

    server_settings = ServerSettings(
        media_dir=tmp_path / "server-media",
        config_dir=tmp_path / "server-config",
        state_dir=tmp_path / "server-state",
        api_token=api_token,
        public_base_url="https://server.example",
    )
    converted_path = server_settings.media_dir / "converted" / filename
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(media_bytes)
    original_path = server_settings.media_dir / "uploads" / "source.mp4"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"source bytes")

    store = DeliveryStateStore(server_settings)
    store.create_uploaded_item(
        item_id=item_id,
        user_id="user-1",
        original_path=original_path,
    )
    store.mark_converting(item_id)
    store.mark_pending(
        item_id,
        converted_path=converted_path,
        channel_id=channel_id,
    )

    pi_media_root = tmp_path / "pi-media"
    channel = Channel(
        id=channel_id,
        number=1,
        display_name="Citadel",
        path=pi_media_root / channel_id,
    )
    pi_settings = PiSettings(
        server_base_url="https://server.example",
        api_token=api_token,
        media_root=pi_media_root,
    )

    app = create_app(server_settings, store)
    client = TestClient(app, base_url="https://server.example")

    Poller(pi_settings, client).poll_once([channel])

    delivered_path = pi_media_root / channel_id / filename
    assert delivered_path.exists()
    assert delivered_path.read_bytes() == media_bytes

    reloaded_store = DeliveryStateStore(server_settings)
    assert reloaded_store.items[item_id].status == "archived"
    assert reloaded_store.archive_index[item_id]["status"] == "archived"


def test_registry_channel_first_delivery_reaches_empty_pi_media_root(
    tmp_path: Path,
):
    api_token = "contract-token"
    item_id = "contract-item-1"
    channel_id = "01_Citadel"
    filename = "citadel-loop.mp4"
    media_bytes = b"converted mp4 bytes"

    server_settings = ServerSettings(
        media_dir=tmp_path / "server-media",
        config_dir=tmp_path / "server-config",
        state_dir=tmp_path / "server-state",
        api_token=api_token,
        public_base_url="https://server.example",
        channels_path=tmp_path / "server-config" / "channels.yml",
    )
    server_settings.channels_path.parent.mkdir(parents=True)
    server_settings.channels_path.write_text(
        """
channels:
  01_Citadel:
    display_name: Citadel TV
""".lstrip(),
        encoding="utf-8",
    )
    converted_path = server_settings.media_dir / "converted" / filename
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(media_bytes)
    original_path = server_settings.media_dir / "uploads" / "source.mp4"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"source bytes")

    store = DeliveryStateStore(server_settings)
    store.create_uploaded_item(
        item_id=item_id,
        user_id="user-1",
        original_path=original_path,
    )
    store.mark_converting(item_id)
    store.mark_pending(
        item_id,
        converted_path=converted_path,
        channel_id=channel_id,
    )

    pi_media_root = tmp_path / "fresh-pi-media"
    pi_settings = PiSettings(
        server_base_url="https://server.example",
        api_token=api_token,
        media_root=pi_media_root,
        metadata_path=tmp_path / "fresh-pi-config" / "channels.yml",
    )

    app = create_app(server_settings, store)
    client = TestClient(app, base_url="https://server.example")

    Poller(pi_settings, client).poll_once([])

    delivered_path = pi_media_root / channel_id / filename
    assert pi_settings.metadata_path.read_text(encoding="utf-8") == (
        server_settings.channels_path.read_text(encoding="utf-8")
    )
    assert delivered_path.read_bytes() == media_bytes
    assert DeliveryStateStore(server_settings).items[item_id].status == "archived"


def test_restore_all_requeues_library_and_delivers_to_fresh_pi(
    tmp_path: Path,
):
    api_token = "contract-token"
    item_id = "contract-item-1"
    channel_id = "01_Citadel"
    filename = "citadel-loop.mp4"
    media_bytes = b"converted mp4 bytes"

    server_settings = ServerSettings(
        media_dir=tmp_path / "server-media",
        config_dir=tmp_path / "server-config",
        state_dir=tmp_path / "server-state",
        api_token=api_token,
        public_base_url="https://server.example",
        channels_path=tmp_path / "server-config" / "channels.yml",
    )
    server_settings.channels_path.parent.mkdir(parents=True)
    server_settings.channels_path.write_text(
        """
channels:
  01_Citadel:
    display_name: Citadel TV
""".lstrip(),
        encoding="utf-8",
    )
    converted_path = server_settings.media_dir / "converted" / filename
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(media_bytes)
    original_path = server_settings.media_dir / "uploads" / "source.mp4"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"source bytes")

    store = DeliveryStateStore(server_settings)
    store.create_uploaded_item(
        item_id=item_id,
        user_id="user-1",
        original_path=original_path,
    )
    store.mark_converting(item_id)
    store.mark_pending(
        item_id,
        converted_path=converted_path,
        channel_id=channel_id,
    )
    store.ack_item(item_id)
    restored = store.restore_all_archived()

    fresh_pi_media_root = tmp_path / "replacement-pi-media"
    pi_settings = PiSettings(
        server_base_url="https://server.example",
        api_token=api_token,
        media_root=fresh_pi_media_root,
        metadata_path=tmp_path / "replacement-pi-config" / "channels.yml",
    )

    app = create_app(server_settings, store)
    client = TestClient(app, base_url="https://server.example")

    Poller(pi_settings, client).poll_once([])

    assert [item.item_id for item in restored] == [item_id]
    assert (fresh_pi_media_root / channel_id / filename).read_bytes() == media_bytes
    assert original_path.exists()
    assert converted_path.exists()
    assert DeliveryStateStore(server_settings).items[item_id].status == "archived"


def test_pi_poll_deletes_server_removed_media_and_acks_delete(
    tmp_path: Path,
):
    api_token = "contract-token"
    item_id = "contract-item-1"
    channel_id = "01_Citadel"
    filename = "citadel-loop.mp4"

    server_settings = ServerSettings(
        media_dir=tmp_path / "server-media",
        config_dir=tmp_path / "server-config",
        state_dir=tmp_path / "server-state",
        api_token=api_token,
        public_base_url="https://server.example",
        channels_path=tmp_path / "server-config" / "channels.yml",
    )
    server_settings.channels_path.parent.mkdir(parents=True)
    server_settings.channels_path.write_text(
        """
channels:
  01_Citadel:
    display_name: Citadel TV
""".lstrip(),
        encoding="utf-8",
    )
    converted_path = server_settings.media_dir / "converted" / filename
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted mp4 bytes")
    original_path = server_settings.media_dir / "uploads" / "source.mp4"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"source bytes")

    store = DeliveryStateStore(server_settings)
    store.create_uploaded_item(
        item_id=item_id,
        user_id="user-1",
        original_path=original_path,
    )
    store.mark_converting(item_id)
    store.mark_pending(
        item_id,
        converted_path=converted_path,
        channel_id=channel_id,
        filename=filename,
    )
    store.ack_item(item_id)
    store.delete_item_from_channel(item_id)

    pi_media_root = tmp_path / "pi-media"
    local_path = pi_media_root / channel_id / filename
    local_path.parent.mkdir(parents=True)
    local_path.write_bytes(b"local pi media")
    pi_settings = PiSettings(
        server_base_url="https://server.example",
        api_token=api_token,
        media_root=pi_media_root,
        metadata_path=tmp_path / "pi-config" / "channels.yml",
    )

    app = create_app(server_settings, store)
    client = TestClient(app, base_url="https://server.example")

    Poller(pi_settings, client).poll_once([])

    assert not original_path.exists()
    assert not converted_path.exists()
    assert not local_path.exists()
    assert DeliveryStateStore(server_settings).items[item_id].status == (
        "deleted_from_library"
    )
