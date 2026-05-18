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
