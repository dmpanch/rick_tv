from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
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
]

DELIVERY_STATUSES: tuple[DeliveryStatus, ...] = (
    "uploaded",
    "converting",
    "pending",
    "canceled",
    "delivered",
    "archived",
    "deleted_server_side",
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
        self.items: dict[str, DeliveryItem] = {}
        self.last_channel_by_user: dict[str, str] = {}
        self.acknowledgements: dict[str, object] = {}
        self.archive_index: dict[str, object] = {}
        self._load()

    def create_uploaded_item(
        self,
        *,
        item_id: str,
        user_id: str,
        original_path: Path,
        source_message_id: int | None = None,
    ) -> DeliveryItem:
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
        return item

    def mark_converting(self, item_id: str) -> DeliveryItem:
        item = self.items[item_id]
        if item.status != "uploaded":
            raise ValueError(
                f"delivery item must be uploaded before converting: {item_id}"
            )

        item.status = "converting"
        self._persist()
        return item

    def mark_pending(
        self,
        item_id: str,
        *,
        converted_path: Path,
        channel_id: str,
        filename: str | None = None,
        sha256: str | None = None,
    ) -> DeliveryItem:
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
        return item

    def ready_items_for_channels(self, channel_ids: list[str]) -> list[DeliveryItem]:
        channels = set(channel_ids)
        return [
            item
            for item in self.items.values()
            if item.status == "pending" and item.channel_id in channels
        ]

    def ack_item(self, item_id: str) -> DeliveryItem:
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

    def _load(self) -> None:
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

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "items": {item_id: item.to_json() for item_id, item in self.items.items()},
            "last_channel_by_user": self.last_channel_by_user,
            "acknowledgements": self.acknowledgements,
            "archive_index": self.archive_index,
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
