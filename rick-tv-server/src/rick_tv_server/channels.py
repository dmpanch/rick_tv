from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


CHANNEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class ChannelRegistry:
    channels: dict[str, dict[str, str]]


class ChannelRegistryStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> ChannelRegistry:
        if not self.path.exists():
            return ChannelRegistry(channels={})

        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ChannelRegistry(channels={})

        raw_channels = data.get("channels")
        if not isinstance(raw_channels, dict):
            return ChannelRegistry(channels={})

        channels: dict[str, dict[str, str]] = {}
        for channel_id, channel_metadata in raw_channels.items():
            if not isinstance(channel_id, str) or not isinstance(channel_metadata, dict):
                continue
            display_name = channel_metadata.get("display_name")
            if not isinstance(display_name, str):
                continue
            channels[channel_id] = {"display_name": display_name}

        return ChannelRegistry(channels=channels)

    def add_channel(self, channel_id: str, display_name: str) -> None:
        _validate_channel_id(channel_id)
        registry = self.load()
        if channel_id in registry.channels:
            raise ValueError(f"channel already exists: {channel_id}")
        registry.channels[channel_id] = {"display_name": display_name}
        self._persist(registry)

    def rename_channel(self, channel_id: str, display_name: str) -> None:
        registry = self.load()
        if channel_id not in registry.channels:
            raise ValueError(f"unknown channel_id: {channel_id}")
        registry.channels[channel_id] = {"display_name": display_name}
        self._persist(registry)

    def delete_channel(self, channel_id: str, state_store: Any = None) -> None:
        registry = self.load()
        if channel_id not in registry.channels:
            raise ValueError(f"unknown channel_id: {channel_id}")
        if state_store is not None and _has_active_media(state_store, channel_id):
            raise ValueError(f"channel has active media references: {channel_id}")
        del registry.channels[channel_id]
        self._persist(registry)

    def dump_text(self) -> str:
        registry = self.load()
        return _registry_to_yaml(registry)

    def _persist(self, registry: ChannelRegistry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(_registry_to_yaml(registry))
            os.replace(tmp_name, self.path)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise


def _registry_to_yaml(registry: ChannelRegistry) -> str:
    return yaml.safe_dump(
        {"channels": registry.channels},
        sort_keys=True,
        allow_unicode=True,
    )


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
        if getattr(item, "status", None) not in {"canceled", "deleted_server_side"}:
            return True
    return False
