from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterator
from typing import Literal

from rick_tv_server.config import ServerSettings

DeliveryStatus = Literal[
    "uploaded",
    "converting",
    "pending",
    "canceled",
    "delivered",
    "archived",
    "deleted_server_side",
    "deleted_from_library",
]

DELIVERY_STATUSES: tuple[DeliveryStatus, ...] = (
    "uploaded",
    "converting",
    "pending",
    "canceled",
    "delivered",
    "archived",
    "deleted_server_side",
    "deleted_from_library",
)


@dataclass
class DeliveryItem:
    item_id: str
    user_id: str
    status: DeliveryStatus
    original_path: Path
    converted_path: Path | None = None
    source_message_id: int | None = None
    channel_id: str | None = None
    filename: str | None = None
    sha256: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, object]) -> "DeliveryItem":
        converted_path = data.get("converted_path")
        return cls(
            item_id=str(data["item_id"]),
            user_id=str(data["user_id"]),
            status=data["status"],  # type: ignore[arg-type]
            original_path=Path(str(data["original_path"])),
            converted_path=Path(str(converted_path)) if converted_path is not None else None,
            source_message_id=data.get("source_message_id"),  # type: ignore[arg-type]
            channel_id=data.get("channel_id"),  # type: ignore[arg-type]
            filename=data.get("filename"),  # type: ignore[arg-type]
            sha256=data.get("sha256"),  # type: ignore[arg-type]
        )

    def to_json(self) -> dict[str, object]:
        data = asdict(self)
        data["original_path"] = str(self.original_path)
        data["converted_path"] = str(self.converted_path) if self.converted_path is not None else None
        return data


