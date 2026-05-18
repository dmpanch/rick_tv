from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from telegram import InlineKeyboardMarkup

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


@dataclass
class FakeUpdate:
    effective_user: FakeUser
    message: FakeMessage


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
