from __future__ import annotations

import logging
import os
import sys

from rick_tv_server.bot import build_application
from rick_tv_server.channels import ChannelRegistryStore
from rick_tv_server.config import ServerSettings
from rick_tv_server.state import DeliveryStateStore
from rick_tv_server.uploads import UploadProcessor


def configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("RICK_TV_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def load_settings_from_env() -> ServerSettings:
    from rick_tv_server.main import load_settings_from_env as load_server_settings

    return load_server_settings()


def main() -> None:
    configure_logging()
    settings = load_settings_from_env()
    for directory in (settings.media_dir, settings.config_dir, settings.state_dir):
        directory.mkdir(parents=True, exist_ok=True)

    channels_path = settings.channels_path or settings.config_dir / "channels.yml"
    channels_path.parent.mkdir(parents=True, exist_ok=True)

    state_store = DeliveryStateStore(settings)
    channel_store = ChannelRegistryStore(channels_path)
    upload_processor = UploadProcessor(settings=settings, state_store=state_store)
    application = build_application(
        settings,
        channel_store,
        state_store,
        upload_processor,
    )
    application.run_polling()


if __name__ == "__main__":
    main()
