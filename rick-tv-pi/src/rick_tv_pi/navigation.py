from __future__ import annotations

try:
    from typing import Protocol
except ImportError:  # pragma: no cover - Python 3.7 runtime compatibility.
    from typing_extensions import Protocol

from rick_tv_pi.channels import Channel
from rick_tv_pi.touch import SwipeAction


class ChannelPlayer(Protocol):
    def select_channel(self, channel: Channel) -> None: ...


class ChannelNavigator:
    def __init__(self) -> None:
        self._channels: list[Channel] = []
        self._current_index: int | None = None

    @property
    def current_channel(self) -> Channel | None:
        if self._current_index is None or not self._channels:
            return None
        return self._channels[self._current_index]

    def refresh_channels(self, channels: list[Channel]) -> None:
        previous_id = self.current_channel.id if self.current_channel is not None else None
        self._channels = channels
        if not channels:
            self._current_index = None
            return
        if previous_id is None:
            return
        for index, channel in enumerate(channels):
            if channel.id == previous_id:
                self._current_index = index
                return
        self._current_index = 0

    def select_initial(self, player: ChannelPlayer) -> None:
        if self._current_index is not None or not self._channels:
            return
        self._current_index = 0
        player.select_channel(self._channels[self._current_index])

    def apply_action(self, action: SwipeAction | None, player: ChannelPlayer) -> None:
        if action is None or not self._channels:
            return
        if self._current_index is None:
            self._current_index = 0
        elif action == "next":
            self._current_index = (self._current_index + 1) % len(self._channels)
        elif action == "previous":
            self._current_index = (self._current_index - 1) % len(self._channels)
        player.select_channel(self._channels[self._current_index])
