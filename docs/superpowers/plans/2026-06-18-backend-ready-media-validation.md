# Backend Ready Media Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Rick TV media-profile validation to the server, retry conversion once on validation failure, and make the appliance delivery client independent of `ffprobe`.

**Architecture:** The server owns conversion and validation before an item reaches `/api/v1/ready`. `UploadProcessor` converts, validates with server-side `ffprobe`, retries once with a stricter conversion profile, and marks failed uploads with a persisted message. The Pi trusts server-ready media and only verifies delivery integrity through `sha256` before atomic placement and ack.

**Tech Stack:** Python 3.12 server, server-side ffmpeg/ffprobe, Python >=3.7 appliance client, FastAPI, python-telegram-bot, httpx, pytest, SQLite state.

---

## File Structure

- Create `rick-tv-server/src/rick_tv_server/validator.py`: server-side ready MP4 validator using `ffprobe`.
- Create `rick-tv-server/tests/test_validator.py`: unit tests for server validator profile acceptance and rejection.
- Modify `rick-tv-server/src/rick_tv_server/converter.py`: add optional strict conversion flags and a strict profile factory for retry.
- Modify `rick-tv-server/tests/test_converter.py`: verify normal and strict conversion command construction.
- Modify `rick-tv-server/src/rick_tv_server/state.py`: add terminal `failed` status and persisted `failure_message`.
- Modify `rick-tv-server/tests/test_upload_flow.py`: cover failed state and upload validation/retry behavior.
- Modify `rick-tv-server/src/rick_tv_server/uploads.py`: validate converted output, retry once, mark failed, and raise a user-facing upload error.
- Modify `rick-tv-server/src/rick_tv_server/bot.py`: report the upload preparation error text when `UploadProcessor` raises it.
- Modify `rick-tv-server/tests/test_bot.py`: verify Telegram upload failure message can mention media preparation.
- Modify `rick-tv-pi/src/rick_tv_pi/poller.py`: remove appliance-side `validate_ready_profile()` call and `ffprobe` dependency.
- Delete `rick-tv-pi/src/rick_tv_pi/validator.py`: validation no longer belongs to Pi runtime.
- Delete `rick-tv-pi/tests/test_validator.py`: validator tests move to the server.
- Modify `rick-tv-pi/tests/test_poller.py`: rewrite delivery tests around checksum and atomic placement, not media-profile validation.
- Modify `rick-tv-pi/tests/test_end_to_end_contract.py`: remove Pi validator monkeypatches and assert server-ready media delivery.
- Modify `README.md`, `docs/rick-tv-pi.md`, and `docs/rick-tv-server.md`: document server validation and Pi runtime requirements.

## Task 1: Add Server Ready-Profile Validator

**Files:**
- Create: `rick-tv-server/src/rick_tv_server/validator.py`
- Create: `rick-tv-server/tests/test_validator.py`

- [ ] **Step 1: Write failing server validator tests**

Create `rick-tv-server/tests/test_validator.py`:

```python
import json
import subprocess

from rick_tv_server.validator import validate_ready_profile


def _completed_probe(payload):
    return subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )


def _ready_probe(
    *,
    pixel_format="yuv420p",
    width=640,
    height=480,
    video_bit_rate="700000",
    audio_bit_rate="96000",
    format_bit_rate="796000",
):
    return {
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "bit_rate": format_bit_rate,
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "pix_fmt": pixel_format,
                "width": width,
                "height": height,
                "bit_rate": video_bit_rate,
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "bit_rate": audio_bit_rate,
            },
        ],
    }


def test_validate_ready_profile_accepts_target_mp4_h264_aac():
    def runner(*args, **kwargs):
        return _completed_probe(_ready_probe())

    assert validate_ready_profile("episode.mp4", runner=runner) is True


def test_validate_ready_profile_rejects_wrong_pixel_format():
    def runner(*args, **kwargs):
        return _completed_probe(_ready_probe(pixel_format="yuv422p"))

    assert validate_ready_profile("episode.mp4", runner=runner) is False


def test_validate_ready_profile_rejects_non_target_dimensions():
    def runner(*args, **kwargs):
        return _completed_probe(_ready_probe(width=480, height=320))

    assert validate_ready_profile("episode.mp4", runner=runner) is False


def test_validate_ready_profile_rejects_excessive_video_bitrate():
    def runner(*args, **kwargs):
        return _completed_probe(_ready_probe(video_bit_rate="1400000"))

    assert validate_ready_profile("episode.mp4", runner=runner) is False


def test_validate_ready_profile_rejects_missing_video_bitrate():
    payload = _ready_probe()
    del payload["streams"][0]["bit_rate"]

    def runner(*args, **kwargs):
        return _completed_probe(payload)

    assert validate_ready_profile("episode.mp4", runner=runner) is False


def test_validate_ready_profile_rejects_missing_dimensions():
    payload = _ready_probe()
    del payload["streams"][0]["width"]

    def runner(*args, **kwargs):
        return _completed_probe(payload)

    assert validate_ready_profile("episode.mp4", runner=runner) is False


def test_validate_ready_profile_rejects_malformed_dimensions():
    payload = _ready_probe()
    payload["streams"][0]["width"] = "N/A"

    def runner(*args, **kwargs):
        return _completed_probe(payload)

    assert validate_ready_profile("episode.mp4", runner=runner) is False
```

