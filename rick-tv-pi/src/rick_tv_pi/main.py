from __future__ import annotations

import logging
import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

try:
    from typing import Protocol
    from typing import Literal
except ImportError:  # pragma: no cover - Python 3.7 runtime compatibility.
    from typing_extensions import Protocol
    from typing_extensions import Literal

import httpx

from rick_tv_pi.channels import discover_channels
from rick_tv_pi.config import PiSettings
from rick_tv_pi.navigation import ChannelNavigator
from rick_tv_pi.poller import Poller
from rick_tv_pi.touch import SwipeAction, TouchInterpreter
from rick_tv_pi.touch_source import EvdevTouchSource
from rick_tv_pi.videolooper import VideolooperController


logger = logging.getLogger(__name__)


@dataclass
class RuntimeState:
    initial_channel_selected: bool = False
    navigator: Optional[ChannelNavigator] = None
    next_poll_at: float = 0.0
    next_remote_poll_at: float = 0.0


class RuntimePlayer(Protocol):
    def sync_channels(self, channels: Iterable, now: Optional[float] = None) -> None: ...

    def select_channel(self, channel) -> bool | None: ...

    def rescan_current_channel(self, now: Optional[float] = None) -> None: ...


@dataclass(frozen=True)
class VideolooperSettings:
    playlist_root: Path
    command_path: Path
    channel_shuffle_seconds: int


@dataclass(frozen=True)
class TouchSettings:
    screen_width: int
    screen_height: int
    swap_axes: bool | str
    gesture_horizontal_axis: Literal["x", "y"]
    invert_x: bool
    invert_y: bool
    device_path: str | None


class TouchActionSource:
    def __init__(self, touch_source: EvdevTouchSource, interpreter: TouchInterpreter) -> None:
        self._gestures = touch_source.gestures()
        self._interpreter = interpreter

    def next_action(self) -> Optional[SwipeAction]:
        try:
            start, end = next(self._gestures)
        except StopIteration:
            return None
        except Exception:
            logger.warning("Touch gesture parsing failed", exc_info=True)
            return None
        return self._interpreter.interpret(start, end)


class TouchActionQueue:
    def __init__(self) -> None:
        self._queue: queue.SimpleQueue[SwipeAction] = queue.SimpleQueue()

    def put(self, action: Optional[SwipeAction]) -> None:
        if action is not None:
            self._queue.put(action)

    def next_action(self) -> Optional[SwipeAction]:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None


def start_touch_reader(
    touch_actions: TouchActionSource,
    action_queue: TouchActionQueue,
) -> threading.Thread:
    thread = threading.Thread(
        target=_read_touch_actions,
        args=(touch_actions, action_queue),
        daemon=True,
        name="rick-tv-touch",
    )
    thread.start()
    return thread


def _read_touch_actions(
    touch_actions: TouchActionSource,
    action_queue: TouchActionQueue,
) -> None:
    while True:
        action = touch_actions.next_action()
        action_queue.put(action)
        if action is None:
            time.sleep(0.1)


def load_settings_from_env(environ: Optional[dict[str, str]] = None) -> PiSettings:
    env = os.environ if environ is None else environ
    metadata_path = env.get("RICK_TV_METADATA_PATH")

    return PiSettings(
        server_base_url=env["RICK_TV_SERVER_URL"],
        api_token=env["RICK_TV_API_TOKEN"],
        media_root=Path(env["RICK_TV_MEDIA_ROOT"]),
        poll_interval_seconds=int(env.get("RICK_TV_POLL_INTERVAL_SECONDS", "60")),
        metadata_path=Path(metadata_path) if metadata_path else None,
        remote_poll_interval_seconds=int(
            env.get("RICK_TV_REMOTE_POLL_INTERVAL_SECONDS", "2")
        ),
    )


def load_videolooper_settings_from_env(
    environ: Optional[dict[str, str]] = None,
) -> VideolooperSettings:
    env = os.environ if environ is None else environ
    return VideolooperSettings(
        playlist_root=Path(
            env.get("RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT", "/home/pi/rick-tv/playlists")
        ),
        command_path=Path(
            env.get("RICK_TV_VIDEOLOOPER_COMMAND_PATH", "/tmp/rick-tv-videolooper.fifo")
        ),
        channel_shuffle_seconds=int(env.get("RICK_TV_CHANNEL_SHUFFLE_SECONDS", "3600")),
    )


def load_touch_settings_from_env(
    environ: Optional[dict[str, str]] = None,
) -> TouchSettings:
    env = os.environ if environ is None else environ
    return TouchSettings(
        screen_width=int(env.get("RICK_TV_TOUCH_SCREEN_WIDTH", "480")),
        screen_height=int(env.get("RICK_TV_TOUCH_SCREEN_HEIGHT", "640")),
        swap_axes=env.get("RICK_TV_TOUCH_SWAP_AXES", "auto"),
        gesture_horizontal_axis=_normalize_gesture_horizontal_axis(
            env.get("RICK_TV_TOUCH_GESTURE_HORIZONTAL_AXIS", "x")
        ),
        invert_x=env.get("RICK_TV_TOUCH_INVERT_X", "0").lower()
        in {"1", "true", "on", "yes"},
        invert_y=env.get("RICK_TV_TOUCH_INVERT_Y", "0").lower()
        in {"1", "true", "on", "yes"},
        device_path=env.get("RICK_TV_TOUCH_DEVICE"),
    )


