from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Channel:
    id: str
    number: int
    display_name: str | None
    path: Path


def discover_channels(media_root: Path, metadata_path: Path | None) -> list[Channel]:
    del metadata_path

    channel_paths = [path for path in media_root.iterdir() if path.is_dir()]
    ordered_paths = sorted(channel_paths, key=_channel_sort_key)

    return [
        Channel(id=path.name, number=index, display_name=None, path=path)
        for index, path in enumerate(ordered_paths, start=1)
    ]


def _channel_sort_key(path: Path) -> tuple[int, int | str, str]:
    channel_id = path.name
    prefix, separator, _ = channel_id.partition("_")

    if separator and prefix.isdigit():
        return (0, int(prefix), channel_id)

    return (1, channel_id, channel_id)