- [ ] **Step 2: Run server validator tests and verify they fail**

Run: `cd rick-tv-server && python -m pytest tests/test_validator.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'rick_tv_server.validator'`.

- [ ] **Step 3: Implement server validator**

Create `rick-tv-server/src/rick_tv_server/validator.py`:

```python
import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ReadyProfile:
    width: int = 640
    height: int = 480
    max_video_bit_rate: int = 800_000
    max_audio_bit_rate: int = 128_000
    video_codec: str = "h264"
    pixel_format: str = "yuv420p"
    audio_codec: str = "aac"


def probe_media(path, runner=subprocess.run):
    result = runner(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=format_name,bit_rate:stream=codec_type,codec_name,pix_fmt,width,height,bit_rate",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def validate_ready_profile(path, profile=ReadyProfile(), runner=subprocess.run):
    try:
        media = probe_media(path, runner=runner)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return False

    format_names = {
        name.strip()
        for name in media.get("format", {}).get("format_name", "").split(",")
    }
    if "mp4" not in format_names:
        return False

    streams = media.get("streams", [])
    video_stream = _first_stream(streams, "video")
    audio_stream = _first_stream(streams, "audio")
    if video_stream is None or audio_stream is None:
        return False

    width = _positive_int(video_stream.get("width"))
    height = _positive_int(video_stream.get("height"))
    if width is None or height is None:
        return False
    video_bit_rate = _positive_int(video_stream.get("bit_rate"))
    audio_bit_rate = _positive_int(audio_stream.get("bit_rate"))
    if video_bit_rate is None or audio_bit_rate is None:
        return False

    return (
        video_stream.get("codec_name") == profile.video_codec
        and video_stream.get("pix_fmt") == profile.pixel_format
        and audio_stream.get("codec_name") == profile.audio_codec
        and width == profile.width
        and height == profile.height
        and video_bit_rate <= profile.max_video_bit_rate
        and audio_bit_rate <= profile.max_audio_bit_rate
    )


def _first_stream(streams, codec_type):
    return next(
        (
            stream
            for stream in streams
            if stream.get("codec_type") == codec_type
        ),
        None,
    )


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None
    return parsed
```

- [ ] **Step 4: Run server validator tests and verify they pass**

Run: `cd rick-tv-server && python -m pytest tests/test_validator.py -v`

Expected: PASS.

- [ ] **Step 5: Commit server validator**

```bash
git add rick-tv-server/src/rick_tv_server/validator.py rick-tv-server/tests/test_validator.py
git commit -m "feat: add server media profile validator"
```

## Task 2: Add Strict Retry Conversion Profile

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/converter.py`
- Modify: `rick-tv-server/tests/test_converter.py`

- [ ] **Step 1: Write failing strict profile test**

Append to `rick-tv-server/tests/test_converter.py`:

```python
from rick_tv_server.converter import strict_conversion_profile


def test_strict_ffmpeg_command_adds_bitrate_caps_and_faststart():
    command = build_ffmpeg_command(
        input_path="/tmp/uploads/source.mov",
        output_path="/tmp/converted/ready.mp4",
        profile=strict_conversion_profile(),
    )

    assert command[command.index("-b:v") + 1] == "650k"
    assert "-maxrate" in command
    assert command[command.index("-maxrate") + 1] == "700k"
    assert "-bufsize" in command
    assert command[command.index("-bufsize") + 1] == "1400k"
    assert "-r" in command
    assert command[command.index("-r") + 1] == "30"
    assert "-ac" in command
    assert command[command.index("-ac") + 1] == "2"
    assert "-ar" in command
    assert command[command.index("-ar") + 1] == "44100"
    assert "-movflags" in command
    assert command[command.index("-movflags") + 1] == "+faststart"
