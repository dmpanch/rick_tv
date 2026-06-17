from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from telegram import InlineKeyboardMarkup

from rick_tv_server import bot
from rick_tv_server.channels import ChannelRegistryStore
from rick_tv_server.bot import ChannelChoice, handle_upload_media, remember_user_channel
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


@dataclass
class FakeUser:
    id: int


class FakeMessage:
    def __init__(self, text: str | None = None, video=None, document=None) -> None:
        self.text = text
        self.video = video
        self.document = document
        self.replies: list[dict[str, object]] = []

    async def reply_text(self, text: str, **kwargs: object) -> None:
        self.replies.append({"text": text, **kwargs})


class FakeCallbackQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.answers: list[str | None] = []
        self.edits: list[dict[str, object]] = []

    async def answer(self, text: str | None = None) -> None:
        self.answers.append(text)

    async def edit_message_text(self, text: str, **kwargs: object) -> None:
        self.edits.append({"text": text, **kwargs})


@dataclass
class FakeUpdate:
    effective_user: FakeUser
    message: FakeMessage | None = None
    callback_query: FakeCallbackQuery | None = None


class FakeContext:
    def __init__(self) -> None:
        self.user_data: dict[str, object] = {}


class FakeTelegramFile:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def download_to_drive(self, path: Path) -> None:
        Path(path).write_bytes(self.content)


class FakeAttachment:
    def __init__(self, *, file_name: str, content: bytes) -> None:
        self.file_name = file_name
        self.content = content

    async def get_file(self) -> FakeTelegramFile:
        return FakeTelegramFile(self.content)


class RecordingUploadProcessor:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def process_upload(self, **kwargs: object):
        source_path = Path(kwargs["source_path"])
        self.calls.append({**kwargs, "content": source_path.read_bytes()})
        if self.fail:
            raise RuntimeError("conversion failed")
        return type("Item", (), {"item_id": "item-1"})()


class FakeStateStore:
    def __init__(self) -> None:
        self.last_channel_by_user = {"42": "garage"}


class PublicOnlyStateStore:
    def __init__(self) -> None:
        self.remembered: list[tuple[str, str]] = []

    def remember_user_channel(self, user_id: str, channel_id: str) -> None:
        self.remembered.append((user_id, channel_id))


def test_upload_always_shows_explicit_channel_choices():
    message = FakeMessage()
    update = FakeUpdate(effective_user=FakeUser(id=42), message=message)
    channels = [
        ChannelChoice(id="kitchen", display_name="Kitchen"),
        ChannelChoice(id="garage", display_name="Garage"),
        ChannelChoice(id="patio", display_name="Patio"),
    ]

    asyncio.run(handle_upload_media(update, FakeContext(), channels, FakeStateStore()))

    assert len(message.replies) == 1
    reply = message.replies[0]
    assert "Garage" in str(reply["text"])
    assert "choose" in str(reply["text"]).lower()

    reply_markup = reply["reply_markup"]
    assert isinstance(reply_markup, InlineKeyboardMarkup)

    labels = [
        button.text
        for row in reply_markup.inline_keyboard
        for button in row
    ]
    callback_data = [
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
    ]

    assert labels == ["Garage (last used)", "Kitchen", "Patio"]
    assert callback_data == [
        "upload_channel:garage",
        "upload_channel:kitchen",
        "upload_channel:patio",
    ]


def test_remember_user_channel_uses_public_state_store_interface():
    state_store = PublicOnlyStateStore()

    remember_user_channel(42, "garage", state_store)

    assert state_store.remembered == [("42", "garage")]


def test_remember_user_channel_persists_with_real_state_store(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)

    remember_user_channel(42, "garage", state_store)

    reloaded = DeliveryStateStore(settings)
    assert reloaded.last_channel_by_user == {"42": "garage"}


def test_pending_delete_marks_canceled(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)
    for item_id, filename in [
        ("item-1", "first-video.mp4"),
        ("item-2", "second-video.mp4"),
    ]:
        state_store.create_uploaded_item(
            item_id=item_id,
            user_id="user-1",
            original_path=tmp_path / "media" / "uploads" / f"{item_id}.mov",
        )
        state_store.mark_converting(item_id)
        state_store.mark_pending(
            item_id,
            converted_path=tmp_path / "media" / "converted" / filename,
            channel_id="01_Citadel",
            filename=filename,
        )

    pending_text = bot.format_pending_media_list(state_store.list_pending_items())

    assert "item-1" in pending_text
    assert "first-video.mp4" in pending_text
    assert "item-2" in pending_text
    assert "second-video.mp4" in pending_text

    canceled = bot.cancel_pending_media("item-1", state_store)

    assert canceled.status == "canceled"
    assert state_store.items["item-1"].status == "canceled"
    assert [item.item_id for item in state_store.list_pending_items()] == ["item-2"]


