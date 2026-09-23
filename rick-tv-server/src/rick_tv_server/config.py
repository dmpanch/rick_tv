from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerSettings:
    media_dir: Path
    config_dir: Path
    state_dir: Path
    api_token: str
    public_base_url: str
    telegram_bot_token: str | None = None
    telegram_allowed_user_ids: tuple[int, ...] = ()
    channels_path: Path | None = None
    db_path: Path | None = None
    telegram_local_api_url: str | None = None