```

- [ ] **Step 2: Run converter tests and verify they fail**

Run: `cd rick-tv-server && python -m pytest tests/test_converter.py -v`

Expected: FAIL with `ImportError` for `strict_conversion_profile`.

- [ ] **Step 3: Implement optional strict conversion fields**

Update `rick-tv-server/src/rick_tv_server/converter.py` so it contains:

```python
@dataclass(frozen=True)
class ConversionProfile:
    width: int = 640
    height: int = 480
    video_bitrate: str = "700k"
    audio_bitrate: str = "96k"
    video_maxrate: str | None = None
    video_bufsize: str | None = None
    frame_rate: str | None = None
    audio_channels: int | None = None
    audio_sample_rate: str | None = None
    movflags: str | None = None


def strict_conversion_profile() -> ConversionProfile:
    return ConversionProfile(
        video_bitrate="650k",
        audio_bitrate="96k",
        video_maxrate="700k",
        video_bufsize="1400k",
        frame_rate="30",
        audio_channels=2,
        audio_sample_rate="44100",
        movflags="+faststart",
    )
```

Build the command in a mutable list. Keep the existing base flags, then append optional strict flags before the output path:

```python
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-f",
        "mp4",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        f"scale={profile.width}:{profile.height}",
        "-b:v",
        profile.video_bitrate,
    ]
    if profile.video_maxrate is not None:
        command.extend(["-maxrate", profile.video_maxrate])
    if profile.video_bufsize is not None:
        command.extend(["-bufsize", profile.video_bufsize])
    if profile.frame_rate is not None:
        command.extend(["-r", profile.frame_rate])
    command.extend(["-c:a", "aac", "-b:a", profile.audio_bitrate])
    if profile.audio_channels is not None:
        command.extend(["-ac", str(profile.audio_channels)])
    if profile.audio_sample_rate is not None:
        command.extend(["-ar", profile.audio_sample_rate])
    if profile.movflags is not None:
        command.extend(["-movflags", profile.movflags])
    command.append(str(output_path))
    return command
```

- [ ] **Step 4: Run converter tests and verify they pass**

Run: `cd rick-tv-server && python -m pytest tests/test_converter.py -v`

Expected: PASS.

- [ ] **Step 5: Commit strict retry profile**

```bash
git add rick-tv-server/src/rick_tv_server/converter.py rick-tv-server/tests/test_converter.py
git commit -m "feat: add strict media conversion profile"
```

## Task 3: Persist Failed Upload State

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/state.py`
- Modify: `rick-tv-server/tests/test_upload_flow.py`

- [ ] **Step 1: Write failing failed-state test**

Append to `rick-tv-server/tests/test_upload_flow.py`:

```python
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
```

- [ ] **Step 2: Run the failed-state test and verify it fails**

Run: `cd rick-tv-server && python -m pytest tests/test_upload_flow.py::test_failed_upload_state_persists_message_and_is_not_ready -v`

Expected: FAIL with `AttributeError` for `mark_failed`.

- [ ] **Step 3: Implement failed status and message persistence**

Update `rick-tv-server/src/rick_tv_server/state.py`:

```python
DeliveryStatus = Literal[
    "uploaded",
    "converting",
    "pending_delivery",
    "available",
    "failed",
    "canceled",
    "pending_device_delete",
    "deleted",
]
```

Add `"failed"` to `DELIVERY_STATUSES`.

Add a dataclass field:

```python
    failure_message: str | None = None
```

Load it in `DeliveryItem.from_json(...)`:

```python
            failure_message=data.get("failure_message"),  # type: ignore[arg-type]
```

Add a state method after `mark_pending(...)`:

```python
    def mark_failed(
        self,
        item_id: str,
        *,
        message: str,
        channel_id: str | None = None,
    ) -> DeliveryItem:
        with self._locked_state():
            item = self.items[item_id]
            if item.status not in ("uploaded", "converting"):
                raise ValueError(
                    f"delivery item must be uploaded or converting before failed: {item_id}"
                )

            item.status = "failed"
            item.failure_message = message
            if channel_id is not None:
                item.channel_id = channel_id
            self._persist()
            return replace(item)
```

