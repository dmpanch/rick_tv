from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from rick_tv_server.config import ServerSettings
from rick_tv_server.database import connect_database, ensure_database
from rick_tv_server.library_paths import relative_media_path, resolve_media_path

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

DELIVERY_STATUSES: tuple[DeliveryStatus, ...] = (
    "uploaded",
    "converting",
    "pending_delivery",
    "available",
    "failed",
    "canceled",
    "pending_device_delete",
    "deleted",
)

VISIBLE_CHANNEL_VIDEO_STATUSES: tuple[DeliveryStatus, ...] = (
    "pending_delivery",
    "available",
)

CHANNEL_DELETE_BLOCKING_STATUSES: tuple[DeliveryStatus, ...] = (
    "uploaded",
    "converting",
    "pending_delivery",
    "available",
    "pending_device_delete",
)


@dataclass
class DeliveryItem:
    item_id: str
    status: DeliveryStatus
    original_path: Path
    channel_id: str
    converted_path: Path | None = None
    filename: str | None = None
    sha256: str | None = None
    failure_message: str | None = None


class DeliveryStateStore:
    def __init__(self, settings: ServerSettings):
        self.settings = settings
        ensure_database(settings)

    @property
    def items(self) -> dict[str, DeliveryItem]:
        with connect_database(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM media_items
                ORDER BY rowid
                """
            ).fetchall()
        return {row["item_id"]: self._item_from_row(row) for row in rows}

    @property
    def last_channel_by_user(self) -> dict[str, str]:
        with connect_database(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT user_id, channel_id
                FROM user_channel_preferences
                ORDER BY user_id
                """
            ).fetchall()
        return {row["user_id"]: row["channel_id"] for row in rows}

    def create_uploaded_item(
        self,
        *,
        item_id: str,
        channel_id: str = "Unassigned",
        original_path: Path,
    ) -> DeliveryItem:
        try:
            with connect_database(self.settings) as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO media_items (
                            item_id,
                            channel_id,
                            status,
                            original_path
                        )
                        VALUES (?, ?, 'uploaded', ?)
                        """,
                        (
                            item_id,
                            channel_id,
                            relative_media_path(self.settings, original_path),
                        ),
                    )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"delivery item already exists: {item_id}") from error

        item = self.get_item(item_id)
        if item is None:
            raise RuntimeError(f"delivery item was not created: {item_id}")
        return item

    def mark_converting(self, item_id: str) -> DeliveryItem:
        item = self._require_item(item_id)
        if item.status != "uploaded":
            raise ValueError(
                f"delivery item must be uploaded before converting: {item_id}"
            )

        self._update_item_status(item_id, "converting")
        return self._require_item(item_id)

    def mark_pending(
        self,
        item_id: str,
        *,
        converted_path: Path,
        filename: str | None = None,
        sha256: str | None = None,
        channel_id: str | None = None,
    ) -> DeliveryItem:
        item = self._require_item(item_id)
        if item.status != "converting":
            raise ValueError(
                f"delivery item must be converting before pending delivery: {item_id}"
            )

        with connect_database(self.settings) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE media_items
                    SET status = 'pending_delivery',
                        converted_path = ?,
                        filename = ?,
                        sha256 = ?,
                        channel_id = COALESCE(?, channel_id)
                    WHERE item_id = ?
                    """,
                    (
                        relative_media_path(self.settings, converted_path),
                        filename,
                        sha256,
                        channel_id,
                        item_id,
                    ),
                )
        return self._require_item(item_id)

    def mark_failed(
        self,
        item_id: str,
        *,
        message: str,
        channel_id: str | None = None,
    ) -> DeliveryItem:
        item = self._require_item(item_id)
        if item.status not in ("uploaded", "converting"):
            raise ValueError(
                f"delivery item must be uploaded or converting before failed: {item_id}"
            )

        with connect_database(self.settings) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE media_items
                    SET status = 'failed',
                        failure_message = ?,
                        channel_id = COALESCE(?, channel_id)
                    WHERE item_id = ?
                    """,
                    (message, channel_id, item_id),
                )
        return self._require_item(item_id)

    def remember_user_channel(self, user_id: str, channel_id: str) -> None:
        with connect_database(self.settings) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO user_channel_preferences (user_id, channel_id)
                    VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET channel_id = excluded.channel_id
                    """,
                    (user_id, channel_id),
                )

    def ready_items_for_channels(self, channel_ids: list[str]) -> list[DeliveryItem]:
        if not channel_ids:
            return []
        placeholders = ",".join("?" for _ in channel_ids)
        with connect_database(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM media_items
                WHERE status = 'pending_delivery'
                  AND channel_id IN ({placeholders})
                ORDER BY rowid
                """,
                tuple(channel_ids),
            ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def list_pending_items(self) -> list[DeliveryItem]:
        with connect_database(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM media_items
                WHERE status = 'pending_delivery'
                ORDER BY rowid
                """
            ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def list_active_items_for_channel(self, channel_id: str) -> list[DeliveryItem]:
        with connect_database(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM media_items
                WHERE channel_id = ?
                  AND status IN ('pending_delivery', 'available')
                ORDER BY rowid
                """,
                (channel_id,),
            ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def cancel_pending_item(self, item_id: str) -> DeliveryItem:
        item = self._require_item(item_id)
        if item.status != "pending_delivery":
            raise ValueError(
                f"delivery item must be pending delivery before cancel: {item_id}"
            )

        self._update_item_status(item_id, "canceled")
        return self._require_item(item_id)

    def ack_item(self, item_id: str) -> DeliveryItem:
        item = self._require_item(item_id)
        if item.status != "pending_delivery":
            raise ValueError(
                f"delivery item must be pending delivery before ack: {item_id}"
            )

        self._update_item_status(item_id, "available")
        return self._require_item(item_id)

    def restore_all_available(self) -> list[DeliveryItem]:
        with connect_database(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM media_items
                WHERE status = 'available'
                ORDER BY rowid
                """
            ).fetchall()
            items = [self._item_from_row(row) for row in rows]
            with connection:
                connection.execute(
                    """
                    UPDATE media_items
                    SET status = 'pending_delivery'
                    WHERE status = 'available'
                    """
                )
        return [replace(item, status="pending_delivery") for item in items]

    def delete_item_from_channel(self, item_id: str) -> DeliveryItem:
        item = self._require_item(item_id)
        if item.status not in VISIBLE_CHANNEL_VIDEO_STATUSES:
            raise ValueError(f"delivery item must be active before channel delete: {item_id}")
        if item.filename is None and item.converted_path is None:
            raise ValueError(f"delivery item is missing filename: {item_id}")

        moved_paths: list[tuple[Path, Path]] = []
        try:
            moved_paths = self._quarantine_server_side_media(item)
            self._update_item_status(item_id, "pending_device_delete")
        except Exception:
            self._restore_quarantined_media(moved_paths)
            raise

        self._delete_quarantined_media(moved_paths)
        return self._require_item(item_id)

    def device_delete_items_for_channels(
        self,
        channel_ids: list[str],
    ) -> list[DeliveryItem]:
        if not channel_ids:
            return []
        placeholders = ",".join("?" for _ in channel_ids)
        with connect_database(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM media_items
                WHERE status = 'pending_device_delete'
                  AND channel_id IN ({placeholders})
                ORDER BY rowid
                """,
                tuple(channel_ids),
            ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def ack_device_delete(self, item_id: str) -> DeliveryItem:
        item = self._require_item(item_id)
        if item.status != "pending_device_delete":
            raise ValueError(
                f"delivery item must be pending device delete before device ack: {item_id}"
            )

        self._update_item_status(item_id, "deleted")
        return self._require_item(item_id)

    def get_item(self, item_id: str) -> DeliveryItem | None:
        with connect_database(self.settings) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM media_items
                WHERE item_id = ?
                """,
                (item_id,),
            ).fetchone()
        return self._item_from_row(row) if row is not None else None

    def has_active_media_for_channel(self, channel_id: str) -> bool:
        with connect_database(self.settings) as connection:
            count = connection.execute(
                """
                SELECT COUNT(*)
                FROM media_items
                WHERE channel_id = ?
                  AND status IN (
                      'uploaded',
                      'converting',
                      'pending_delivery',
                      'available',
                      'pending_device_delete'
                  )
                """,
                (channel_id,),
            ).fetchone()[0]
        return bool(count)

    def _require_item(self, item_id: str) -> DeliveryItem:
        item = self.get_item(item_id)
        if item is None:
            raise KeyError(item_id)
        return item

    def _update_item_status(self, item_id: str, status: DeliveryStatus) -> None:
        with connect_database(self.settings) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE media_items
                    SET status = ?
                    WHERE item_id = ?
                    """,
                    (status, item_id),
                )

    def _item_from_row(self, row: sqlite3.Row) -> DeliveryItem:
        converted_path = row["converted_path"]
        return DeliveryItem(
            item_id=row["item_id"],
            channel_id=row["channel_id"],
            status=row["status"],
            original_path=resolve_media_path(self.settings, row["original_path"]),
            converted_path=(
                resolve_media_path(self.settings, converted_path)
                if converted_path is not None
                else None
            ),
            filename=row["filename"],
            sha256=row["sha256"],
            failure_message=row["failure_message"],
        )

    def _server_side_media_paths(self, item: DeliveryItem) -> list[Path]:
        paths: list[Path] = []
        for media_path in (item.converted_path, item.original_path):
            if media_path is None or media_path in paths:
                continue
            if not self._is_server_media_path(media_path):
                continue
            if media_path.exists() and media_path.is_file():
                paths.append(media_path)
        return paths

    def _is_server_media_path(self, media_path: Path) -> bool:
        try:
            media_path.resolve(strict=False).relative_to(
                self.settings.media_dir.resolve(strict=False)
            )
        except ValueError:
            return False
        return True

    def _quarantine_server_side_media(self, item: DeliveryItem) -> list[tuple[Path, Path]]:
        moved_paths: list[tuple[Path, Path]] = []
        quarantine_dir = self.settings.media_dir / ".pending_device_delete" / item.item_id
        for index, media_path in enumerate(self._server_side_media_paths(item)):
            quarantine_path = quarantine_dir / f"{index}-{media_path.name}"
            quarantine_path.parent.mkdir(parents=True, exist_ok=True)
            media_path.replace(quarantine_path)
            moved_paths.append((quarantine_path, media_path))
        return moved_paths

    def _restore_quarantined_media(self, moved_paths: list[tuple[Path, Path]]) -> None:
        for quarantine_path, media_path in reversed(moved_paths):
            if not quarantine_path.exists() or media_path.exists():
                continue
            media_path.parent.mkdir(parents=True, exist_ok=True)
            quarantine_path.replace(media_path)

    def _delete_quarantined_media(self, moved_paths: list[tuple[Path, Path]]) -> None:
        for quarantine_path, _media_path in moved_paths:
            try:
                quarantine_path.unlink(missing_ok=True)
            except OSError:
                pass
