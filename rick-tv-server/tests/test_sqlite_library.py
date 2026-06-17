from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from rick_tv_server.channels import ChannelRegistryStore
from rick_tv_server.config import ServerSettings
from rick_tv_server.state import DeliveryStateStore
from rick_tv_server.uploads import UploadProcessor


def make_settings(tmp_path: Path) -> ServerSettings:
    return ServerSettings(
        media_dir=tmp_path / "media",
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        api_token="test-token",
        public_base_url="https://example.test",
        channels_path=tmp_path / "config" / "channels.yml",
    )


def test_state_store_creates_sqlite_schema_at_default_db_path(tmp_path: Path):
    settings = make_settings(tmp_path)

    DeliveryStateStore(settings)

    db_path = settings.state_dir / "rick-tv.sqlite3"
    assert db_path.exists()
    with sqlite3.connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            )
        }

    assert {"channels", "media_items", "user_channel_preferences"} <= table_names


def test_channel_registry_is_backed_by_sqlite_and_dumps_json_payload(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)

    channel_store.add_channel("01_Citadel", "Citadel")
    channel_store.add_channel("02_Test_Channel", "Test Channel")
    channel_store.rename_channel("02_Test_Channel", "Test Archive")

    reloaded = ChannelRegistryStore(settings)
    assert reloaded.load().channels == {
        "01_Citadel": {"display_name": "Citadel"},
        "02_Test_Channel": {"display_name": "Test Archive"},
    }
    assert reloaded.dump_payload() == {
        "channels": {
            "01_Citadel": {"display_name": "Citadel"},
            "02_Test_Channel": {"display_name": "Test Archive"},
        }
    }


def test_legacy_json_and_yml_migrate_to_sqlite_library_and_are_deleted(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    legacy_original = settings.media_dir / "seed" / "01_Citadel" / "episode.mov"
    legacy_converted = settings.media_dir / "seed" / "01_Citadel" / "episode.mp4"
    legacy_original.parent.mkdir(parents=True)
    legacy_original.write_bytes(b"original bytes")
    legacy_converted.write_bytes(b"converted bytes")
    settings.config_dir.mkdir(parents=True)
    settings.channels_path.write_text(
        """
channels:
  01_Citadel:
    display_name: Citadel
""".lstrip(),
        encoding="utf-8",
    )
    settings.state_dir.mkdir(parents=True)
    queue_path = settings.state_dir / "queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "items": {
                    "legacy-item": {
                        "item_id": "legacy-item",
                        "user_id": "seed",
                        "status": "archived",
                        "original_path": str(legacy_original),
                        "converted_path": str(legacy_converted),
                        "source_message_id": None,
                        "channel_id": "01_Citadel",
                        "filename": "episode.mp4",
                        "sha256": "stale",
                        "failure_message": None,
                    }
                },
                "last_channel_by_user": {
                    "104065396": "01_Citadel",
                    "seed": "01_Citadel",
                },
                "acknowledgements": {"legacy-item": {"status": "delivered"}},
                "archive_index": {"legacy-item": {"status": "archived"}},
                "archive_delete_requests": {},
            }
        ),
        encoding="utf-8",
    )

    state_store = DeliveryStateStore(settings)
    channel_store = ChannelRegistryStore(settings)
    item = state_store.items["legacy-item"]

    assert item.status == "available"
    assert item.channel_id == "01_Citadel"
    assert item.filename == "episode.mp4"
    assert item.original_path == (
        settings.media_dir
        / "library"
        / "01_Citadel"
        / "legacy-item"
        / "original"
        / "episode.mov"
    )
    assert item.converted_path == (
        settings.media_dir
        / "library"
        / "01_Citadel"
        / "legacy-item"
        / "converted"
        / "episode.mp4"
    )
    assert item.original_path.read_bytes() == b"original bytes"
    assert item.converted_path.read_bytes() == b"converted bytes"
    assert item.sha256 == hashlib.sha256(b"converted bytes").hexdigest()
    assert state_store.last_channel_by_user == {"104065396": "01_Citadel"}
    assert channel_store.load().channels == {
        "01_Citadel": {"display_name": "Citadel"}
    }
    assert not queue_path.exists()
    assert not settings.channels_path.exists()

    with sqlite3.connect(settings.state_dir / "rick-tv.sqlite3") as connection:
        columns = {
            row[1]
            for row in connection.execute("pragma table_info(media_items)")
        }
    assert "source_message_id" not in columns
    assert "user_id" not in columns


def test_upload_processor_writes_readable_library_paths_without_user_id(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    state_store = DeliveryStateStore(settings)
    source_path = tmp_path / "incoming" / "My Episode!.mov"
    source_path.parent.mkdir()
    source_path.write_bytes(b"uploaded source bytes")
    converted_bytes = b"ready mp4 bytes"

    def convert_success(input_path: Path, output_path: Path):
        assert input_path == (
            settings.media_dir
            / "library"
            / "01_Citadel"
            / "abcdef123456"
            / "original"
            / "My_Episode.mov"
        )
        assert output_path == (
            settings.media_dir
            / "library"
            / "01_Citadel"
            / "abcdef123456"
            / "converted"
            / "My_Episode--abcdef12.mp4"
        )
        output_path.write_bytes(converted_bytes)

    processor = UploadProcessor(
        settings=settings,
        state_store=state_store,
        converter=convert_success,
        validator=lambda _path: True,
        item_id_factory=lambda: "abcdef123456",
    )

    item = processor.process_upload(
        channel_id="01_Citadel",
        source_path=source_path,
        original_filename="My Episode!.mov",
    )

    assert item.status == "pending_delivery"
    assert item.filename == "My_Episode--abcdef12.mp4"
    assert item.original_path.read_bytes() == b"uploaded source bytes"
    assert item.converted_path.read_bytes() == converted_bytes
    assert item.sha256 == hashlib.sha256(converted_bytes).hexdigest()
