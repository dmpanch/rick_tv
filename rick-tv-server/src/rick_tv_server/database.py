from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import yaml

from rick_tv_server.config import ServerSettings
from rick_tv_server.library_paths import (
    legacy_library_paths,
    relative_media_path,
    unique_delivery_filename,
)

DEFAULT_DB_FILENAME = "rick-tv.sqlite3"
LEGACY_CONTAINER_MEDIA_ROOT = Path("/var/lib/rick-tv/media")

VALID_STATUSES = (
    "uploaded",
    "converting",
    "pending_delivery",
    "available",
    "failed",
    "canceled",
    "pending_device_delete",
    "deleted",
)

LEGACY_STATUS_MAP = {
    "uploaded": "uploaded",
    "converting": "converting",
    "pending": "pending_delivery",
    "failed": "failed",
    "canceled": "canceled",
    "delivered": "available",
    "archived": "available",
    "deleted_server_side": "pending_device_delete",
    "deleted_from_library": "deleted",
}


def database_path(settings: ServerSettings) -> Path:
    return settings.db_path or settings.state_dir / DEFAULT_DB_FILENAME


@contextmanager
def connect_database(settings: ServerSettings) -> Iterator[sqlite3.Connection]:
    path = database_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
    finally:
        connection.close()


def ensure_database(settings: ServerSettings) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = settings.state_dir / ".sqlite-migration.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            with connect_database(settings) as connection:
                _create_schema(connection)
                if _database_is_empty(connection):
                    _migrate_legacy_state(settings, connection)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _create_schema(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS media_items (
                item_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'uploaded',
                        'converting',
                        'pending_delivery',
                        'available',
                        'failed',
                        'canceled',
                        'pending_device_delete',
                        'deleted'
                    )
                ),
                original_path TEXT NOT NULL,
                converted_path TEXT,
                filename TEXT,
                sha256 TEXT,
                failure_message TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_channel_preferences (
                user_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL
            )
            """
        )


def _database_is_empty(connection: sqlite3.Connection) -> bool:
    for table_name in ("channels", "media_items", "user_channel_preferences"):
        count = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        if count:
            return False
    return True


def _migrate_legacy_state(
    settings: ServerSettings,
    connection: sqlite3.Connection,
) -> None:
    channels_path = settings.channels_path or settings.config_dir / "channels.yml"
    queue_path = settings.state_dir / "queue.json"
    legacy_channels = _load_legacy_channels(channels_path)
    legacy_state = _load_legacy_queue(queue_path)
    legacy_items = legacy_state.get("items", {})
    if not legacy_channels and not legacy_items:
        return

    used_filenames_by_channel: dict[str, set[str]] = {}
    imported_items = []
    legacy_sources_to_delete: set[Path] = set()
    for item_id, raw_item in legacy_items.items():
        if not isinstance(raw_item, dict):
            continue
        item_id = str(raw_item.get("item_id") or item_id)
        channel_id = str(raw_item.get("channel_id") or "Unassigned")
        status = LEGACY_STATUS_MAP.get(str(raw_item.get("status")), "failed")
        original_source = _legacy_media_path(settings, raw_item.get("original_path"))
        converted_source = _legacy_media_path(settings, raw_item.get("converted_path"))
        original_filename = (
            original_source.name if original_source is not None else f"{item_id}.original"
        )
        legacy_filename = str(
            raw_item.get("filename")
            or (converted_source.name if converted_source is not None else f"{item_id}.mp4")
        )
        used_filenames = used_filenames_by_channel.setdefault(channel_id, set())
        delivery_filename = unique_delivery_filename(
            filename=legacy_filename,
            item_id=item_id,
            used_filenames=used_filenames,
        )
        original_path, converted_path = legacy_library_paths(
            settings,
            channel_id=channel_id,
            item_id=item_id,
            original_filename=original_filename,
            delivery_filename=delivery_filename,
        )

        _copy_if_present(original_source, original_path)
        _copy_if_present(converted_source, converted_path)
        if converted_source is None and original_source is not None:
            _copy_if_present(original_source, converted_path)

        for legacy_path in (original_source, converted_source):
            if _is_legacy_media_file(settings, legacy_path):
                legacy_sources_to_delete.add(legacy_path)

        imported_items.append(
            {
                "item_id": item_id,
                "channel_id": channel_id,
                "status": status,
                "original_path": relative_media_path(settings, original_path),
                "converted_path": relative_media_path(settings, converted_path),
                "filename": delivery_filename,
                "sha256": _sha256_file(converted_path) if converted_path.exists() else None,
                "failure_message": raw_item.get("failure_message"),
            }
        )
        legacy_channels.setdefault(channel_id, {"display_name": channel_id})

    with connection:
        for channel_id, metadata in legacy_channels.items():
            connection.execute(
                """
                INSERT OR IGNORE INTO channels (channel_id, display_name)
                VALUES (?, ?)
                """,
                (channel_id, metadata["display_name"]),
            )
        for item in imported_items:
            connection.execute(
                """
                INSERT INTO media_items (
                    item_id,
                    channel_id,
                    status,
                    original_path,
                    converted_path,
                    filename,
                    sha256,
                    failure_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["item_id"],
                    item["channel_id"],
                    item["status"],
                    item["original_path"],
                    item["converted_path"],
                    item["filename"],
                    item["sha256"],
                    item["failure_message"],
                ),
            )
        for user_id, channel_id in _legacy_preferences(legacy_state).items():
            connection.execute(
                """
                INSERT OR REPLACE INTO user_channel_preferences (user_id, channel_id)
                VALUES (?, ?)
                """,
                (user_id, channel_id),
            )

    for legacy_path in legacy_sources_to_delete:
        if legacy_path.exists() and legacy_path.is_file():
            legacy_path.unlink()
    queue_path.unlink(missing_ok=True)
    channels_path.unlink(missing_ok=True)


