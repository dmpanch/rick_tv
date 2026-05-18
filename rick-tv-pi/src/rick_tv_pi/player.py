from dataclasses import dataclass
from pathlib import Path

from rick_tv_pi.channels import Channel


@dataclass(frozen=True)
class PlayableFile:
    path: Path


class PlaybackController:
    def __init__(self) -> None:
        self.screen_state: str = "empty"
        self.current_file: PlayableFile | None = None
        self._current_channel: Channel | None = None

    def select_channel(self, channel: Channel) -> None:
        self._current_channel = channel
        self.rescan_current_channel()

    def rescan_current_channel(self) -> None:
        if self._current_channel is None:
            self.screen_state = "empty"
            self.current_file = None
            return

        playable_files = sorted(
            path
            for path in self._current_channel.path.iterdir()
            if path.is_file() and path.suffix == ".mp4"
        )
        if not playable_files:
            self.screen_state = "empty"
            self.current_file = None
            return

        self.screen_state = "playing"
        self.current_file = PlayableFile(path=playable_files[0])
