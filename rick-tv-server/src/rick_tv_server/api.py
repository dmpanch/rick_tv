from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from rick_tv_server.channels import ChannelRegistryStore
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/ready", dependencies=[Depends(require_bearer_token)])
    def ready(channels: str = Query(...)) -> dict[str, list[dict[str, str]]]:
        channel_ids = [channel_id for channel_id in channels.split(",") if channel_id]
        return {
            "items": [
                _ready_item_response(settings, item)
                for item in state_store.ready_items_for_channels(channel_ids)
            ],
            "deletions": [
                _delete_item_response(item)
                for item in state_store.device_delete_items_for_channels(channel_ids)
            ],
        }

    @app.get("/api/v1/channels.yml", dependencies=[Depends(require_bearer_token)])
    def channels_yml() -> Response:
        channels_path = settings.channels_path or settings.config_dir / "channels.yml"
        registry = ChannelRegistryStore(channels_path)
        if not channels_path.exists():
            return Response(content="channels: {}\n", media_type="application/yaml")
        return Response(content=registry.dump_text(), media_type="application/yaml")

    @app.get("/api/v1/download/{item_id}", dependencies=[Depends(require_bearer_token)])
    def download(item_id: str) -> FileResponse:
        item = state_store.get_item(item_id)
        if (
            item is None
            or item.status != "pending"
            or item.converted_path is None
            or not item.converted_path.exists()
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

        return FileResponse(item.converted_path)

    @app.post("/api/v1/ack/{item_id}", dependencies=[Depends(require_bearer_token)])
    def ack(item_id: str) -> Response:
        item = state_store.get_item(item_id)
        if item is None or item.status in {
            "uploaded",
            "converting",
            "failed",
            "canceled",
            "deleted_server_side",
            "deleted_from_library",
        }:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

        if item.status == "pending":
            state_store.ack_item(item_id)

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/v1/delete-ack/{item_id}",
        dependencies=[Depends(require_bearer_token)],
    )
    def delete_ack(item_id: str) -> Response:
        item = state_store.get_item(item_id)
        if item is None or item.status not in {
            "deleted_server_side",
            "deleted_from_library",
        }:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

        if item.status == "deleted_server_side":
            state_store.ack_device_delete(item_id)

        return Response(status_code=status.HTTP_204_NO_CONTENT)

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


def _delete_item_response(item: DeliveryItem) -> dict[str, str]:
    if item.channel_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Delete item is missing channel metadata",
        )

    filename = item.filename
    if filename is None and item.converted_path is not None:
        filename = item.converted_path.name
    if filename is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Delete item is missing filename metadata",
        )

    return {
        "id": item.item_id,
        "channel_id": item.channel_id,
        "filename": filename,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as media_file:
        for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
