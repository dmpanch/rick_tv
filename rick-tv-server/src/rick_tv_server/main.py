from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI

from rick_tv_server.api import create_app
from rick_tv_server.config import ServerSettings
from rick_tv_server.state import DeliveryStateStore

DEFAULT_MEDIA_DIR = Path("/var/lib/rick-tv/media")
DEFAULT_CONFIG_DIR = Path("/etc/rick-tv")
DEFAULT_STATE_DIR = Path("/var/lib/rick-tv/state")
DEFAULT_PUBLIC_BASE_URL = "http://localhost:8080"


def configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("RICK_TV_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )


def load_settings_from_env() -> ServerSettings:
    api_token = os.environ.get("RICK_TV_API_TOKEN")
    if not api_token:
        raise RuntimeError("RICK_TV_API_TOKEN must be set")

    config_dir = Path(os.environ.get("RICK_TV_CONFIG_DIR", DEFAULT_CONFIG_DIR))
    channels_path = Path(
        os.environ.get("RICK_TV_CHANNELS_PATH", str(config_dir / "channels.yml"))
    )

    return ServerSettings(
        media_dir=Path(os.environ.get("RICK_TV_MEDIA_DIR", DEFAULT_MEDIA_DIR)),
        config_dir=config_dir,
        state_dir=Path(os.environ.get("RICK_TV_STATE_DIR", DEFAULT_STATE_DIR)),
        api_token=api_token,
        public_base_url=os.environ.get(
            "RICK_TV_PUBLIC_BASE_URL",
            DEFAULT_PUBLIC_BASE_URL,
        ),
        telegram_bot_token=os.environ.get("RICK_TV_TELEGRAM_BOT_TOKEN") or None,
        telegram_allowed_user_ids=_parse_allowed_user_ids(
            os.environ.get("RICK_TV_TELEGRAM_ALLOWED_USER_IDS", "")
        ),
        telegram_local_api_url=(
            os.environ.get("RICK_TV_TELEGRAM_LOCAL_API_URL", "").strip().rstrip("/")
            or None
        ),
        channels_path=channels_path,
        db_path=(
            Path(db_path)
            if (db_path := os.environ.get("RICK_TV_DB_PATH"))
            else None
        ),
    )


def create_server_app() -> FastAPI:
    configure_logging()
    settings = load_settings_from_env()
    for directory in (settings.media_dir, settings.config_dir, settings.state_dir):
        directory.mkdir(parents=True, exist_ok=True)
    if settings.channels_path is not None:
        settings.channels_path.parent.mkdir(parents=True, exist_ok=True)

    state_store = DeliveryStateStore(settings)
    return create_app(settings, state_store)


def _parse_allowed_user_ids(value: str) -> tuple[int, ...]:
    user_ids: list[int] = []
    for raw_user_id in value.split(","):
        stripped = raw_user_id.strip()
        if not stripped:
            continue
        try:
            user_ids.append(int(stripped))
        except ValueError as error:
            raise RuntimeError(
                "RICK_TV_TELEGRAM_ALLOWED_USER_IDS must contain integers"
            ) from error
    return tuple(user_ids)


app = create_server_app()
