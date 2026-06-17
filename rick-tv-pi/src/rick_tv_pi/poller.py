from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from rick_tv_pi.channels import Channel
from rick_tv_pi.config import PiSettings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadyItem:
    id: str
    channel_id: str
    filename: str
    download_url: str
    sha256: str | None = None


@dataclass(frozen=True)
class DeleteItem:
    id: str
    channel_id: str
    filename: str


class Poller:
    def __init__(self, settings: PiSettings, http_client: httpx.Client) -> None:
        self._settings = settings
        self._http_client = http_client

    def poll_once(self, channels: list[Channel]) -> list[ReadyItem]:
        base_url = self._settings.server_base_url.rstrip("/")
        self.sync_channel_registry()
        poll_channel_ids = self._poll_channel_ids(channels)
        if not poll_channel_ids:
            return []
        channel_ids = ",".join(poll_channel_ids)
        response = self._http_client.get(
            f"{base_url}/api/v1/ready?channels={channel_ids}",
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        items = [
            ReadyItem(
                id=item["id"],
                channel_id=item["channel_id"],
                filename=item["filename"],
                download_url=item["download_url"],
                sha256=item.get("sha256"),
            )
            for item in payload.get("items", [])
        ]
        deletions = [
            DeleteItem(
                id=item["id"],
                channel_id=item["channel_id"],
                filename=item["filename"],
            )
            for item in payload.get("deletions", [])
        ]
        known_channel_ids = set(poll_channel_ids)

        for item in items:
            if item.channel_id not in known_channel_ids:
                continue
            self._deliver(item, base_url)

        for item in deletions:
            if item.channel_id not in known_channel_ids:
                continue
            self._delete_from_device(item, base_url)

        return items

    def sync_channel_registry(self) -> None:
        metadata_path = self._settings.metadata_path
        if metadata_path is None:
            return

        base_url = self._settings.server_base_url.rstrip("/")
        response = self._http_client.get(
            f"{base_url}/api/v1/channels",
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        self._write_metadata(metadata_path, response.text)

    def _deliver(self, item: ReadyItem, base_url: str) -> None:
        downloads_dir = self._settings.media_root / ".downloads"
        temp_path = downloads_dir / f"{item.id}.tmp"

        try:
            download_response = self._http_client.get(
                item.download_url,
                headers=self._auth_headers(),
            )
            download_response.raise_for_status()

            downloads_dir.mkdir(parents=True, exist_ok=True)
            temp_path.write_bytes(download_response.content)

            if item.sha256 is not None:
                digest = hashlib.sha256(download_response.content).hexdigest()
                if digest != item.sha256:
                    self._remove_temp(temp_path)
                    return

            destination_dir = self._settings.media_root / item.channel_id
            destination_dir.mkdir(parents=True, exist_ok=True)
            temp_path.replace(destination_dir / item.filename)

            ack_response = self._http_client.post(
                f"{base_url}/api/v1/ack/{item.id}",
                headers=self._auth_headers(),
            )
            ack_response.raise_for_status()
        except Exception:
            logger.warning(
                "Failed to deliver ready item %s for channel %s",
                item.id,
                item.channel_id,
                exc_info=True,
            )
            self._remove_temp(temp_path)
            return

    def _delete_from_device(self, item: DeleteItem, base_url: str) -> None:
        destination = (
            self._settings.media_root / item.channel_id / Path(item.filename).name
        )
        try:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass

            ack_response = self._http_client.post(
                f"{base_url}/api/v1/delete-ack/{item.id}",
                headers=self._auth_headers(),
            )
            ack_response.raise_for_status()
        except Exception:
            logger.warning(
                "Failed to delete ready item %s for channel %s",
                item.id,
                item.channel_id,
                exc_info=True,
            )
            return

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._settings.api_token}"}

    def _poll_channel_ids(self, channels: list[Channel]) -> list[str]:
        registry_channel_ids = self._registry_channel_ids()
        if registry_channel_ids is not None:
            return registry_channel_ids
        return [channel.id for channel in channels]

    def _registry_channel_ids(self) -> Optional[list[str]]:
        metadata_path = self._settings.metadata_path
        if metadata_path is None or not metadata_path.exists():
            return None

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(metadata, dict):
            return None
        channels = metadata.get("channels")
        if not isinstance(channels, dict):
            return None
        return [channel_id for channel_id in channels if isinstance(channel_id, str)]

    def _write_metadata(self, metadata_path: Path, content: str) -> None:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{metadata_path.name}.",
            suffix=".tmp",
            dir=metadata_path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(content)
            os.replace(tmp_name, metadata_path)
        except Exception:
            try:
                Path(tmp_name).unlink()
            except FileNotFoundError:
                pass
            raise

    def _remove_temp(self, temp_path: Path) -> None:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            return