class DeliveryStateStore:
    def __init__(self, settings: ServerSettings):
        self.settings = settings
        self.state_path = settings.state_dir / "queue.json"
        self.lock_path = settings.state_dir / ".queue.lock"
        self.items: dict[str, DeliveryItem] = {}
        self.last_channel_by_user: dict[str, str] = {}
        self.acknowledgements: dict[str, object] = {}
        self.archive_index: dict[str, object] = {}
        self.archive_delete_requests: dict[str, object] = {}
        self._load()

    def create_uploaded_item(
        self,
        *,
        item_id: str,
        user_id: str,
        original_path: Path,
        source_message_id: int | None = None,
    ) -> DeliveryItem:
        with self._locked_state():
            if item_id in self.items:
                raise ValueError(f"delivery item already exists: {item_id}")

            item = DeliveryItem(
                item_id=item_id,
                user_id=user_id,
                status="uploaded",
                original_path=original_path,
                source_message_id=source_message_id,
            )
            self.items[item_id] = item
            self._persist()
            return replace(item)

    def mark_converting(self, item_id: str) -> DeliveryItem:
        with self._locked_state():
            item = self.items[item_id]
            if item.status != "uploaded":
                raise ValueError(
                    f"delivery item must be uploaded before converting: {item_id}"
                )

            item.status = "converting"
            self._persist()
            return replace(item)

    def mark_pending(
        self,
        item_id: str,
        *,
        converted_path: Path,
        channel_id: str,
        filename: str | None = None,
        sha256: str | None = None,
    ) -> DeliveryItem:
        with self._locked_state():
            item = self.items[item_id]
            if item.status != "converting":
                raise ValueError(
                    f"delivery item must be converting before pending: {item_id}"
                )

            item.status = "pending"
            item.converted_path = converted_path
            item.channel_id = channel_id
            item.filename = filename
            item.sha256 = sha256
            self.last_channel_by_user[item.user_id] = channel_id
            self._persist()
            return replace(item)

    def remember_user_channel(self, user_id: str, channel_id: str) -> None:
        with self._locked_state():
            self.last_channel_by_user[user_id] = channel_id
            self._persist()

    def ready_items_for_channels(self, channel_ids: list[str]) -> list[DeliveryItem]:
        with self._locked_state():
            channels = set(channel_ids)
            return [
                replace(item)
                for item in self.items.values()
                if item.status == "pending" and item.channel_id in channels
            ]

    def list_pending_items(self) -> list[DeliveryItem]:
        with self._locked_state():
            return [
                replace(item)
                for item in self.items.values()
                if item.status == "pending"
            ]

    def list_archived_items(self) -> list[DeliveryItem]:
        with self._locked_state():
            return [
                replace(item)
                for item in self.items.values()
                if item.status in ("delivered", "archived")
            ]

    def cancel_pending_item(self, item_id: str) -> DeliveryItem:
        with self._locked_state():
            item = self.items[item_id]
            if item.status != "pending":
                raise ValueError(f"delivery item must be pending before cancel: {item_id}")

            item.status = "canceled"
            self._persist()
            return replace(item)

    def request_archive_delete(self, item_id: str) -> DeliveryItem:
        with self._locked_state():
            item = self.items[item_id]
            if item.status not in ("delivered", "archived"):
                raise ValueError(
                    f"delivery item must be archived before archive delete: {item_id}"
                )

            self.archive_delete_requests[item_id] = {"status": "requested"}
            self._persist()
            return replace(item)

    def confirm_archive_delete(self, item_id: str) -> DeliveryItem:
        with self._locked_state():
            item = self.items[item_id]
            if item.status not in ("delivered", "archived"):
                raise ValueError(
                    f"delivery item must be archived before archive delete: {item_id}"
                )
            if item_id not in self.archive_delete_requests:
                raise ValueError(
                    f"archive delete must be requested before confirm: {item_id}"
                )

            previous_status = item.status
            previous_archive_entry = self.archive_index.get(item_id)
            previous_request = self.archive_delete_requests.get(item_id)
            item.status = "deleted_from_library"
            self.archive_index.pop(item_id, None)
            self.archive_delete_requests.pop(item_id, None)
            try:
                self._persist()
            except Exception:
                item.status = previous_status
                if previous_archive_entry is not None:
                    self.archive_index[item_id] = previous_archive_entry
                if previous_request is not None:
                    self.archive_delete_requests[item_id] = previous_request
                raise

            return replace(item)

    def ack_item(self, item_id: str) -> DeliveryItem:
        with self._locked_state():
            item = self.items[item_id]
            if item.status != "pending":
                raise ValueError(f"delivery item must be pending before ack: {item_id}")

            item.status = "delivered"
            delivered = replace(item)
            self.acknowledgements[item_id] = {"status": "delivered"}

            item.status = "archived"
            self.archive_index[item_id] = {
                "status": "archived",
                "channel_id": item.channel_id,
                "user_id": item.user_id,
            }
            self._persist()
            return delivered

    def restore_all_archived(self) -> list[DeliveryItem]:
        with self._locked_state():
            restored: list[DeliveryItem] = []
            for item_id, item in self.items.items():
                if item.status != "archived":
                    continue
                item.status = "pending"
                self.archive_index.pop(item_id, None)
                restored.append(replace(item))
            self._persist()
            return restored

    def get_item(self, item_id: str) -> DeliveryItem | None:
        with self._locked_state():
            item = self.items.get(item_id)
            return replace(item) if item is not None else None

    def has_active_media_for_channel(self, channel_id: str) -> bool:
        with self._locked_state():
            for item in self.items.values():
                if item.channel_id != channel_id:
                    continue
                if item.status not in {
                    "canceled",
                    "deleted_server_side",
                    "deleted_from_library",
                }:
                    return True
            return False

    def _load(self) -> None:
        self.items = {}
        self.last_channel_by_user = {}
        self.acknowledgements = {}
        self.archive_index = {}
        self.archive_delete_requests = {}
        if not self.state_path.exists():
            return

        with self.state_path.open("r", encoding="utf-8") as state_file:
            data = json.load(state_file)

        self.items = {
            item_id: DeliveryItem.from_json(item_data)
            for item_id, item_data in data.get("items", {}).items()
        }
        self.last_channel_by_user = dict(data.get("last_channel_by_user", {}))
        self.acknowledgements = dict(data.get("acknowledgements", {}))
        self.archive_index = dict(data.get("archive_index", {}))
        self.archive_delete_requests = dict(data.get("archive_delete_requests", {}))

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "items": {item_id: item.to_json() for item_id, item in self.items.items()},
            "last_channel_by_user": self.last_channel_by_user,
            "acknowledgements": self.acknowledgements,
            "archive_index": self.archive_index,
            "archive_delete_requests": self.archive_delete_requests,
        }

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.state_path.name}.",
            suffix=".tmp",
            dir=self.state_path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                json.dump(data, tmp_file, indent=2, sort_keys=True)
                tmp_file.write("\n")
            os.replace(tmp_name, self.state_path)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    @contextmanager
    def _locked_state(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                self._load()
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

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
        quarantine_dir = self.settings.media_dir / ".deleted_server_side" / item.item_id
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