def test_archive_delete_requires_confirmation_and_is_server_side_only(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)
    original_path = tmp_path / "media" / "uploads" / "item-1.mov"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"original media bytes")
    converted_path = tmp_path / "media" / "converted" / "archived-video.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted media bytes")
    state_store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=original_path,
    )
    state_store.mark_converting("item-1")
    state_store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
        filename="archived-video.mp4",
    )
    state_store.ack_item("item-1")

    archive_text = bot.format_archive_media_list(state_store.list_archived_items())
    archive_keyboard = bot.build_archive_media_keyboard(state_store.list_archived_items())

    assert "item-1" in archive_text
    assert "archived-video.mp4" in archive_text
    assert archive_keyboard == [
        [
            {
                "text": "Delete archived-video.mp4",
                "callback_data": "archive_delete:item-1",
            }
        ]
    ]

    confirmation_text = bot.request_archive_delete("item-1", state_store)
    confirmation_keyboard = bot.build_archive_delete_confirmation_keyboard("item-1")

    assert "Confirm" in confirmation_text
    assert confirmation_keyboard == [
        [
            {
                "text": "Confirm delete",
                "callback_data": "archive_delete_confirm:item-1",
            }
        ]
    ]
    assert state_store.items["item-1"].status == "archived"
    assert state_store.archive_index["item-1"]["status"] == "archived"
    assert converted_path.exists()

    deleted = bot.confirm_archive_delete("item-1", state_store)

    assert deleted.status == "deleted_from_library"
    assert state_store.items["item-1"].status == "deleted_from_library"
    assert "item-1" not in state_store.archive_index
    assert original_path.exists()
    assert converted_path.exists()
    assert state_store.acknowledgements == {"item-1": {"status": "delivered"}}


def test_archive_callbacks_request_confirmation_and_delete(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)
    original_path = tmp_path / "media" / "uploads" / "item-1.mov"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"original media bytes")
    converted_path = tmp_path / "media" / "converted" / "archived-video.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted media bytes")
    state_store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=original_path,
    )
    state_store.mark_converting("item-1")
    state_store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
        filename="archived-video.mp4",
    )
    state_store.ack_item("item-1")

    request_query = FakeCallbackQuery("archive_delete:item-1")
    request_update = FakeUpdate(
        effective_user=FakeUser(id=42),
        callback_query=request_query,
    )

    asyncio.run(bot.handle_archive_callback(request_update, FakeContext(), state_store))

    assert request_query.answers == [None]
    assert len(request_query.edits) == 1
    assert "Confirm library removal" in str(request_query.edits[0]["text"])
    assert isinstance(request_query.edits[0]["reply_markup"], InlineKeyboardMarkup)
    assert state_store.items["item-1"].status == "archived"
    assert original_path.exists()
    assert converted_path.exists()

    confirm_query = FakeCallbackQuery("archive_delete_confirm:item-1")
    confirm_update = FakeUpdate(
        effective_user=FakeUser(id=42),
        callback_query=confirm_query,
    )

    asyncio.run(bot.handle_archive_callback(confirm_update, FakeContext(), state_store))

    assert confirm_query.answers == [None]
    assert len(confirm_query.edits) == 1
    assert "Removed archived media from library" in str(confirm_query.edits[0]["text"])
    assert state_store.items["item-1"].status == "deleted_from_library"
    assert original_path.exists()
    assert converted_path.exists()


def test_archive_list_handler_shows_archived_media(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "archived-video.mp4"
    state_store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mov",
    )
    state_store.mark_converting("item-1")
    state_store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
        filename="archived-video.mp4",
    )
    state_store.ack_item("item-1")
    message = FakeMessage()
    update = FakeUpdate(effective_user=FakeUser(id=42), message=message)

    asyncio.run(bot.handle_archive_media(update, FakeContext(), state_store))

    assert len(message.replies) == 1
    assert "archived-video.mp4" in str(message.replies[0]["text"])
    assert isinstance(message.replies[0]["reply_markup"], InlineKeyboardMarkup)


