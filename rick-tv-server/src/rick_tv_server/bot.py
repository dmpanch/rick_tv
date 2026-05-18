from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


@dataclass(frozen=True)
class ChannelChoice:
    id: str
    display_name: str


KeyboardButton = dict[str, str]
Keyboard = list[list[KeyboardButton]]


def build_upload_channel_keyboard(
    channels: list[ChannelChoice],
    remembered_channel_id: str | None,
) -> Keyboard:
    remembered = [channel for channel in channels if channel.id == remembered_channel_id]
    remaining = [channel for channel in channels if channel.id != remembered_channel_id]
    ordered_channels = remembered + remaining

    keyboard: Keyboard = []
    for channel in ordered_channels:
        label = channel.display_name
        if channel.id == remembered_channel_id:
            label = f"{label} (last used)"
        keyboard.append(
            [
                {
                    "text": label,
                    "callback_data": f"upload_channel:{channel.id}",
                }
            ]
        )
    return keyboard


def build_upload_channel_reply_markup(keyboard: Keyboard) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=button["text"],
                    callback_data=button["callback_data"],
                )
                for button in row
            ]
            for row in keyboard
        ]
    )


def remember_user_channel(
    user_id: int | str,
    channel_id: str,
    state_store: Any,
) -> None:
    state_store.remember_user_channel(str(user_id), channel_id)


async def handle_upload_media(
    update: Any,
    context: Any,
    channels: list[ChannelChoice],
    state_store: Any,
) -> None:
    del context

    user_id = str(update.effective_user.id)
    remembered_channel_id = state_store.last_channel_by_user.get(user_id)
    keyboard = build_upload_channel_keyboard(channels, remembered_channel_id)
    remembered_channel = next(
        (channel for channel in channels if channel.id == remembered_channel_id),
        None,
    )

    await update.message.reply_text(
        f"Choose a channel for this upload. Last used: {remembered_channel.display_name}"
        if remembered_channel is not None
        else "Choose a channel for this upload.",
        reply_markup=build_upload_channel_reply_markup(keyboard),
    )