Update `has_active_media_for_channel(...)` so failed uploads are not active:

```python
                if item.status not in {
                    "failed",
                    "canceled",
                    "deleted",
                }:
                    return True
```

Update `rick-tv-server/src/rick_tv_server/api.py` ack exclusions to include `"failed"`:

```python
            "failed",
```

- [ ] **Step 4: Run upload-flow tests and verify they pass**

Run: `cd rick-tv-server && python -m pytest tests/test_upload_flow.py -v`

Expected: PASS.

- [ ] **Step 5: Commit failed state**

```bash
git add rick-tv-server/src/rick_tv_server/state.py rick-tv-server/src/rick_tv_server/api.py rick-tv-server/tests/test_upload_flow.py
git commit -m "feat: persist failed upload state"
```

## Task 4: Validate Server Uploads and Retry Once

**Files:**
- Modify: `rick-tv-server/src/rick_tv_server/uploads.py`
- Modify: `rick-tv-server/tests/test_upload_flow.py`
- Modify: `rick-tv-server/src/rick_tv_server/bot.py`
- Modify: `rick-tv-server/tests/test_bot.py`

- [ ] **Step 1: Write failing upload validation tests**

Append to `rick-tv-server/tests/test_upload_flow.py`:

```python
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
        user_id="user-1",
        channel_id="01_Citadel",
        source_path=source_path,
        original_filename="citadel.mov",
    )

    assert validator_calls == [settings.media_dir / "converted" / "item-1.mp4"]
    assert store.statuses == ["uploaded", "converting", "pending"]
    assert pending.status == "pending"


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
        user_id="user-1",
        channel_id="01_Citadel",
        source_path=source_path,
        original_filename="citadel.mov",
    )

    converted_path = settings.media_dir / "converted" / "item-1.mp4"
    assert converter_calls == [("first", converted_path), ("retry", converted_path)]
    assert converted_path.read_bytes() == b"retry converted bytes"
    assert pending.status == "pending"
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
            user_id="user-1",
            channel_id="01_Citadel",
            source_path=source_path,
            original_filename="citadel.mov",
        )

    item = DeliveryStateStore(settings).items["item-1"]
    assert item.status == "failed"
    assert item.channel_id == "01_Citadel"
    assert item.failure_message == "Video could not be prepared for Rick TV playback."
```

Also update imports at the top of `test_upload_flow.py`:

```python
from rick_tv_server.uploads import UploadProcessingError, UploadProcessor
```

- [ ] **Step 2: Run upload validation tests and verify they fail**

Run: `cd rick-tv-server && python -m pytest tests/test_upload_flow.py -v`

Expected: FAIL because `UploadProcessor` has no `validator`, no `retry_converter`, and no `UploadProcessingError`.

- [ ] **Step 3: Implement upload validation and retry**

Update `rick-tv-server/src/rick_tv_server/uploads.py` imports:

```python
from rick_tv_server.converter import (
    ConversionProfile,
    convert_to_ready_mp4,
    strict_conversion_profile,
)
from rick_tv_server.validator import validate_ready_profile
```

Add types and error:

```python
UploadConverter = Callable[[Path, Path], object]
UploadValidator = Callable[[Path], bool]
ItemIdFactory = Callable[[], str]


class UploadProcessingError(RuntimeError):
    pass
```

Update `UploadProcessor.__init__(...)`:

```python
        converter: UploadConverter | None = None,
        retry_converter: UploadConverter | None = None,
        validator: UploadValidator | None = None,
        item_id_factory: ItemIdFactory | None = None,
```

Set defaults:

```python
        self.converter = converter or self._convert_to_ready_mp4
        self.retry_converter = retry_converter or self._convert_to_strict_ready_mp4
        self.validator = validator or validate_ready_profile
```

Replace the conversion section in `process_upload(...)` with:

```python
        try:
            self.converter(original_path, converted_path)
            if not self.validator(converted_path):
                self.retry_converter(original_path, converted_path)
                if not self.validator(converted_path):
                    raise UploadProcessingError(
                        "Video could not be prepared for Rick TV playback."
                    )
        except UploadProcessingError as exc:
            self.state_store.mark_failed(
                item_id,
                message=str(exc),
                channel_id=channel_id,
            )
            raise
        except Exception as exc:
            message = "Video could not be prepared for Rick TV playback."
            self.state_store.mark_failed(
                item_id,
                message=message,
                channel_id=channel_id,
            )
            raise UploadProcessingError(message) from exc
```

