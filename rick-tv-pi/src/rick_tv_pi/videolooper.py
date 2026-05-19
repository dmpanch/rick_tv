from __future__ import annotations

import errno
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple

from rick_tv_pi.channels import Channel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayableFile:
    path: Path


class VideolooperController:
    def __init__(
        self,
        playlist_root: Path,
        command_path: Path = Path("/tmp/rick-tv-videolooper.fifo"),
        command_writer: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.screen_state: str = "empty"
        self.current_file: Optional[PlayableFile] = None
        self._current_channel: Optional[Channel] = None
        self._current_commanded_channel_id: Optional[str] = None
        self._playlist_root = playlist_root
        self._channels_root = playlist_root / "channels"
        self._master_playlist_path = playlist_root / "channels.m3u"
        self._command_path = command_path
        self._command_writer = command_writer or self._write_fifo_command
        self._last_playlist_text_by_channel = {}
        self._last_master_playlist_text: Optional[str] = None

    @property
    def master_playlist_path(self) -> Path:
        return self._master_playlist_path

    def sync_channels(self, channels: Iterable[Channel]) -> None:
        channels = list(channels)
        self._playlist_root.mkdir(parents=True, exist_ok=True)
        self._channels_root.mkdir(parents=True, exist_ok=True)
        for channel in channels:
            self._write_channel_playlist_if_changed(channel)

        master_playlist_text = self._build_master_playlist(channels)
        if master_playlist_text == self._last_master_playlist_text:
            return
        self._master_playlist_path.write_text(master_playlist_text)
        self._last_master_playlist_text = master_playlist_text

    def select_channel(self, channel: Channel) -> None:
        if self._current_channel is not None and self._current_channel.id == channel.id:
            return
        self._current_channel = channel
        self._write_channel_playlist_if_changed(channel)
        self._update_state(channel)
        self._send_channel_command(channel, force=True)

    def rescan_current_channel(self) -> None:
        if self._current_channel is None:
            self.screen_state = "empty"
            self.current_file = None
            return

        changed = self._write_channel_playlist_if_changed(self._current_channel)
        self._update_state(self._current_channel)
        if changed:
            self._send_channel_command(self._current_channel, force=True)

    def _write_channel_playlist_if_changed(self, channel: Channel) -> bool:
        playlist_text, _first_file = self._build_channel_playlist(channel)
        last_playlist_text = self._last_playlist_text_by_channel.get(channel.id)
        if playlist_text == last_playlist_text:
            return False

        channel_playlist_path = self._channel_playlist_path(channel)
        channel_playlist_path.parent.mkdir(parents=True, exist_ok=True)
        channel_playlist_path.write_text(playlist_text)
        self._last_playlist_text_by_channel[channel.id] = playlist_text
        return True

    def _update_state(self, channel: Channel) -> None:
        _playlist_text, first_file = self._build_channel_playlist(channel)
        self.screen_state = "playing" if first_file is not None else "empty"
        self.current_file = PlayableFile(first_file) if first_file is not None else None

    def _build_master_playlist(self, channels: Iterable[Channel]) -> str:
        lines = ["#EXTM3U"]
        for channel in channels:
            lines.append(f"#EXTINF:0,{_channel_title(channel)}")
            lines.append(str(self._channel_playlist_path(channel)))
        return "\n".join(lines) + "\n"

    def _build_channel_playlist(self, channel: Channel) -> Tuple[str, Optional[Path]]:
        files = sorted(
            path
            for path in channel.path.iterdir()
            if path.is_file() and path.suffix.lower() == ".mp4"
        )
        if not files:
            return "#EXTM3U\n", None

        title = _channel_title(channel)
        lines = ["#EXTM3U"]
        for path in files:
            lines.append(f"#EXTINF:0,{title}")
            lines.append(str(path))
        return "\n".join(lines) + "\n", files[0]

    def _send_channel_command(self, channel: Channel, *, force: bool = False) -> None:
        command = str(self._channel_playlist_path(channel))
        if not force and self._current_commanded_channel_id == channel.id:
            return
        try:
            self._command_writer(command)
        except OSError as exc:
            logger.warning("Videolooper command pipe is unavailable: %s", exc)
        else:
            self._current_commanded_channel_id = channel.id

    def _write_fifo_command(self, command: str) -> None:
        fd = os.open(str(self._command_path), os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, (command + "\n").encode("utf-8"))
        except OSError as exc:
            if exc.errno not in (errno.EPIPE, errno.ENXIO):
                raise
            logger.warning("Videolooper command pipe has no reader: %s", exc)
        finally:
            os.close(fd)

    def _channel_playlist_path(self, channel: Channel) -> Path:
        return self._channels_root / f"{channel.id}.m3u"


def _channel_title(channel: Channel) -> str:
    if channel.display_name:
        return f"Channel {channel.number} - {channel.display_name}"
    return f"Channel {channel.number}"
