import logging
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rick_tv_pi.channels import Channel


logger = logging.getLogger(__name__)


class PlayerProcess(Protocol):
    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...


@dataclass(frozen=True)
class PlayableFile:
    path: Path


class PlaybackController:
    def __init__(
        self,
        player_command: str = "mpv --fs --loop-file=inf --no-terminal --really-quiet",
        process_factory=subprocess.Popen,
    ) -> None:
        self.screen_state: str = "empty"
        self.current_file: PlayableFile | None = None
        self._current_channel: Channel | None = None
        self._player_command = player_command
        self._process_factory = process_factory
        self._process: PlayerProcess | None = None

    def select_channel(self, channel: Channel) -> None:
        self._current_channel = channel
        self.rescan_current_channel()

    def rescan_current_channel(self) -> None:
        if self._current_channel is None:
            self._stop_playback()
            self.screen_state = "empty"
            self.current_file = None
            return

        playable_files = sorted(
            path
            for path in self._current_channel.path.iterdir()
            if path.is_file() and path.suffix == ".mp4"
        )
        if not playable_files:
            self._stop_playback()
            self.screen_state = "empty"
            self.current_file = None
            return

        selected_file = PlayableFile(path=playable_files[0])
        self.screen_state = "playing"
        if self.current_file == selected_file and self._process_is_running():
            return

        self.current_file = selected_file
        self._start_playback(selected_file.path)

    def _start_playback(self, path: Path) -> None:
        self._stop_playback()
        command = [*shlex.split(self._player_command), str(path)]
        logger.info("Starting player: %s", command)
        self._process = self._process_factory(command)

    def _stop_playback(self) -> None:
        if self._process is None:
            return
        if self._process_is_running():
            self._process.terminate()
        self._process = None

    def _process_is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None
