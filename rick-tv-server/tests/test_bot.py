from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path

from telegram import InlineKeyboardMarkup

from rick_tv_server import bot
from rick_tv_server.channels import ChannelRegistryStore
from rick_tv_server.bot import remember_user_channel
from rick_tv_server.config import ServerSettings
from rick_tv_server.state import DeliveryStateStore
from rick_tv_server.uploads import UploadProcessingError


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
        self.videos: list[dict[str, object]] = []

    async def reply_text(self, text: str, **kwargs: object) -> None:
        self.replies.append({"text": text, **kwargs})

    async def reply_video(self, video, **kwargs: object) -> None:
        self.videos.append({"content": video.read(), **kwargs})


class FakeCallbackQuery:
    def __init__(self, data: str, message: FakeMessage | None = None) -> None:
        self.data = data
        self.message = message or FakeMessage()
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
            raise UploadProcessingError(
                "Video could not be prepared for Rick TV playback."
            )
        return type("Item", (), {"item_id": "item-1"})()


class FakeStateStore:
    def __init__(self) -> None:
        self.last_channel_by_user = {"42": "garage"}


class RecordingRemoteCommandStore:
    def __init__(self) -> None:
        self.selected_channels: list[str] = []

    def enqueue_select_channel(self, channel_id: str):
        self.selected_channels.append(channel_id)
        return type("Command", (), {"command_id": "cmd-1"})()


def markup_labels(markup: InlineKeyboardMarkup) -> list[str]:
    return [
        button.text
        for row in markup.inline_keyboard
        for button in row
    ]


def markup_callback_data(markup: InlineKeyboardMarkup) -> list[str | None]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]


class PublicOnlyStateStore:
    def __init__(self) -> None:
        self.remembered: list[tuple[str, str]] = []

    def remember_user_channel(self, user_id: str, channel_id: str) -> None:
        self.remembered.append((user_id, channel_id))


def command_handlers(application) -> set[str]:
    commands: set[str] = set()
    for handlers in application.handlers.values():
        for handler in handlers:
            handler_commands = getattr(handler, "commands", None)
            if handler_commands is not None:
                commands.update(handler_commands)
    return commands


def callback_handler_patterns(application) -> set[str]:
    patterns: set[str] = set()
    for handlers in application.handlers.values():
        for handler in handlers:
            pattern = getattr(handler, "pattern", None)
            if pattern is None:
                continue
            patterns.add(getattr(pattern, "pattern", str(pattern)))
    return patterns


def test_application_registers_direct_command_handlers(tmp_path: Path):
    settings = replace(
        make_settings(tmp_path),
        telegram_bot_token="123456:ABC",
        telegram_allowed_user_ids=(42,),
    )
    channel_store = ChannelRegistryStore(settings)
    state_store = DeliveryStateStore(settings)

    application = bot.build_application(
        settings,
        channel_store,
        state_store,
        RecordingUploadProcessor(),
    )

    assert {
        "add_channel",
        "list_channels",
        "restore_all_videos",
    }.issubset(command_handlers(application))
    assert "menu" not in command_handlers(application)
    assert "channels" not in command_handlers(application)
    assert "upload" not in command_handlers(application)
    assert callback_handler_patterns(application) == {
        r"^channel_",
        r"^restore_all",
        r"^upload_channel:",
    }


