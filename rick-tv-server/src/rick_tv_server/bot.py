from __future__ import annotations

import asyncio
import os
import re
import tempfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from rick_tv_server.channels import ChannelRegistryStore
from rick_tv_server.config import ServerSettings
from rick_tv_server.remote import RemoteCommandStore
from rick_tv_server.uploads import UploadProcessingError


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
        label = channel_label(channel.id, channel.display_name)
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


def build_restore_confirmation_keyboard() -> Keyboard:
    return [
        [
            {
                "text": "Confirm restore all",
                "callback_data": "restore_all_confirm",
            }
        ]
    ]


def build_channel_list_keyboard(channel_store: ChannelRegistryStore) -> Keyboard:
    registry = channel_store.load()
    keyboard: Keyboard = []
    for channel_id, metadata in registry.channels.items():
        keyboard.append(
            [
                {
                    "text": channel_label(channel_id, metadata["display_name"]),
                    "callback_data": f"channel_view:{channel_id}",
                }
            ]
        )
    return keyboard


def build_selected_channel_keyboard(channel_id: str) -> Keyboard:
    return [
        [{"text": "Switch channel on Pi", "callback_data": f"channel_switch:{channel_id}"}],
        [{"text": "List all videos", "callback_data": f"channel_videos:{channel_id}"}],
        [{"text": "Rename channel", "callback_data": f"channel_rename:{channel_id}"}],
        [{"text": "Delete channel", "callback_data": f"channel_delete:{channel_id}"}],
        [{"text": "Back to list", "callback_data": "channel_list"}],
    ]


def build_channel_video_list_keyboard(channel_id: str, state_store: Any) -> Keyboard:
    keyboard: Keyboard = []
    for item in _channel_video_items(state_store, channel_id):
        keyboard.append(
            [
                {
                    "text": _media_filename(item),
                    "callback_data": f"channel_video:{item.item_id}",
                }
            ]
        )
    keyboard.append(
        [{"text": "Back to channel", "callback_data": f"channel_view:{channel_id}"}]
    )
    return keyboard


def build_selected_video_keyboard(item: Any) -> Keyboard:
    return [
        [
            {
                "text": "Download",
                "callback_data": f"channel_video_download:{item.item_id}",
            }
        ],
        [
            {
                "text": "Delete",
                "callback_data": f"channel_video_delete:{item.item_id}",
            }
        ],
        [{"text": "Back", "callback_data": f"channel_videos:{item.channel_id}"}],
    ]


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


def channel_label(channel_id: str, display_name: str) -> str:
    match = re.match(r"^(\d+)", channel_id)
    if match is None:
        return display_name
    return f"{match.group(1)} - {display_name}"


def format_channel_list(channel_store: ChannelRegistryStore) -> str:
    registry = channel_store.load()
    if not registry.channels:
        return "No channels."

    lines = ["Channels:"]
    for channel_id, metadata in registry.channels.items():
        lines.append(f"- {channel_label(channel_id, metadata['display_name'])}")
    return "\n".join(lines)


def format_selected_channel(channel_store: ChannelRegistryStore, channel_id: str) -> str:
    registry = channel_store.load()
    metadata = registry.channels.get(channel_id)
    if metadata is None:
        return "Channel is not available."
    return f"Channel: {channel_label(channel_id, metadata['display_name'])}"


def format_channel_video_list(
    channel_store: ChannelRegistryStore,
    state_store: Any,
    channel_id: str,
) -> str:
    channel_text = format_selected_channel(channel_store, channel_id)
    if channel_text == "Channel is not available.":
        return channel_text

    label = channel_text.removeprefix("Channel: ")
    items = _channel_video_items(state_store, channel_id)
    if not items:
        return f"No videos in {label}."

    lines = [f"Videos in {label}:"]
    for item in items:
        lines.append(f"- {_media_filename(item)}")
    return "\n".join(lines)


def format_selected_video(item: Any) -> str:
    return f"Video: {_media_filename(item)}"


def next_channel_id(channel_store: ChannelRegistryStore, display_name: str) -> str:
    registry = channel_store.load()
    next_index = 1
    for channel_id in registry.channels:
        match = re.match(r"^(\d+)", channel_id)
        if match is not None:
            next_index = max(next_index, int(match.group(1)) + 1)

    slug = _channel_slug(display_name)
    while True:
        candidate = f"{next_index:02d}_{slug}"
        if candidate not in registry.channels:
            return candidate
        next_index += 1