Add default retry converter:

```python
    @staticmethod
    def _convert_to_strict_ready_mp4(input_path: Path, output_path: Path) -> object:
        return convert_to_ready_mp4(
            input_path,
            output_path,
            strict_conversion_profile(),
        )
```

- [ ] **Step 4: Improve Telegram upload failure text**

In `rick-tv-server/src/rick_tv_server/bot.py`, add an import:

```python
from rick_tv_server.uploads import UploadProcessingError
```

Update `_process_pending_upload(...)` exception handling:

```python
    except UploadProcessingError as exc:
        await _send_upload_result(update, str(exc))
        return
    except Exception:
        await _send_upload_result(update, "Upload failed.")
        return
```

Update `rick-tv-server/tests/test_bot.py` imports:

```python
from rick_tv_server.uploads import UploadProcessingError
```

Update `RecordingUploadProcessor.process_upload(...)` failure:

```python
        if self.fail:
            raise UploadProcessingError(
                "Video could not be prepared for Rick TV playback."
            )
```

Update `test_channel_upload_flow_reports_failure_without_deliverable(...)` assertion:

```python
    assert "prepared for rick tv playback" in str(select_query.edits[0]["text"]).lower()
```

- [ ] **Step 5: Run server upload and bot tests**

Run:

```bash
cd rick-tv-server
python -m pytest tests/test_upload_flow.py tests/test_bot.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit server validation retry**

```bash
git add rick-tv-server/src/rick_tv_server/uploads.py rick-tv-server/src/rick_tv_server/bot.py rick-tv-server/tests/test_upload_flow.py rick-tv-server/tests/test_bot.py
git commit -m "feat: validate uploads before delivery"
```

## Task 5: Remove Pi Media-Profile Validation From Delivery

**Files:**
- Modify: `rick-tv-pi/src/rick_tv_pi/poller.py`
- Delete: `rick-tv-pi/src/rick_tv_pi/validator.py`
- Modify: `rick-tv-pi/tests/test_poller.py`
- Delete: `rick-tv-pi/tests/test_validator.py`

- [ ] **Step 1: Rewrite appliance poller tests around checksum, not ffprobe**

In `rick-tv-pi/tests/test_poller.py`, remove `import rick_tv_pi.poller as poller_module` if it is only used for validator monkeypatches after the edits.

In `test_poll_uses_registry_channel_ids_for_first_delivery(...)`, remove the `validate_ready_profile(...)` helper and this monkeypatch block:

```python
    monkeypatch.setattr(
        poller_module,
        "validate_ready_profile",
        validate_ready_profile,
        raising=False,
    )
```

Rename `test_download_validate_atomic_move_then_ack` to:

```python
def test_download_checksum_atomic_move_then_ack(tmp_path, monkeypatch):
```

Inside that test, remove the `validate_ready_profile(...)` helper and its monkeypatch. Keep the `Path.replace` spy and checksum-bearing ready payload.

Replace `test_failed_validation_does_not_ack(...)` with:

```python
def test_checksum_mismatch_does_not_ack(tmp_path):
    media_bytes = b"ready mp4 bytes"
    item_id = "delivery-invalid-checksum"
    channel_id = "01_Citadel"
    filename = "episode.mp4"
    destination = tmp_path / channel_id / filename
    temp_path = tmp_path / ".downloads" / f"{item_id}.tmp"
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        if request.method == "GET" and request.url.path == "/api/v1/ready":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": item_id,
                            "channel_id": channel_id,
                            "filename": filename,
                            "download_url": "https://server.example/downloads/episode.mp4",
                            "sha256": hashlib.sha256(b"different bytes").hexdigest(),
                        }
                    ]
                },
            )

        if request.method == "GET" and request.url.path == "/downloads/episode.mp4":
            return httpx.Response(200, content=media_bytes)

        if request.method == "POST" and request.url.path == f"/api/v1/ack/{item_id}":
            return httpx.Response(204)

        return httpx.Response(404)

    http_client = httpx.Client(
        base_url="https://server.example",
        transport=httpx.MockTransport(handler),
    )
    settings = PiSettings(
        server_base_url="https://server.example",
        api_token="test-token",
        media_root=tmp_path,
    )
    channels = [
        Channel(
            id=channel_id,
            number=1,
            display_name=None,
            path=tmp_path / channel_id,
        )
    ]

    Poller(settings, http_client).poll_once(channels)

    assert not destination.exists()
    assert not temp_path.exists()
    assert [request.url.path for request in requests] == [
        "/api/v1/ready",
        "/downloads/episode.mp4",
    ]
