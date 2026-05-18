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


def build_pending_media_keyboard(pending_items: list[Any]) -> Keyboard:
    keyboard: Keyboard = []
    for item in pending_items:
        filename = _media_filename(item)
        keyboard.append(
            [
                {
                    "text": f"Delete {filename}",
                    "callback_data": f"pending_delete:{item.item_id}",
                }
            ]
        )
    return keyboard


def build_pending_media_reply_markup(keyboard: Keyboard) -> InlineKeyboardMarkup:
    return _build_reply_markup(keyboard)


def build_archive_media_keyboard(archived_items: list[Any]) -> Keyboard:
    keyboard: Keyboard = []
    for item in archived_items:
        filename = _media_filename(item)
        keyboard.append(
            [
                {
                    "text": f"Delete {filename}",
                    "callback_data": f"archive_delete:{item.item_id}",
                }
            ]
        )
    return keyboard


def build_archive_delete_confirmation_keyboard(item_id: str) -> Keyboard:
    return [
        [
            {
                "text": "Confirm delete",
                "callback_data": f"archive_delete_confirm:{item_id}",
            }
        ]
    ]


def build_archive_media_reply_markup(keyboard: Keyboard) -> InlineKeyboardMarkup:
    return _build_reply_markup(keyboard)


def _build_reply_markup(keyboard: Keyboard) -> InlineKeyboardMarkup:
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


def format_pending_media_list(pending_items: list[Any]) -> str:
    if not pending_items:
        return "No pending media."

    lines = ["Pending media:"]
    for item in pending_items:
        lines.append(f"- {item.item_id}: {_media_filename(item)}")
    return "\n".join(lines)


def format_archive_media_list(archived_items: list[Any]) -> str:
    if not archived_items:
        return "No archived media."

    lines = ["Archived media:"]
    for item in archived_items:
        lines.append(f"- {item.item_id}: {_media_filename(item)}")
    return "\n".join(lines)


def cancel_pending_media(item_id: str, state_store: Any) -> Any:
    return state_store.cancel_pending_item(item_id)


def request_archive_delete(item_id: str, state_store: Any) -> str:
    item = state_store.request_archive_delete(item_id)
    return f"Confirm server-side delete for {item.item_id}: {_media_filename(item)}?"


def confirm_archive_delete(item_id: str, state_store: Any) -> Any:
    return state_store.confirm_archive_delete(item_id)


async def handle_archive_media(update: Any, context: Any, state_store: Any) -> None:
    del context

    archived_items = state_store.list_archived_items()
    await update.message.reply_text(
        format_archive_media_list(archived_items),
        reply_markup=build_archive_media_reply_markup(
            build_archive_media_keyboard(archived_items)
        ),
    )


async def handle_archive_callback(update: Any, context: Any, state_store: Any) -> None:
    del context

    query = update.callback_query
    await query.answer()
    data = str(query.data or "")

    if data.startswith("archive_delete_confirm:"):
        item_id = data.removeprefix("archive_delete_confirm:")
        try:
            item = confirm_archive_delete(item_id, state_store)
        except (KeyError, ValueError):
            await query.edit_message_text("Archived media is no longer available.")
            return

        await query.edit_message_text(
            f"Deleted server-side media: {item.item_id}: {_media_filename(item)}"
        )
        return

    if data.startswith("archive_delete:"):
        item_id = data.removeprefix("archive_delete:")
        try:
            confirmation_text = request_archive_delete(item_id, state_store)
        except (KeyError, ValueError):
            await query.edit_message_text("Archived media is no longer available.")
            return

        await query.edit_message_text(
            confirmation_text,
            reply_markup=build_archive_media_reply_markup(
                build_archive_delete_confirmation_keyboard(item_id)
            ),
        )
        return

    await query.edit_message_text("Archived media action is not available.")


def _media_filename(item: Any) -> str:
    if item.filename:
        return str(item.filename)
    if item.converted_path is not None:
        return item.converted_path.name
    return item.item_id


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