def _channel_slug(display_name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", display_name)
    if not words:
        return "Channel"
    return "_".join(words)


def format_pending_media_list(pending_items: list[Any]) -> str:
    if not pending_items:
        return "No pending media."

    lines = ["Pending media:"]
    for item in pending_items:
        lines.append(f"- {item.item_id}: {_media_filename(item)}")
    return "\n".join(lines)


def cancel_pending_media(item_id: str, state_store: Any) -> Any:
    return state_store.cancel_pending_item(item_id)


async def handle_add_channel_command(
    update: Any,
    context: Any,
    channel_store: ChannelRegistryStore,
    *,
    allowed_user_ids: tuple[int, ...],
) -> None:
    if not await _ensure_authorized(update, allowed_user_ids):
        return

    context.user_data["channel_action"] = {"type": "add"}
    await update.message.reply_text(
        "Send channel display name.",
    )


async def handle_list_channels_command(
    update: Any,
    context: Any,
    channel_store: ChannelRegistryStore,
    *,
    allowed_user_ids: tuple[int, ...],
) -> None:
    del context

    if not await _ensure_authorized(update, allowed_user_ids):
        return

    await update.message.reply_text(
        format_channel_list(channel_store),
        reply_markup=_build_reply_markup(build_channel_list_keyboard(channel_store)),
    )


async def handle_restore_all_videos_command(
    update: Any,
    context: Any,
    state_store: Any,
    *,
    allowed_user_ids: tuple[int, ...],
) -> None:
    del context, state_store

    if not await _ensure_authorized(update, allowed_user_ids):
        return

    await update.message.reply_text(
        "Confirm restore all available library media.",
        reply_markup=_build_reply_markup(build_restore_confirmation_keyboard()),
    )


async def handle_channel_callback(
    update: Any,
    context: Any,
    channel_store: ChannelRegistryStore,
    state_store: Any,
    remote_command_store: Any | None = None,
    *,
    allowed_user_ids: tuple[int, ...],
) -> None:
    if not await _ensure_authorized(update, allowed_user_ids):
        return

    query = update.callback_query
    await query.answer()
    data = str(query.data or "")

    if data == "channel_list":
        await query.edit_message_text(
            format_channel_list(channel_store),
            reply_markup=_build_reply_markup(build_channel_list_keyboard(channel_store)),
        )
        return

    if data.startswith("channel_view:"):
        channel_id = data.removeprefix("channel_view:")
        await query.edit_message_text(
            format_selected_channel(channel_store, channel_id),
            reply_markup=_build_reply_markup(build_selected_channel_keyboard(channel_id)),
        )
        return

    if data.startswith("channel_switch:"):
        channel_id = data.removeprefix("channel_switch:")
        label = format_selected_channel(channel_store, channel_id).removeprefix(
            "Channel: "
        )
        if label == "Channel is not available.":
            await query.edit_message_text("Channel is not available.")
            return
        if remote_command_store is None:
            await query.edit_message_text("Remote command store is not available.")
            return
        remote_command_store.enqueue_select_channel(channel_id)
        await query.edit_message_text(f"Queued switch to {label} on Pi.")
        return

    if data.startswith("channel_videos:"):
        channel_id = data.removeprefix("channel_videos:")
        await query.edit_message_text(
            format_channel_video_list(channel_store, state_store, channel_id),
            reply_markup=_build_reply_markup(
                build_channel_video_list_keyboard(channel_id, state_store)
            ),
        )
        return

    if data.startswith("channel_video_download:"):
        item_id = data.removeprefix("channel_video_download:")
        item = _active_channel_video_item(state_store, item_id)
        if item is None:
            await query.edit_message_text("Video is not available.")
            return

        converted_path = getattr(item, "converted_path", None)
        if converted_path is None or not converted_path.exists():
            await query.edit_message_text("Video file is not available.")
            return

        message = getattr(query, "message", None)
        if message is None:
            await query.edit_message_text("Video message is not available.")
            return

        with converted_path.open("rb") as media_file:
            await message.reply_video(
                video=media_file,
                filename=_media_filename(item),
            )
        return

    if data.startswith("channel_video_delete:"):
        item_id = data.removeprefix("channel_video_delete:")
        try:
            item = state_store.delete_item_from_channel(item_id)
        except (KeyError, ValueError):
            await query.edit_message_text("Video is not available.")
            return

        channel_id = str(item.channel_id)
        await query.edit_message_text(
            f"Deleted {_media_filename(item)}.\n\n"
            f"{format_channel_video_list(channel_store, state_store, channel_id)}",
            reply_markup=_build_reply_markup(
                build_channel_video_list_keyboard(channel_id, state_store)
            ),
        )
        return

    if data.startswith("channel_video:"):
        item_id = data.removeprefix("channel_video:")
        item = _active_channel_video_item(state_store, item_id)
        if item is None:
            await query.edit_message_text("Video is not available.")
            return

        await query.edit_message_text(
            format_selected_video(item),
            reply_markup=_build_reply_markup(build_selected_video_keyboard(item)),
        )
        return

    if data == "channel_add":
        context.user_data["channel_action"] = {"type": "add"}
        await query.edit_message_text("Send channel display name.")
        return

    if data.startswith("channel_rename:"):
        channel_id = data.removeprefix("channel_rename:")
        context.user_data["channel_action"] = {
            "type": "rename",
            "channel_id": channel_id,
        }
        await query.edit_message_text(
            f"Send new display name for {format_selected_channel(channel_store, channel_id)}."
        )
        return

    if data.startswith("channel_delete_confirm:"):
        channel_id = data.removeprefix("channel_delete_confirm:")
        label = format_selected_channel(channel_store, channel_id).removeprefix(
            "Channel: "
        )
        try:
            channel_store.delete_channel(channel_id, state_store=state_store)
        except ValueError as error:
            await query.edit_message_text(str(error))
            return
        await query.edit_message_text(f"Deleted channel {label}.")
        return

    if data.startswith("channel_delete:"):
        channel_id = data.removeprefix("channel_delete:")
        label = format_selected_channel(channel_store, channel_id).removeprefix(
            "Channel: "
        )
        await query.edit_message_text(
            f"Confirm delete channel {label}.",
            reply_markup=_build_reply_markup(
                [
                    [
                        {
                            "text": "Confirm",
                            "callback_data": f"channel_delete_confirm:{channel_id}",
                        }
                    ],
                    [
                        {
                            "text": "Back to channel",
                            "callback_data": f"channel_view:{channel_id}",
                        }
                    ],
                ]
            ),
        )
        return

    await query.edit_message_text("Channel action is not available.")


async def handle_channel_text(
    update: Any,
    context: Any,
    channel_store: ChannelRegistryStore,
    *,
    allowed_user_ids: tuple[int, ...],
) -> None:
    if not await _ensure_authorized(update, allowed_user_ids):
        return

    action = context.user_data.get("channel_action")
    if not isinstance(action, dict):
        return

    text = str(update.message.text or "").strip()
    action_type = action.get("type")
    try:
        if action_type == "add":
            display_name = text
            channel_id = next_channel_id(channel_store, display_name)
            channel_store.add_channel(channel_id, display_name)
            await update.message.reply_text(
                f"Added channel {channel_label(channel_id, display_name)}."
            )
        elif action_type == "rename":
            channel_id = str(action["channel_id"])
            channel_store.rename_channel(channel_id, text)
            await update.message.reply_text(
                f"Renamed channel {channel_label(channel_id, text)}."
            )
        else:
            return
    except ValueError as error:
        await update.message.reply_text(str(error))
        return
    finally:
        context.user_data.pop("channel_action", None)


async def handle_upload_channel_callback(
    update: Any,
    context: Any,
    settings: ServerSettings,
    state_store: Any,
    upload_processor: Any,
    channel_store: ChannelRegistryStore,
    *,
    allowed_user_ids: tuple[int, ...],
) -> None:
    if not await _ensure_authorized(update, allowed_user_ids):
        return

    query = update.callback_query
    await query.answer()
    channel_id = str(query.data or "").removeprefix("upload_channel:")
    context.user_data["upload_channel_id"] = channel_id
    remember_user_channel(update.effective_user.id, channel_id, state_store)

    pending_upload = context.user_data.get("pending_upload")
    if isinstance(pending_upload, dict):
        await _process_pending_upload(
            update,
            context,
            settings,
            upload_processor,
            channel_id,
            pending_upload,
        )
        return

    await query.edit_message_text(
        f"Send a video or document for {format_selected_channel(channel_store, channel_id)}."
    )


async def handle_upload_attachment(
    update: Any,
    context: Any,
    settings: ServerSettings,
    upload_processor: Any,
    channel_store: ChannelRegistryStore,
    state_store: Any,
    *,
    allowed_user_ids: tuple[int, ...],
) -> None:
    if not await _ensure_authorized(update, allowed_user_ids):
        return

    attachment = getattr(update.message, "video", None) or getattr(
        update.message,
        "document",
        None,
    )
    if attachment is None:
        await update.message.reply_text("Send a video or document.")
        return

    original_filename = Path(
        getattr(attachment, "file_name", None) or "telegram-upload.mp4"
    ).name
    temp_path = _temporary_upload_path(settings, original_filename)
    try:
        telegram_file = await attachment.get_file()
        await telegram_file.download_to_drive(temp_path)
    except Exception:
        await update.message.reply_text("Upload failed.")
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        return

    channel_id = context.user_data.get("upload_channel_id")
    if isinstance(channel_id, str) and channel_id:
        pending_upload = {
            "temp_path": str(temp_path),
            "original_filename": original_filename,
        }
        await _process_pending_upload(
            update,
            context,
            settings,
            upload_processor,
            channel_id,
            pending_upload,
        )
        return

    _cleanup_pending_upload(context)
    context.user_data["pending_upload"] = {
        "temp_path": str(temp_path),
        "original_filename": original_filename,
    }
    channels = channel_choices_from_registry(channel_store)
    if not channels:
        _cleanup_pending_upload(context)
        await update.message.reply_text("No channels. Add one with /add_channel first.")
        return

    user_id = str(update.effective_user.id)
    remembered_channel_id = state_store.last_channel_by_user.get(user_id)
    await update.message.reply_text(
        f"Choose a channel for {original_filename}.",
        reply_markup=build_upload_channel_reply_markup(
            build_upload_channel_keyboard(channels, remembered_channel_id)
        ),
    )


async def handle_restore_callback(
    update: Any,
    context: Any,
    state_store: Any,
    *,
    allowed_user_ids: tuple[int, ...],
) -> None:
    del context

    if not await _ensure_authorized(update, allowed_user_ids):
        return

    query = update.callback_query
    await query.answer()
    data = str(query.data or "")

    if data == "restore_all":
        await query.edit_message_text(
            "Confirm restore all available library media.",
            reply_markup=_build_reply_markup(build_restore_confirmation_keyboard()),
        )
        return

    if data == "restore_all_confirm":
        restored = state_store.restore_all_available()
        noun = "media item" if len(restored) == 1 else "media items"
        await query.edit_message_text(f"Requeued {len(restored)} {noun}.")
        return

    await query.edit_message_text("Restore action is not available.")


def _media_filename(item: Any) -> str:
    if item.filename:
        return str(item.filename)
    if item.converted_path is not None:
        return item.converted_path.name
    return item.item_id


def _channel_video_items(state_store: Any, channel_id: str) -> list[Any]:
    items = state_store.list_active_items_for_channel(channel_id)
    return sorted(items, key=_media_filename)


def _active_channel_video_item(state_store: Any, item_id: str) -> Any | None:
    item = state_store.get_item(item_id)
    if item is None:
        return None
    if getattr(item, "status", None) not in {"pending_delivery", "available"}:
        return None
    if getattr(item, "channel_id", None) is None:
        return None
    return item


def remember_user_channel(
    user_id: int | str,
    channel_id: str,
    state_store: Any,
) -> None:
    state_store.remember_user_channel(str(user_id), channel_id)


def channel_choices_from_registry(
    channel_store: ChannelRegistryStore,
) -> list[ChannelChoice]:
    registry = channel_store.load()
    return [
        ChannelChoice(id=channel_id, display_name=metadata["display_name"])
        for channel_id, metadata in registry.channels.items()
    ]


def build_application(
    settings: ServerSettings,
    channel_store: ChannelRegistryStore,
    state_store: Any,
    upload_processor: Any,
) -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("RICK_TV_TELEGRAM_BOT_TOKEN must be set for bot runner")

    allowed_user_ids = settings.telegram_allowed_user_ids
    remote_command_store = RemoteCommandStore(settings)
    builder = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(configure_bot_command_menu)
    )
    if settings.telegram_local_api_url:
        base_url = settings.telegram_local_api_url.rstrip("/")
        builder.base_url(f"{base_url}/bot").base_file_url(
            f"{base_url}/file/bot"
        ).local_mode(True).read_timeout(300).media_write_timeout(300)
    application = builder.build()
    application.add_handler(
        CommandHandler(
            "add_channel",
            partial(
                handle_add_channel_command,
                channel_store=channel_store,
                allowed_user_ids=allowed_user_ids,
            ),
        )
    )
    application.add_handler(
        CommandHandler(
            "list_channels",
            partial(
                handle_list_channels_command,
                channel_store=channel_store,
                allowed_user_ids=allowed_user_ids,
            ),
        )
    )
    application.add_handler(
        CommandHandler(
            "restore_all_videos",
            partial(
                handle_restore_all_videos_command,
                state_store=state_store,
                allowed_user_ids=allowed_user_ids,
            ),
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            partial(
                handle_channel_callback,
                channel_store=channel_store,
                state_store=state_store,
                remote_command_store=remote_command_store,
                allowed_user_ids=allowed_user_ids,
            ),
            pattern=r"^channel_",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            partial(
                handle_upload_channel_callback,
                settings=settings,
                state_store=state_store,
                upload_processor=upload_processor,
                channel_store=channel_store,
                allowed_user_ids=allowed_user_ids,
            ),
            pattern=r"^upload_channel:",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            partial(
                handle_restore_callback,
                state_store=state_store,
                allowed_user_ids=allowed_user_ids,
            ),
            pattern=r"^restore_all",
        )
    )
    application.add_handler(
        MessageHandler(
            filters.VIDEO | filters.Document.ALL,
            partial(
                handle_upload_attachment,
                settings=settings,
                upload_processor=upload_processor,
                channel_store=channel_store,
                state_store=state_store,
                allowed_user_ids=allowed_user_ids,
            ),
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            partial(
                handle_channel_text,
                channel_store=channel_store,
                allowed_user_ids=allowed_user_ids,
            ),
        )
    )
    return application