```

Replace `test_failed_item_does_not_block_next_delivery(...)` validation logic so the first item fails by checksum mismatch and the second succeeds:

```python
    failed_sha = hashlib.sha256(b"different bytes").hexdigest()
```

Use `failed_sha` for the failed item payload, remove `validated_paths`, remove validator monkeypatching, and assert:

```python
    assert not failed_destination.exists()
    assert not failed_temp_path.exists()
    assert downloaded_destination.read_bytes() == downloaded_media_bytes
    assert not downloaded_temp_path.exists()
```

Remove all remaining `poller_module.validate_ready_profile` monkeypatches in `test_poller.py`.

- [ ] **Step 2: Run Pi poller tests and verify they fail**

Run: `cd rick-tv-pi && python -m pytest tests/test_poller.py -v`

Expected: FAIL because `Poller._deliver(...)` still calls `validate_ready_profile`.

- [ ] **Step 3: Remove validation from Pi delivery**

Update `rick-tv-pi/src/rick_tv_pi/poller.py`:

Remove:

```python
from rick_tv_pi.validator import validate_ready_profile
```

Remove this block from `_deliver(...)`:

```python
            if not validate_ready_profile(temp_path):
                self._remove_temp(temp_path)
                return
```

Keep checksum validation:

```python
            if item.sha256 is not None:
                digest = hashlib.sha256(download_response.content).hexdigest()
                if digest != item.sha256:
                    self._remove_temp(temp_path)
                    return
```

Delete Pi validator files:

```bash
rm rick-tv-pi/src/rick_tv_pi/validator.py
rm rick-tv-pi/tests/test_validator.py
```

- [ ] **Step 4: Run Pi tests and verify they pass**

Run: `cd rick-tv-pi && python -m pytest -v`

Expected: PASS.

- [ ] **Step 5: Commit Pi delivery simplification**

```bash
git add rick-tv-pi/src/rick_tv_pi/poller.py rick-tv-pi/src/rick_tv_pi/validator.py rick-tv-pi/tests/test_poller.py rick-tv-pi/tests/test_validator.py
git commit -m "feat: trust server-validated media on pi"
```

## Task 6: Update End-to-End Contract Tests

**Files:**
- Modify: `rick-tv-pi/tests/test_end_to_end_contract.py`

- [ ] **Step 1: Remove Pi validator monkeypatches from contract tests**

In `rick-tv-pi/tests/test_end_to_end_contract.py`, remove:

```python
import rick_tv_pi.poller as poller_module
```

Remove each block like:

```python
    monkeypatch.setattr(
        poller_module,
        "validate_ready_profile",
        lambda path: True,
        raising=False,
    )
```

For tests that only use `monkeypatch` for this block, remove the `monkeypatch` fixture from the function signature.

- [ ] **Step 2: Run contract tests and verify they pass**

Run: `python -m pytest rick-tv-pi/tests/test_end_to_end_contract.py -v`

Expected: PASS.

- [ ] **Step 3: Commit contract update**

```bash
git add rick-tv-pi/tests/test_end_to_end_contract.py
git commit -m "test: update media delivery contract"
```

## Task 7: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/rick-tv-pi.md`
- Modify: `docs/rick-tv-server.md`
- Modify: `docs/superpowers/plans/2026-05-18-rick-tv-implementation.md`

- [ ] **Step 1: Replace outdated Pi validation wording**

Run:

```bash
rg -n "локально проверяет|ffprobe|validate_ready_profile|validator.py|server.*valid|готовый файл" README.md docs
```

Update docs so the current contract is explicit:

```markdown
The server converts uploads to the Rick TV ready profile and validates the
converted MP4 with `ffprobe` before exposing it through `/api/v1/ready`. The Pi
does not require `ffmpeg` or `ffprobe`; it downloads server-ready media, verifies
`sha256`, places the file into the channel directory, and acknowledges delivery.
```

