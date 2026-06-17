from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from rick_tv_server.config import ServerSettings
from rick_tv_server.database import connect_database, ensure_database

CHANNEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class ChannelRegistry:
    channels: dict[str, dict[str, str]]


class ChannelRegistryStore:
    def __init__(self, settings: ServerSettings) -> None:
        self.settings = settings
        ensure_database(settings)

    def load(self) -> ChannelRegistry:
        with connect_database(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT channel_id, display_name
                FROM channels
                ORDER BY channel_id
                """
            ).fetchall()
        return ChannelRegistry(
            channels={
                row["channel_id"]: {"display_name": row["display_name"]}
                for row in rows
            }
        )

    def add_channel(self, channel_id: str, display_name: str) -> None:
        _validate_channel_id(channel_id)
        try:
            with connect_database(self.settings) as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO channels (channel_id, display_name)
                        VALUES (?, ?)
                        """,
                        (channel_id, display_name),
                    )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"channel already exists: {channel_id}") from error

    def rename_channel(self, channel_id: str, display_name: str) -> None:
        with connect_database(self.settings) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE channels
                    SET display_name = ?
                    WHERE channel_id = ?
                    """,
                    (display_name, channel_id),
                )
        if cursor.rowcount == 0:
            raise ValueError(f"unknown channel_id: {channel_id}")

    def delete_channel(self, channel_id: str, state_store: Any = None) -> None:
        if channel_id not in self.load().channels:
            raise ValueError(f"unknown channel_id: {channel_id}")
        if state_store is not None and _has_active_media(state_store, channel_id):
            raise ValueError(f"channel has active media references: {channel_id}")

        with connect_database(self.settings) as connection:
            with connection:
                connection.execute(
                    """
                    DELETE FROM channels
                    WHERE channel_id = ?
                    """,
                    (channel_id,),
                )

    def dump_payload(self) -> dict[str, dict[str, dict[str, str]]]:
        return {"channels": self.load().channels}


def _validate_channel_id(channel_id: str) -> None:
    if not CHANNEL_ID_PATTERN.fullmatch(channel_id):
        raise ValueError(f"invalid channel_id: {channel_id}")


def _has_active_media(state_store: Any, channel_id: str) -> bool:
    has_active_media = getattr(state_store, "has_active_media_for_channel", None)
    if has_active_media is not None:
        return bool(has_active_media(channel_id))

    for item in getattr(state_store, "items", {}).values():
        if getattr(item, "channel_id", None) != channel_id:
            continue
        if getattr(item, "status", None) in {
            "uploaded",
            "converting",
            "pending_delivery",
            "available",
            "pending_device_delete",
        }:
            return True
    return False