async def configure_bot_command_menu(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("add_channel", "Add channel"),
            BotCommand("list_channels", "List channels"),
            BotCommand("restore_all_videos", "Restore all videos"),
        ]
    )


def _temporary_upload_path(settings: ServerSettings, original_filename: str) -> Path:
    temp_dir = settings.media_dir / ".telegram_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_filename).suffix
    fd, tmp_name = tempfile.mkstemp(prefix="telegram-", suffix=suffix, dir=temp_dir)
    os.close(fd)
    return Path(tmp_name)


async def _process_pending_upload(
    update: Any,
    context: Any,
    settings: ServerSettings,
    upload_processor: Any,
    channel_id: str,
    pending_upload: dict[Any, Any],
) -> None:
    del settings
    temp_path = Path(str(pending_upload.get("temp_path", "")))
    original_filename = Path(
        str(pending_upload.get("original_filename") or "telegram-upload.mp4")
    ).name
    try:
        item = await asyncio.to_thread(
            upload_processor.process_upload,
            channel_id=channel_id,
            source_path=temp_path,
            original_filename=original_filename,
        )
    except UploadProcessingError as exc:
        await _send_upload_result(update, str(exc))
        return
    except Exception:
        await _send_upload_result(update, "Upload failed.")
        return
    finally:
        _cleanup_pending_upload(context)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass

    await _send_upload_result(update, f"Upload accepted: {item.item_id}.")


async def _send_upload_result(update: Any, text: str) -> None:
    if getattr(update, "callback_query", None) is not None:
        await update.callback_query.edit_message_text(text)
        return
    await update.message.reply_text(text)


def _cleanup_pending_upload(context: Any) -> None:
    pending_upload = context.user_data.pop("pending_upload", None)
    context.user_data.pop("upload_channel_id", None)
    if not isinstance(pending_upload, dict):
        return
    temp_path = pending_upload.get("temp_path")
    if not isinstance(temp_path, str):
        return
    try:
        Path(temp_path).unlink()
    except FileNotFoundError:
        pass


async def _ensure_authorized(
    update: Any,
    allowed_user_ids: tuple[int, ...],
) -> bool:
    user = getattr(update, "effective_user", None)
    user_id = getattr(user, "id", None)
    if isinstance(user_id, int) and user_id in allowed_user_ids:
        return True

    if getattr(update, "message", None) is not None:
        await update.message.reply_text("Unauthorized.")
    elif getattr(update, "callback_query", None) is not None:
        await update.callback_query.answer("Unauthorized.")
    return False