In Russian README text, use:

```markdown
Сервер конвертирует загрузку в Rick TV ready-profile и валидирует результат
через `ffprobe` до появления файла в `/api/v1/ready`. `ffmpeg` и `ffprobe`
нужны только серверу: Pi скачивает уже проверенный сервером `.mp4`, сверяет `sha256`,
кладет файл в каталог канала и отправляет ack.
```

- [ ] **Step 2: Run doc consistency scan**

Run:

```bash
rg -n "локально проверяет|rick_tv_pi.validator|validate_ready_profile|ffprobe" README.md docs rick-tv-pi rick-tv-server
```

Expected:
- `ffprobe` remains in server docs, server Docker docs, server validator code/tests, and historical implementation plan lines that are updated to say server-side.
- No docs claim appliance runtime needs `ffprobe`.
- No production Pi code imports `validate_ready_profile`.

- [ ] **Step 3: Commit docs**

```bash
git add README.md docs/rick-tv-pi.md docs/rick-tv-server.md docs/superpowers/plans/2026-05-18-rick-tv-implementation.md
git commit -m "docs: document server-side media validation"
```

## Task 8: Full Local Verification

**Files:**
- No source edits.

- [ ] **Step 1: Run server tests**

Run:

```bash
cd rick-tv-server
python -m pytest -v
```

Expected: PASS.

- [ ] **Step 2: Run Pi tests**

Run:

```bash
cd rick-tv-pi
python -m pytest -v
```

Expected: PASS.

- [ ] **Step 3: Run repo-level contract tests**

Run:

```bash
python -m pytest rick-tv-pi/tests/test_end_to_end_contract.py -v
```

Expected: PASS.

- [ ] **Step 4: Run consistency scans**

Run:

```bash
rg -n "from rick_tv_pi.validator|validate_ready_profile" rick-tv-pi/src rick-tv-pi/tests tests
rg -n "ffprobe|validate_ready_profile" README.md docs rick-tv-server/src rick-tv-server/tests
```

Expected:
- First command has no matches.
- Second command only shows server-side validation and docs that describe server-side validation.

## Task 9: Deploy to Running Server and Pi for Live Check

**Files:**
- No repository source edits.

- [ ] **Step 1: Rebuild and restart server and bot**

Run:

```bash
cd rick-tv-server
docker compose --profile bot up -d --build
```

Expected: `rick-tv-server` and `rick-tv-bot` containers are running.

- [ ] **Step 2: Deploy updated Pi poller source to the legacy image**

Run from repo root:

```bash
scp rick-tv-pi/src/rick_tv_pi/poller.py pi@192.168.1.68:/tmp/rick-tv-poller.py
ssh -tt pi@192.168.1.68 'sudo install -m 0644 /tmp/rick-tv-poller.py /opt/rick-tv-src/rick-tv-pi/src/rick_tv_pi/poller.py && sudo systemctl restart rick-tv-pi.service'
```

Expected: SSH succeeds and `rick-tv-pi.service` restarts.

- [ ] **Step 3: Verify pending upload reaches `04_Pipa_Panch`**

Run:

```bash
ssh -tt pi@192.168.1.68 'sleep 35; sudo find /home/pi/rick-tv/media/04_Pipa_Panch -maxdepth 1 -type f -name "*.mp4" -printf "%f\n"'
```

Expected: output includes `a37a668d54c244acae1e5947b14b77f9.mp4` or another newly uploaded item for `04_Pipa_Panch`.

- [ ] **Step 4: Verify server acked the available item**

Run:

```bash
cd rick-tv-server
docker compose exec -T rick-tv-server python - <<'PY'
import json
from pathlib import Path

import sqlite3

with sqlite3.connect('/var/lib/rick-tv/state/rick-tv.sqlite3') as connection:
    for item_id, status, filename in connection.execute(
        "SELECT item_id, status, filename FROM media_items WHERE channel_id = ?",
        ('04_Pipa_Panch',),
    ):
        print(item_id, status, filename)
PY
```

Expected: the uploaded `04_Pipa_Panch` item is `available` after ack.

- [ ] **Step 5: Push branch**

Run:

```bash
git status --short
git push github feature/telegram-upload-runner-library
```

Expected: branch pushes successfully. Any pre-existing unrelated `.gitignore` change remains uncommitted unless it belongs to this implementation.
