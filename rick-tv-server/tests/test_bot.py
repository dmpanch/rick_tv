from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from telegram import InlineKeyboardMarkup

from rick_tv_server import bot
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
    def __init__(self) -> None:
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
    pass


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

    assert deleted.status == "deleted_server_side"
    assert state_store.items["item-1"].status == "deleted_server_side"
    assert "item-1" not in state_store.archive_index
    assert not original_path.exists()
    assert not converted_path.exists()
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
    assert "Confirm server-side delete" in str(request_query.edits[0]["text"])
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
    assert "Deleted server-side media" in str(confirm_query.edits[0]["text"])
    assert state_store.items["item-1"].status == "deleted_server_side"
    assert not original_path.exists()
    assert not converted_path.exists()


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
