import httpx

from rick_tv_pi.channels import Channel
from rick_tv_pi.config import PiSettings


class Poller:
    def __init__(self, settings: PiSettings, http_client: httpx.Client) -> None:
        self._settings = settings
        self._http_client = http_client

    def poll_once(self, channels: list[Channel]) -> list[object]:
        channel_ids = ",".join(channel.id for channel in channels)
        base_url = self._settings.server_base_url.rstrip("/")
        response = self._http_client.get(
            f"{base_url}/api/v1/ready?channels={channel_ids}",
            headers={"Authorization": f"Bearer {self._settings.api_token}"},
        )
        response.raise_for_status()
        return response.json()["items"]