def _normalize_gesture_horizontal_axis(value: str | None) -> Literal["x", "y"]:
    if (value or "").strip().lower() == "y":
        return "y"
    return "x"


def run_runtime_cycle(
    settings: PiSettings,
    player: RuntimePlayer,
    poller: Poller,
    state: RuntimeState,
    touch_actions=None,
    now: Optional[float] = None,
) -> None:
    current_time = time.monotonic() if now is None else now
    channels = discover_channels(settings.media_root, settings.metadata_path)
    if state.navigator is None:
        state.navigator = ChannelNavigator()
    state.navigator.refresh_channels(channels)

    player.sync_channels(channels, now=current_time)
    if channels and not state.initial_channel_selected:
        state.navigator.select_initial(player)
        state.initial_channel_selected = True

    if touch_actions is not None:
        while True:
            action = touch_actions.next_action()
            if action is None:
                break
            logger.info("Touch action detected: %s", action)
            state.navigator.apply_action(action, player)

    if current_time >= state.next_remote_poll_at:
        try:
            registry_channel_ids = _load_registry_channel_ids(settings.metadata_path)
            for command in poller.poll_remote_commands():
                if _apply_remote_command(
                    command,
                    state.navigator,
                    player,
                    registry_channel_ids=registry_channel_ids,
                ):
                    poller.ack_remote_command(command.id)
        except Exception:
            logger.warning("Pi runtime remote command poll failed", exc_info=True)
        state.next_remote_poll_at = (
            current_time + settings.remote_poll_interval_seconds
        )

    if current_time >= state.next_poll_at:
        try:
            poller.poll_once(channels)
        except Exception:
            logger.warning("Pi runtime poll failed", exc_info=True)
        state.next_poll_at = current_time + settings.poll_interval_seconds

    player.rescan_current_channel(now=current_time)


def _apply_remote_command(
    command,
    navigator: ChannelNavigator,
    player: RuntimePlayer,
    registry_channel_ids: set[str] | None = None,
) -> bool:
    if getattr(command, "type", None) != "select_channel":
        logger.warning("Unknown remote command type: %s", getattr(command, "type", None))
        return True

    channel_id = str(getattr(command, "channel_id", ""))
    channel_is_local = navigator.has_channel_id(channel_id)
    if not navigator.select_channel_id(channel_id, player):
        if channel_is_local:
            logger.warning("Remote channel selection failed: %s", channel_id)
            return False
        if registry_channel_ids is not None and channel_id in registry_channel_ids:
            logger.info("Remote channel is not locally playable yet: %s", channel_id)
            return False
        logger.info("Remote channel is not locally playable: %s", channel_id)
        return True
    return True


def _load_registry_channel_ids(metadata_path: Path | None) -> set[str] | None:
    if metadata_path is None or not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(metadata, dict):
        return None
    channels = metadata.get("channels")
    if not isinstance(channels, dict):
        return None
    return {channel_id for channel_id in channels if isinstance(channel_id, str)}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings_from_env()
    videolooper_settings = load_videolooper_settings_from_env()
    touch_settings = load_touch_settings_from_env()
    player = VideolooperController(
        playlist_root=videolooper_settings.playlist_root,
        command_path=videolooper_settings.command_path,
        shuffle_interval_seconds=videolooper_settings.channel_shuffle_seconds,
    )
    touch_actions = TouchActionSource(
        EvdevTouchSource(
            screen_width=touch_settings.screen_width,
            screen_height=touch_settings.screen_height,
            swap_axes=touch_settings.swap_axes,
            invert_x=touch_settings.invert_x,
            invert_y=touch_settings.invert_y,
            device_path=touch_settings.device_path,
        ),
        TouchInterpreter(
            cooldown_seconds=0.5,
            gesture_horizontal_axis=touch_settings.gesture_horizontal_axis,
        ),
    )
    touch_action_queue = TouchActionQueue()
    start_touch_reader(touch_actions, touch_action_queue)
    state = RuntimeState()

    with httpx.Client(timeout=30.0) as http_client:
        poller = Poller(settings=settings, http_client=http_client)

        while True:
            run_runtime_cycle(
                settings=settings,
                player=player,
                poller=poller,
                state=state,
                touch_actions=touch_action_queue,
            )
            time.sleep(float(os.environ.get("RICK_TV_RUNTIME_TICK_SECONDS", "0.1")))


if __name__ == "__main__":
    main()