def test_telegram_command_menu_contains_direct_actions_only() -> None:
    recorded_commands = []

    class FakeBot:
        async def set_my_commands(self, commands):
            recorded_commands.extend(commands)

    class FakeApplication:
        bot = FakeBot()

    asyncio.run(bot.configure_bot_command_menu(FakeApplication()))

    assert [(command.command, command.description) for command in recorded_commands] == [
        ("add_channel", "Add channel"),
        ("list_channels", "List channels"),
        ("restore_all_videos", "Restore all videos"),
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


def test_unauthorized_user_is_rejected_before_add_channel_command(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    message = FakeMessage()
    update = FakeUpdate(effective_user=FakeUser(id=99), message=message)

    asyncio.run(
        bot.handle_add_channel_command(
            update,
            FakeContext(),
            channel_store,
            allowed_user_ids=(42,),
        )
    )

    assert message.replies == [{"text": "Unauthorized."}]
    assert channel_store.load().channels == {}


def test_add_channel_command_starts_add_flow(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    context = FakeContext()
    message = FakeMessage()

    asyncio.run(
        bot.handle_add_channel_command(
            FakeUpdate(effective_user=FakeUser(id=42), message=message),
            context,
            channel_store,
            allowed_user_ids=(42,),
        )
    )

    assert context.user_data["channel_action"] == {"type": "add"}
    assert len(message.replies) == 1
    assert "display name" in str(message.replies[0]["text"]).lower()
    assert "reply_markup" not in message.replies[0]


def test_list_channels_command_opens_channel_list(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    channel_store.add_channel("02_Interdimensional_Cable", "Interdimensional Cable")
    message = FakeMessage()

    asyncio.run(
        bot.handle_list_channels_command(
            FakeUpdate(effective_user=FakeUser(id=42), message=message),
            FakeContext(),
            channel_store,
            allowed_user_ids=(42,),
        )
    )

    assert "01 - Citadel" in str(message.replies[0]["text"])
    assert "02 - Interdimensional Cable" in str(message.replies[0]["text"])
    list_markup = message.replies[0]["reply_markup"]
    assert isinstance(list_markup, InlineKeyboardMarkup)
    assert markup_labels(list_markup) == [
        "01 - Citadel",
        "02 - Interdimensional Cable",
    ]
    assert markup_callback_data(list_markup) == [
        "channel_view:01_Citadel",
        "channel_view:02_Interdimensional_Cable",
    ]


def test_channels_list_opens_per_channel_actions(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    channel_store.add_channel("02_Interdimensional_Cable", "Interdimensional Cable")
    state_store = DeliveryStateStore(settings)
    context = FakeContext()

    view_query = FakeCallbackQuery("channel_view:01_Citadel")
    asyncio.run(
        bot.handle_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=view_query),
            context,
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )

    assert "01 - Citadel" in str(view_query.edits[0]["text"])
    view_markup = view_query.edits[0]["reply_markup"]
    assert isinstance(view_markup, InlineKeyboardMarkup)
    assert markup_labels(view_markup) == [
        "Switch channel on Pi",
        "List all videos",
        "Rename channel",
        "Delete channel",
        "Back to list",
    ]
    assert markup_callback_data(view_markup) == [
        "channel_switch:01_Citadel",
        "channel_videos:01_Citadel",
        "channel_rename:01_Citadel",
        "channel_delete:01_Citadel",
        "channel_list",
    ]


def test_selected_channel_can_queue_remote_pi_switch(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    state_store = DeliveryStateStore(settings)
    remote_store = RecordingRemoteCommandStore()

    switch_query = FakeCallbackQuery("channel_switch:01_Citadel")
    asyncio.run(
        bot.handle_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=switch_query),
            FakeContext(),
            channel_store,
            state_store,
            remote_command_store=remote_store,
            allowed_user_ids=(42,),
        )
    )

    assert remote_store.selected_channels == ["01_Citadel"]
    assert "queued" in str(switch_query.edits[0]["text"]).lower()
    assert "01 - Citadel" in str(switch_query.edits[0]["text"])


def test_channel_video_list_opens_video_detail_actions(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    state_store = DeliveryStateStore(settings)
    for item_id, channel_id, filename in [
        ("item-1", "01_Citadel", "first.mp4"),
        ("item-2", "01_Citadel", "second.mp4"),
        ("item-3", "02_Interdimensional_Cable", "other.mp4"),
    ]:
        original_path = settings.media_dir / "uploads" / f"{item_id}.mov"
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_bytes(f"original {item_id}".encode())
        converted_path = settings.media_dir / "converted" / filename
        converted_path.parent.mkdir(parents=True, exist_ok=True)
        converted_path.write_bytes(f"converted {item_id}".encode())
        state_store.create_uploaded_item(
            item_id=item_id,
            original_path=original_path,
        )
        state_store.mark_converting(item_id)
        state_store.mark_pending(
            item_id,
            converted_path=converted_path,
            channel_id=channel_id,
            filename=filename,
        )
    state_store.ack_item("item-2")

    list_query = FakeCallbackQuery("channel_videos:01_Citadel")
    asyncio.run(
        bot.handle_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=list_query),
            FakeContext(),
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )

    assert "Videos in 01 - Citadel" in str(list_query.edits[0]["text"])
    assert "first.mp4" in str(list_query.edits[0]["text"])
    assert "second.mp4" in str(list_query.edits[0]["text"])
    list_markup = list_query.edits[0]["reply_markup"]
    assert isinstance(list_markup, InlineKeyboardMarkup)
    assert markup_labels(list_markup) == ["first.mp4", "second.mp4", "Back to channel"]
    assert markup_callback_data(list_markup) == [
        "channel_video:item-1",
        "channel_video:item-2",
        "channel_view:01_Citadel",
    ]

    detail_query = FakeCallbackQuery("channel_video:item-1")
    asyncio.run(
        bot.handle_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=detail_query),
            FakeContext(),
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )

    assert "first.mp4" in str(detail_query.edits[0]["text"])
    detail_markup = detail_query.edits[0]["reply_markup"]
    assert isinstance(detail_markup, InlineKeyboardMarkup)
    assert markup_labels(detail_markup) == ["Download", "Delete", "Back"]
    assert markup_callback_data(detail_markup) == [
        "channel_video_download:item-1",
        "channel_video_delete:item-1",
        "channel_videos:01_Citadel",
    ]


def test_channel_video_download_sends_converted_mp4(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    state_store = DeliveryStateStore(settings)
    original_path = settings.media_dir / "uploads" / "item-1.mov"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"original media bytes")
    converted_path = settings.media_dir / "converted" / "first.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted media bytes")
    state_store.create_uploaded_item(
        item_id="item-1",
        original_path=original_path,
    )
    state_store.mark_converting("item-1")
    state_store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
        filename="first.mp4",
    )
    message = FakeMessage()
    download_query = FakeCallbackQuery("channel_video_download:item-1", message=message)

    asyncio.run(
        bot.handle_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=download_query),
            FakeContext(),
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )

    assert message.videos == [
        {"content": b"converted media bytes", "filename": "first.mp4"}
    ]
    assert download_query.edits == []


