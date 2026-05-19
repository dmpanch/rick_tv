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

    return ServerSettings(
        media_dir=Path(os.environ.get("RICK_TV_MEDIA_DIR", DEFAULT_MEDIA_DIR)),
        config_dir=Path(os.environ.get("RICK_TV_CONFIG_DIR", DEFAULT_CONFIG_DIR)),
        state_dir=Path(os.environ.get("RICK_TV_STATE_DIR", DEFAULT_STATE_DIR)),
        api_token=api_token,
        public_base_url=os.environ.get(
            "RICK_TV_PUBLIC_BASE_URL",
            DEFAULT_PUBLIC_BASE_URL,
        ),
    )


def create_server_app() -> FastAPI:
    configure_logging()
    settings = load_settings_from_env()
    for directory in (settings.media_dir, settings.config_dir, settings.state_dir):
        directory.mkdir(parents=True, exist_ok=True)

    state_store = DeliveryStateStore(settings)
    return create_app(settings, state_store)


app = create_server_app()
