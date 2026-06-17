from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from typing import Callable, Literal

from rick_tv_server.config import ServerSettings
from rick_tv_server.database import connect_database, ensure_database

RemoteCommandType = Literal["select_channel"]
RemoteCommandStatus = Literal["pending", "completed"]


@dataclass(frozen=True)
class RemoteCommand:
    command_id: str
    command_type: RemoteCommandType
    channel_id: str
    status: RemoteCommandStatus


class RemoteCommandStore:
    def __init__(
        self,
        settings: ServerSettings,
        *,
        command_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.settings = settings
        self._command_id_factory = command_id_factory or (lambda: uuid.uuid4().hex)
        ensure_database(settings)

    def enqueue_select_channel(self, channel_id: str) -> RemoteCommand:
        command_id = self._command_id_factory()
        try:
            with connect_database(self.settings) as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO remote_commands (
                            command_id,
                            command_type,
                            channel_id,
                            status
                        )
                        VALUES (?, 'select_channel', ?, 'pending')
                        """,
                        (command_id, channel_id),
                    )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"remote command already exists: {command_id}") from error

        return self._require_command(command_id)

    def pending_commands(self) -> list[RemoteCommand]:
        with connect_database(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT command_id, command_type, channel_id, status
                FROM remote_commands
                WHERE status = 'pending'
                ORDER BY rowid
                """
            ).fetchall()
        return [self._command_from_row(row) for row in rows]

    def ack_command(self, command_id: str) -> RemoteCommand:
        self._require_command(command_id)
        with connect_database(self.settings) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE remote_commands
                    SET status = 'completed',
                        completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
                    WHERE command_id = ?
                    """,
                    (command_id,),
                )
        return self._require_command(command_id)

    def _require_command(self, command_id: str) -> RemoteCommand:
        with connect_database(self.settings) as connection:
            row = connection.execute(
                """
                SELECT command_id, command_type, channel_id, status
                FROM remote_commands
                WHERE command_id = ?
                """,
                (command_id,),
            ).fetchone()
        if row is None:
            raise KeyError(command_id)
        return self._command_from_row(row)

    def _command_from_row(self, row) -> RemoteCommand:
        return RemoteCommand(
            command_id=row["command_id"],
            command_type=row["command_type"],
            channel_id=row["channel_id"],
            status=row["status"],
        )