def test_channel_video_delete_removes_server_files_and_returns_to_video_list(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    state_store = DeliveryStateStore(settings)
    original_path = settings.media_dir / "uploads" / "item-1.mov"
    original_path.parent.mkdir(parents=True)
    original_path.write_bytes(b"original media bytes")
    converted_path = settings.media_dir / "converted" / "first.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted media bytes")
    state_store.create_uploaded_item(
        item_id="item-1",
        original_path=original_path,
    )
    state_store.mark_converting("item-1")
    state_store.mark_pending(
        "item-1",
        converted_path=converted_path,
        channel_id="01_Citadel",
        filename="first.mp4",
    )
    state_store.ack_item("item-1")
    delete_query = FakeCallbackQuery("channel_video_delete:item-1")

    asyncio.run(
        bot.handle_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=delete_query),
            FakeContext(),
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )

    assert state_store.items["item-1"].status == "pending_device_delete"
    assert state_store.device_delete_items_for_channels(["01_Citadel"])[0].item_id == (
        "item-1"
    )
    assert not original_path.exists()
    assert not converted_path.exists()
    assert "Deleted first.mp4" in str(delete_query.edits[0]["text"])
    assert "No videos in 01 - Citadel" in str(delete_query.edits[0]["text"])


def test_restore_all_videos_command_requires_confirmation(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)
    message = FakeMessage()

    asyncio.run(
        bot.handle_restore_all_videos_command(
            FakeUpdate(effective_user=FakeUser(id=42), message=message),
            FakeContext(),
            state_store,
            allowed_user_ids=(42,),
        )
    )

    assert "Confirm" in str(message.replies[0]["text"])
    reply_markup = message.replies[0]["reply_markup"]
    assert isinstance(reply_markup, InlineKeyboardMarkup)
    assert markup_labels(reply_markup) == ["Confirm restore all"]
    assert markup_callback_data(reply_markup) == ["restore_all_confirm"]


