from pathlib import Path
import hashlib
import pytest

from rick_tv_server.config import ServerSettings
from rick_tv_server.state import DeliveryStateStore
from rick_tv_server.uploads import UploadProcessingError, UploadProcessor


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
    original_path = (
        settings.media_dir
        / "library"
        / "01_Citadel"
        / "item-1"
        / "original"
        / "citadel.mov"
    )
    converted_path = (
        settings.media_dir
        / "library"
        / "01_Citadel"
        / "item-1"
        / "converted"
        / "citadel--item-1.mp4"
    )

    def convert_success(input_path: Path, output_path: Path):
        assert input_path == original_path
        assert output_path == converted_path
        output_path.write_bytes(converted_bytes)

    processor = UploadProcessor(
        settings=settings,
        state_store=store,
        converter=convert_success,
        validator=lambda _path: True,
        item_id_factory=lambda: "item-1",
    )

    pending = processor.process_upload(
        channel_id="01_Citadel",
        source_path=source_path,
        original_filename="citadel.mov",
    )

    assert store.statuses == ["uploaded", "converting", "pending_delivery"]
    assert pending.status == "pending_delivery"
    assert pending.original_path == original_path
    assert pending.original_path.read_bytes() == b"uploaded source bytes"
    assert pending.converted_path == converted_path
    assert pending.converted_path.read_bytes() == converted_bytes
    assert pending.filename == "citadel--item-1.mp4"
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
        validator=lambda _path: True,
        item_id_factory=lambda: "item-1",
    )
    processor.process_upload(
        channel_id="01_Citadel",
        source_path=first_source,
        original_filename="first.mov",
    )

    with pytest.raises(ValueError, match="already exists"):
        processor.process_upload(
            channel_id="Garage",
            source_path=duplicate_source,
            original_filename="duplicate.mov",
        )

    uploaded_path = (
        settings.media_dir
        / "library"
        / "01_Citadel"
        / "item-1"
        / "original"
        / "first.mov"
    )
    assert uploaded_path.read_bytes() == b"original uploaded source"


def test_failed_upload_state_persists_message_and_is_not_ready(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    original_path = settings.media_dir / "uploaded" / "item-1.mov"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"source bytes")

    store.create_uploaded_item(
        item_id="item-1",
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


def test_upload_processor_validates_converted_media_before_pending(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = RecordingStateStore(settings)
    source_path = tmp_path / "incoming" / "citadel.mov"
    source_path.parent.mkdir()
    source_path.write_bytes(b"uploaded source bytes")
    validator_calls = []

    def convert_success(_input_path: Path, output_path: Path):
        output_path.write_bytes(b"ready mp4 bytes")

    def validate_success(path: Path) -> bool:
        validator_calls.append(path)
        return True

    processor = UploadProcessor(
        settings=settings,
        state_store=store,
        converter=convert_success,
        validator=validate_success,
        item_id_factory=lambda: "item-1",
    )

    pending = processor.process_upload(
        channel_id="01_Citadel",
        source_path=source_path,
        original_filename="citadel.mov",
    )

    assert validator_calls == [
        settings.media_dir
        / "library"
        / "01_Citadel"
        / "item-1"
        / "converted"
        / "citadel--item-1.mp4"
    ]
    assert store.statuses == ["uploaded", "converting", "pending_delivery"]
    assert pending.status == "pending_delivery"


def test_upload_processor_retries_conversion_once_after_validation_failure(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    source_path = tmp_path / "incoming" / "citadel.mov"
    source_path.parent.mkdir()
    source_path.write_bytes(b"uploaded source bytes")
    converter_calls = []
    validation_results = iter([False, True])

    def convert_first(_input_path: Path, output_path: Path):
        converter_calls.append(("first", output_path))
        output_path.write_bytes(b"first converted bytes")

    def convert_retry(_input_path: Path, output_path: Path):
        converter_calls.append(("retry", output_path))
        output_path.write_bytes(b"retry converted bytes")

    def validate_next(_path: Path) -> bool:
        return next(validation_results)

    processor = UploadProcessor(
        settings=settings,
        state_store=store,
        converter=convert_first,
        retry_converter=convert_retry,
        validator=validate_next,
        item_id_factory=lambda: "item-1",
    )

    pending = processor.process_upload(
        channel_id="01_Citadel",
        source_path=source_path,
        original_filename="citadel.mov",
    )

    converted_path = (
        settings.media_dir
        / "library"
        / "01_Citadel"
        / "item-1"
        / "converted"
        / "citadel--item-1.mp4"
    )
    assert converter_calls == [("first", converted_path), ("retry", converted_path)]
    assert converted_path.read_bytes() == b"retry converted bytes"
    assert pending.status == "pending_delivery"
    assert pending.converted_path == converted_path


def test_upload_processor_marks_failed_when_retry_validation_fails(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = DeliveryStateStore(settings)
    source_path = tmp_path / "incoming" / "citadel.mov"
    source_path.parent.mkdir()
    source_path.write_bytes(b"uploaded source bytes")

    def convert_invalid(_input_path: Path, output_path: Path):
        output_path.write_bytes(b"invalid converted bytes")

    processor = UploadProcessor(
        settings=settings,
        state_store=store,
        converter=convert_invalid,
        retry_converter=convert_invalid,
        validator=lambda _path: False,
        item_id_factory=lambda: "item-1",
    )

    with pytest.raises(UploadProcessingError, match="prepared for Rick TV playback"):
        processor.process_upload(
            channel_id="01_Citadel",
            source_path=source_path,
            original_filename="citadel.mov",
        )

    item = DeliveryStateStore(settings).items["item-1"]
    assert item.status == "failed"
    assert item.channel_id == "01_Citadel"
    assert item.failure_message == "Video could not be prepared for Rick TV playback."
