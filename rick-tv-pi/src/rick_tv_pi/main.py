import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from rick_tv_pi.channels import discover_channels
from rick_tv_pi.config import PiSettings
from rick_tv_pi.player import PlaybackController
from rick_tv_pi.poller import Poller
from rick_tv_pi.touch import TouchInterpreter


logger = logging.getLogger(__name__)


@dataclass
class RuntimeState:
    initial_channel_selected: bool = False


def load_settings_from_env(environ: dict[str, str] | None = None) -> PiSettings:
    env = os.environ if environ is None else environ
    metadata_path = env.get("RICK_TV_METADATA_PATH")

    return PiSettings(
        server_base_url=env["RICK_TV_SERVER_URL"],
        api_token=env["RICK_TV_API_TOKEN"],
        media_root=Path(env["RICK_TV_MEDIA_ROOT"]),
        poll_interval_seconds=int(env.get("RICK_TV_POLL_INTERVAL_SECONDS", "60")),
        metadata_path=Path(metadata_path) if metadata_path else None,
    )


def run_runtime_cycle(
    settings: PiSettings,
    player: PlaybackController,
    poller: Poller,
    state: RuntimeState,
) -> None:
    channels = discover_channels(settings.media_root, settings.metadata_path)
    if channels and not state.initial_channel_selected:
        player.select_channel(channels[0])
        state.initial_channel_selected = True

    try:
        poller.poll_once(channels)
    except Exception:
        logger.warning("Pi runtime poll failed", exc_info=True)

    if player.screen_state == "empty":
        player.rescan_current_channel()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings_from_env()
    player = PlaybackController(
        player_command=os.environ.get(
            "RICK_TV_PLAYER_COMMAND",
            "mpv --fs --loop-file=inf --no-terminal --really-quiet",
        )
    )
    touch = TouchInterpreter(cooldown_seconds=0.5)
    state = RuntimeState()

    with httpx.Client(timeout=30.0) as http_client:
        poller = Poller(settings=settings, http_client=http_client)

        while True:
            run_runtime_cycle(
                settings=settings,
                player=player,
                poller=poller,
                state=state,
            )
            logger.debug("Touch interpreter ready: %s", touch.__class__.__name__)
            time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