def test_channel_add_generates_incremental_channel_id(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    channel_store.add_channel("02_Interdimensional_Cable", "Interdimensional Cable")
    channel_store.add_channel("03_Test_Channel", "Test Channel")
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
    assert "display name" in str(add_query.edits[0]["text"]).lower()

    message = FakeMessage(text="Birdperson TV")
    asyncio.run(
        bot.handle_channel_text(
            FakeUpdate(
                effective_user=FakeUser(id=42),
                message=message,
            ),
            context,
            channel_store,
            allowed_user_ids=(42,),
        )
    )

    registry = channel_store.load()
    assert registry.channels["04_Birdperson_TV"] == {"display_name": "Birdperson TV"}
    assert "04 - Birdperson TV" in str(message.replies[0]["text"])


def test_channel_rename_and_delete_flow_stays_on_selected_channel(tmp_path: Path):
    settings = make_settings(tmp_path)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    state_store = DeliveryStateStore(settings)
    context = FakeContext()

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
    assert "01 - Citadel" in str(rename_query.edits[0]["text"])

    rename_message = FakeMessage(text="Citadel Archive")
    asyncio.run(
        bot.handle_channel_text(
            FakeUpdate(
                effective_user=FakeUser(id=42),
                message=rename_message,
            ),
            context,
            channel_store,
            allowed_user_ids=(42,),
        )
    )
    assert channel_store.load().channels["01_Citadel"] == {
        "display_name": "Citadel Archive"
    }
    assert "01 - Citadel Archive" in str(rename_message.replies[0]["text"])

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
    assert "01 - Citadel Archive" in str(delete_query.edits[0]["text"])
    assert "Confirm" in markup_labels(delete_query.edits[0]["reply_markup"])

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


def test_channel_upload_flow_accepts_video_before_channel_choice(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    channel_store.add_channel("02_Interdimensional_Cable", "Interdimensional Cable")
    upload_processor = RecordingUploadProcessor()
    context = FakeContext()
    message = FakeMessage(
        video=FakeAttachment(file_name="episode.mov", content=b"video bytes")
    )

    asyncio.run(
        bot.handle_upload_attachment(
            FakeUpdate(effective_user=FakeUser(id=42), message=message),
            context,
            settings,
            upload_processor,
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )

    assert upload_processor.calls == []
    assert "pending_upload" in context.user_data
    assert "choose a channel" in str(message.replies[0]["text"]).lower()
    reply_markup = message.replies[0]["reply_markup"]
    assert isinstance(reply_markup, InlineKeyboardMarkup)
    assert markup_labels(reply_markup) == ["01 - Citadel", "02 - Interdimensional Cable"]

    select_query = FakeCallbackQuery("upload_channel:01_Citadel")
    asyncio.run(
        bot.handle_upload_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=select_query),
            context,
            settings,
            state_store,
            upload_processor,
            channel_store,
            allowed_user_ids=(42,),
        )
    )

    assert upload_processor.calls == [
        {
            "channel_id": "01_Citadel",
            "source_path": upload_processor.calls[0]["source_path"],
            "original_filename": "episode.mov",
            "content": b"video bytes",
        }
    ]
    assert "pending_upload" not in context.user_data
    assert "accepted" in str(select_query.edits[0]["text"]).lower()


def test_channel_upload_flow_reports_failure_without_deliverable(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)
    channel_store = ChannelRegistryStore(settings)
    channel_store.add_channel("01_Citadel", "Citadel")
    upload_processor = RecordingUploadProcessor(fail=True)
    context = FakeContext()
    message = FakeMessage(
        document=FakeAttachment(file_name="episode.mp4", content=b"video bytes")
    )

    asyncio.run(
        bot.handle_upload_attachment(
            FakeUpdate(effective_user=FakeUser(id=42), message=message),
            context,
            settings,
            upload_processor,
            channel_store,
            state_store,
            allowed_user_ids=(42,),
        )
    )

    select_query = FakeCallbackQuery("upload_channel:01_Citadel")
    asyncio.run(
        bot.handle_upload_channel_callback(
            FakeUpdate(effective_user=FakeUser(id=42), callback_query=select_query),
            context,
            settings,
            state_store,
            upload_processor,
            channel_store,
            allowed_user_ids=(42,),
        )
    )

    assert len(upload_processor.calls) == 1
    assert "pending_upload" not in context.user_data
    assert "prepared for rick tv playback" in str(select_query.edits[0]["text"]).lower()


def test_restore_all_callback_requires_confirmation_and_requeues_available(tmp_path: Path):
    settings = make_settings(tmp_path)
    state_store = DeliveryStateStore(settings)
    converted_path = tmp_path / "media" / "converted" / "item-1.mp4"
    converted_path.parent.mkdir(parents=True)
    converted_path.write_bytes(b"converted")
    state_store.create_uploaded_item(
        item_id="item-1",
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
    assert state_store.items["item-1"].status == "available"

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
    assert state_store.items["item-1"].status == "pending_delivery"
