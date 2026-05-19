from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from rick_tv_pi.channels import Channel
from rick_tv_pi.config import PiSettings
from rick_tv_pi.validator import validate_ready_profile


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadyItem:
    id: str
    channel_id: str
    filename: str
    download_url: str
    sha256: str | None = None


class Poller:
    def __init__(self, settings: PiSettings, http_client: httpx.Client) -> None:
        self._settings = settings
        self._http_client = http_client

    def poll_once(self, channels: list[Channel]) -> list[ReadyItem]:
        channel_ids = ",".join(channel.id for channel in channels)
        base_url = self._settings.server_base_url.rstrip("/")
        response = self._http_client.get(
            f"{base_url}/api/v1/ready?channels={channel_ids}",
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        items = [
            ReadyItem(
                id=item["id"],
                channel_id=item["channel_id"],
                filename=item["filename"],
                download_url=item["download_url"],
                sha256=item.get("sha256"),
            )
            for item in response.json()["items"]
        ]
        known_channel_ids = {channel.id for channel in channels}

        for item in items:
            if item.channel_id not in known_channel_ids:
                continue
            self._deliver(item, base_url)

        return items

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

            if not validate_ready_profile(temp_path):
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

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._settings.api_token}"}

    def _remove_temp(self, temp_path: Path) -> None:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            return
