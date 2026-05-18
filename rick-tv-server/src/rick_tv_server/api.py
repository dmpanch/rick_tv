from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from rick_tv_server.config import ServerSettings
from rick_tv_server.state import DeliveryItem, DeliveryStateStore

bearer_scheme = HTTPBearer(auto_error=False)


def create_app(settings: ServerSettings, state_store: DeliveryStateStore) -> FastAPI:
    app = FastAPI()

    def require_bearer_token(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> None:
        if credentials is None or not secrets.compare_digest(
            credentials.credentials,
            settings.api_token,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/api/v1/ready", dependencies=[Depends(require_bearer_token)])
    def ready(channels: str = Query(...)) -> dict[str, list[dict[str, str]]]:
        channel_ids = [channel_id for channel_id in channels.split(",") if channel_id]
        return {
            "items": [
                _ready_item_response(settings, item)
                for item in state_store.ready_items_for_channels(channel_ids)
            ]
        }

    return app


def _ready_item_response(settings: ServerSettings, item: DeliveryItem) -> dict[str, str]:
    if item.converted_path is None or item.channel_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ready item is missing delivery metadata",
        )

    return {
        "id": item.item_id,
        "channel_id": item.channel_id,
        "filename": item.converted_path.name,
        "download_url": f"{settings.public_base_url.rstrip('/')}/api/v1/download/{item.item_id}",
        "sha256": _sha256_file(item.converted_path),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as media_file:
        for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
