from pathlib import Path
import hashlib
import pytest

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
    )


class RecordingStateStore(DeliveryStateStore):
    def __init__(self, settings: ServerSettings):
        self.statuses: list[str] = []
        super().__init__(settings)

    def create_uploaded_item(self, **kwargs):
        item = super().create_uploaded_item(**kwargs)
        self.statuses.append(item.status)
        return item

    def mark_converting(self, item_id: str):
        item = super().mark_converting(item_id)
        self.statuses.append(item.status)
        return item

    def mark_pending(self, item_id: str, **kwargs):
        item = super().mark_pending(item_id, **kwargs)
        self.statuses.append(item.status)
        return item


def test_upload_processor_stores_converted_media_as_pending(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = RecordingStateStore(settings)
    source_path = tmp_path / "incoming" / "citadel.mov"
    source_path.parent.mkdir()
    source_path.write_bytes(b"uploaded source bytes")
    converted_bytes = b"ready mp4 bytes"

    def convert_success(input_path: Path, output_path: Path):
        assert input_path == settings.media_dir / "uploaded" / "item-1.mov"
        assert output_path == settings.media_dir / "converted" / "item-1.mp4"
        output_path.write_bytes(converted_bytes)

    processor = UploadProcessor(
        settings=settings,
        state_store=store,
        converter=convert_success,
        item_id_factory=lambda: "item-1",
    )

    pending = processor.process_upload(
        user_id="user-1",
        channel_id="01_Citadel",
        source_path=source_path,
        original_filename="citadel.mov",
    )

    assert store.statuses == ["uploaded", "converting", "pending"]
    assert pending.status == "pending"
    assert pending.original_path == settings.media_dir / "uploaded" / "item-1.mov"
    assert pending.original_path.read_bytes() == b"uploaded source bytes"
    assert pending.converted_path == settings.media_dir / "converted" / "item-1.mp4"
    assert pending.converted_path.read_bytes() == converted_bytes
    assert pending.filename == "item-1.mp4"
    assert pending.channel_id == "01_Citadel"
    assert pending.sha256 == hashlib.sha256(converted_bytes).hexdigest()


def test_duplicate_upload_id_does_not_replace_existing_uploaded_file(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    first_source = tmp_path / "incoming" / "first.mov"
    duplicate_source = tmp_path / "incoming" / "duplicate.mov"
    first_source.parent.mkdir()
    first_source.write_bytes(b"original uploaded source")
    duplicate_source.write_bytes(b"duplicate uploaded source")

    def convert_success(_input_path: Path, output_path: Path):
        output_path.write_bytes(b"ready mp4 bytes")

    processor = UploadProcessor(
        settings=settings,
        state_store=store,
        converter=convert_success,
        item_id_factory=lambda: "item-1",
    )
    processor.process_upload(
        user_id="user-1",
        channel_id="01_Citadel",
        source_path=first_source,
        original_filename="first.mov",
    )

    with pytest.raises(ValueError, match="already exists"):
        processor.process_upload(
            user_id="user-2",
            channel_id="Garage",
            source_path=duplicate_source,
            original_filename="duplicate.mov",
        )

    uploaded_path = settings.media_dir / "uploaded" / "item-1.mov"
    assert uploaded_path.read_bytes() == b"original uploaded source"


def test_failed_upload_state_persists_message_and_is_not_ready(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    original_path = settings.media_dir / "uploaded" / "item-1.mov"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"source bytes")

    store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=original_path,
    )
    store.mark_converting("item-1")

    failed = store.mark_failed(
        "item-1",
        message="Video could not be prepared for Rick TV playback.",
        channel_id="01_Citadel",
    )

    assert failed.status == "failed"
    assert failed.failure_message == "Video could not be prepared for Rick TV playback."
    assert failed.channel_id == "01_Citadel"
    assert store.ready_items_for_channels(["01_Citadel"]) == []
    assert store.has_active_media_for_channel("01_Citadel") is False

    reloaded = DeliveryStateStore(settings)
    assert reloaded.items["item-1"].status == "failed"
    assert (
        reloaded.items["item-1"].failure_message
        == "Video could not be prepared for Rick TV playback."
    )
