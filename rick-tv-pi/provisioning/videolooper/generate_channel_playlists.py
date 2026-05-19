#!/usr/bin/env python3
"""Generate Rick TV master/channel M3U files for pi_video_looper."""

from pathlib import Path


MEDIA_ROOT = Path("/home/pi/rick-tv/media")
PLAYLIST_ROOT = Path("/home/pi/rick-tv/playlists")


def channel_title(index: int, channel_id: str) -> str:
    label = channel_id.split("_", 1)[1].replace("_", " ") if "_" in channel_id else ""
    return f"Channel {index} - {label}" if label else f"Channel {index}"


def main() -> None:
    channels = sorted(path for path in MEDIA_ROOT.iterdir() if path.is_dir())
    channel_playlist_root = PLAYLIST_ROOT / "channels"
    channel_playlist_root.mkdir(parents=True, exist_ok=True)

    master_lines = ["#EXTM3U"]
    for index, channel_path in enumerate(channels, start=1):
        title = channel_title(index, channel_path.name)
        channel_playlist_path = channel_playlist_root / f"{channel_path.name}.m3u"
        master_lines.extend([f"#EXTINF:0,{title}", str(channel_playlist_path)])

        channel_lines = ["#EXTM3U"]
        for video_path in sorted(channel_path.glob("*.mp4")):
            channel_lines.extend([f"#EXTINF:0,{title}", str(video_path)])
        channel_playlist_path.write_text("\n".join(channel_lines) + "\n")

    (PLAYLIST_ROOT / "channels.m3u").write_text("\n".join(master_lines) + "\n")


if __name__ == "__main__":
    main()