def test_unauthorized_user_is_rejected_before_channel_menu(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings.config_dir / "channels.yml")
    state_store = DeliveryStateStore(settings)
    message = FakeMessage()
    update = FakeUpdate(effective_user=FakeUser(id=99), message=message)

    asyncio.run(
        bot.handle_channels_menu(
            update,
            FakeContext(),
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )

    assert message.replies == [{"text": "Unauthorized."}]
    assert channel_store.load().channels == {}


def test_channels_menu_add_rename_and_delete_flow(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings.config_dir / "channels.yml")
    state_store = DeliveryStateStore(settings)
    context = FakeContext()

    add_query = FakeCallbackQuery("channel_add")
    asyncio.run(
        bot.handle_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=add_query),
            context,
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )
    assert "channel_id" in str(add_query.edits[0]["text"])

    asyncio.run(
        bot.handle_channel_text(
            FakeUpdate(
                effective_user=FakeUser(id=42),
                message=FakeMessage(text="01_Citadel Citadel TV"),
            ),
            context,
            channel_store,
            allowed_user_ids=(42,),
        )
    )
    assert channel_store.load().channels == {
        "01_Citadel": {"display_name": "Citadel TV"}
    }

    rename_query = FakeCallbackQuery("channel_rename:01_Citadel")
    asyncio.run(
        bot.handle_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=rename_query),
            context,
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )
    asyncio.run(
        bot.handle_channel_text(
            FakeUpdate(
                effective_user=FakeUser(id=42),
                message=FakeMessage(text="Citadel Archive"),
            ),
            context,
            channel_store,
            allowed_user_ids=(42,),
        )
    )
    assert channel_store.load().channels["01_Citadel"] == {
        "display_name": "Citadel Archive"
    }

    delete_query = FakeCallbackQuery("channel_delete:01_Citadel")
    asyncio.run(
        bot.handle_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=delete_query),
            context,
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )
    assert "Confirm" in str(delete_query.edits[0]["text"])

    confirm_query = FakeCallbackQuery("channel_delete_confirm:01_Citadel")
    asyncio.run(
        bot.handle_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=confirm_query),
            context,
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )
    assert channel_store.load().channels == {}


def test_channel_upload_flow_downloads_video_and_processes_upload(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)
    upload_processor = RecordingUploadProcessor()
    context = FakeContext()
    select_query = FakeCallbackQuery("upload_channel:01_Citadel")

    asyncio.run(
        bot.handle_upload_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=select_query),
            context,
            state_store,
            allowed_user_ids=(42,),
        )
    )
    message = FakeMessage(
        video=FakeAttachment(file_name="episode.mov", content=b"video bytes")
    )

    asyncio.run(
        bot.handle_upload_attachment(
            FakeUpdate(effective_user=FakeUser(id=42), message=message),
            context,
            settings,
            upload_processor,
            allowed_user_ids=(42,),
        )
    )

    assert context.user_data["upload_channel_id"] == "01_Citadel"
    assert upload_processor.calls == [
        {
            "user_id": "42",
            "channel_id": "01_Citadel",
            "source_path": upload_processor.calls[0]["source_path"],
            "original_filename": "episode.mov",
            "content": b"video bytes",
        }
    ]
    assert "accepted" in str(message.replies[0]["text"]).lower()


def test_channel_upload_flow_reports_failure_without_deliverable(tmp_path: Path):
    settings = make_settings(tmp_path)
    upload_processor = RecordingUploadProcessor(fail=True)
    context = FakeContext()
    context.user_data["upload_channel_id"] = "01_Citadel"
    message = FakeMessage(
        document=FakeAttachment(file_name="episode.mp4", content=b"video bytes")
    )

    asyncio.run(
        bot.handle_upload_attachment(
            FakeUpdate(effective_user=FakeUser(id=42), message=message),
            context,
            settings,
            upload_processor,
            allowed_user_ids=(42,),
        )
    )

    assert len(upload_processor.calls) == 1
    assert "failed" in str(message.replies[0]["text"]).lower()


def test_restore_all_callback_requires_confirmation_and_requeues_archived(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted")
    state_store.create_uploaded_item(
        item_id="item-1",
        user_id="user-1",
        original_path=tmp_path / "media" / "uploads" / "item-1.mov",
    )
    state_store.mark_converting("item-1")
    state_store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
    )
    state_store.ack_item("item-1")

    request_query = FakeCallbackQuery("restore_all")
    asyncio.run(
        bot.handle_restore_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=request_query),
            FakeContext(),
            state_store,
            allowed_user_ids=(42,),
        )
    )
    assert "Confirm" in str(request_query.edits[0]["text"])
    assert state_store.items["item-1"].status == "archived"

    confirm_query = FakeCallbackQuery("restore_all_confirm")
    asyncio.run(
        bot.handle_restore_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=confirm_query),
            FakeContext(),
            state_store,
            allowed_user_ids=(42,),
        )
    )

    assert "1 media item" in str(confirm_query.edits[0]["text"])
    assert state_store.items["item-1"].status == "pending"
