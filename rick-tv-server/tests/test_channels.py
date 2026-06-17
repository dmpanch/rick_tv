from __future__ import annotations

from pathlib import Path

import pytest

from rick_tv_server.channels import ChannelRegistry, ChannelRegistryStore
from rick_tv_server.config import ServerSettings


def make_settings(tmp_path: Path) -> ServerSettings:
    return ServerSettings(
        media_dir=tmp_path / "media",
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        api_token="test-token",
        public_base_url="https://example.test",
    )


class FakeStateStore:
    def __init__(self, channel_ids: list[str]) -> None:
        self.items = {
            f"item-{index}": type(
                "Item",
                (),
                {"channel_id": channel_id, "status": "available"},
            )()
            for index, channel_id in enumerate(channel_ids, start=1)
        }


def test_channel_registry_reads_missing_file_as_empty(tmp_path: Path):
    store = ChannelRegistryStore(make_settings(tmp_path))

    assert store.load() == ChannelRegistry(channels={})


def test_channel_registry_add_rename_and_delete_are_persisted_atomically(
    tmp_path: Path,
):
    settings = make_settings(tmp_path)
    store = ChannelRegistryStore(settings)

    store.add_channel("01_Citadel", "Citadel TV")
    store.rename_channel("01_Citadel", "Citadel Archive")
    store.add_channel("Garage", "Garage")
    store.delete_channel("Garage")

    reloaded = ChannelRegistryStore(settings).load()
    assert reloaded.channels == {
        "01_Citadel": {"display_name": "Citadel Archive"}
    }
    assert not list(settings.state_dir.glob("*.tmp"))


@pytest.mark.parametrize(
    "channel_id",
    ["", "../bad", "bad/name", ".hidden", "bad name", "bad:name"],
)
def test_channel_registry_rejects_unstable_channel_ids(
    tmp_path: Path,
    channel_id: str,
):
    store = ChannelRegistryStore(make_settings(tmp_path))

    with pytest.raises(ValueError, match="channel_id"):
        store.add_channel(channel_id, "Bad")


def test_channel_registry_delete_rejects_channels_with_active_media(
    tmp_path: Path,
):
    store = ChannelRegistryStore(make_settings(tmp_path))
    store.add_channel("01_Citadel", "Citadel TV")

    with pytest.raises(ValueError, match="active media"):
        store.delete_channel("01_Citadel", state_store=FakeStateStore(["01_Citadel"]))

    assert "01_Citadel" in store.load().channels
