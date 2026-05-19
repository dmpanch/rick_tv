from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from rick_tv_pi.channels import Channel
from rick_tv_pi.config import PiSettings
import rick_tv_pi.poller as poller_module
from rick_tv_pi.poller import Poller
from rick_tv_server.api import create_app
from rick_tv_server.config import ServerSettings
from rick_tv_server.state import DeliveryStateStore


def test_pi_poll_downloads_pending_server_media_and_archives_ack(
    tmp_path: Path,
    monkeypatch,
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

    monkeypatch.setattr(
        poller_module,
        "validate_ready_profile",
        lambda path: True,
        raising=False,
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
