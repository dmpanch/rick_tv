from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Channel:
    id: str
    number: int
    display_name: str | None
    path: Path


def discover_channels(media_root: Path, metadata_path: Path | None) -> list[Channel]:
    channel_paths = [path for path in media_root.iterdir() if path.is_dir()]
    ordered_paths = sorted(channel_paths, key=_channel_sort_key)
    display_names = _load_display_names(metadata_path)

    return [
        Channel(
            id=path.name,
            number=index,
            display_name=display_names.get(path.name),
            path=path,
        )
        for index, path in enumerate(ordered_paths, start=1)
    ]


def _channel_sort_key(path: Path) -> tuple[int, int | str, str]:
    channel_id = path.name
    prefix, separator, _ = channel_id.partition("_")

    if separator and prefix.isdigit():
        return (0, int(prefix), channel_id)

    return (1, channel_id, channel_id)


def _load_display_names(metadata_path: Path | None) -> dict[str, str]:
    if metadata_path is None or not metadata_path.exists():
        return {}

    metadata = yaml.safe_load(metadata_path.read_text())
    if not isinstance(metadata, dict):
        return {}

    channels = metadata.get("channels")
    if not isinstance(channels, dict):
        return {}

    display_names = {}
    for channel_id, channel_metadata in channels.items():
        if not isinstance(channel_id, str) or not isinstance(channel_metadata, dict):
            continue

        display_name = channel_metadata.get("display_name")
        if isinstance(display_name, str):
            display_names[channel_id] = display_name

    return display_names