def _load_legacy_channels(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    raw_channels = data.get("channels")
    if not isinstance(raw_channels, dict):
        return {}

    channels: dict[str, dict[str, str]] = {}
    for channel_id, metadata in raw_channels.items():
        if not isinstance(channel_id, str) or not isinstance(metadata, dict):
            continue
        display_name = metadata.get("display_name")
        if isinstance(display_name, str):
            channels[channel_id] = {"display_name": display_name}
    return channels


def _load_legacy_queue(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _legacy_preferences(data: dict[str, object]) -> dict[str, str]:
    raw_preferences = data.get("last_channel_by_user")
    if not isinstance(raw_preferences, dict):
        return {}

    preferences: dict[str, str] = {}
    for user_id, channel_id in raw_preferences.items():
        user_id = str(user_id)
        if not user_id.isdigit() or not isinstance(channel_id, str):
            continue
        preferences[user_id] = channel_id
    return preferences


def _legacy_media_path(settings: ServerSettings, value: object) -> Path | None:
    if value is None:
        return None
    path = Path(str(value))
    if path.is_absolute():
        try:
            return settings.media_dir / path.relative_to(LEGACY_CONTAINER_MEDIA_ROOT)
        except ValueError:
            return path
    return settings.media_dir / path


def _copy_if_present(source: Path | None, destination: Path) -> None:
    if source is None or not source.exists() or not source.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve(strict=False) == destination.resolve(strict=False):
        return
    shutil.copy2(source, destination)


def _is_legacy_media_file(settings: ServerSettings, path: Path | None) -> bool:
    if path is None or not path.exists() or not path.is_file():
        return False
    try:
        path.resolve(strict=False).relative_to(settings.media_dir.resolve(strict=False))
    except ValueError:
        return False
    try:
        path.resolve(strict=False).relative_to(
            (settings.media_dir / "library").resolve(strict=False)
        )
    except ValueError:
        return True
    return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as media_file:
        for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
