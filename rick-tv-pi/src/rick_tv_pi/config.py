from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PiSettings:
    server_base_url: str
    api_token: str
    media_root: Path
    poll_interval_seconds: int = 60
    metadata_path: Path | None = None
