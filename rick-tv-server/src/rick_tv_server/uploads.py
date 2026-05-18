from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Callable

from rick_tv_server.config import ServerSettings
from rick_tv_server.converter import ConversionProfile, convert_to_ready_mp4
from rick_tv_server.state import DeliveryItem, DeliveryStateStore

UploadConverter = Callable[[Path, Path], object]
ItemIdFactory = Callable[[], str]


class UploadProcessor:
    def __init__(
        self,
        *,
        settings: ServerSettings,
        state_store: DeliveryStateStore,
        converter: UploadConverter | None = None,
        item_id_factory: ItemIdFactory | None = None,
    ):
        self.settings = settings
        self.state_store = state_store
        self.converter = converter or self._convert_to_ready_mp4
        self.item_id_factory = item_id_factory or (lambda: uuid.uuid4().hex)

    def process_upload(
        self,
        *,
        user_id: str,
        channel_id: str,
        source_path: Path,
        original_filename: str,
    ) -> DeliveryItem:
        item_id = self.item_id_factory()
        if item_id in self.state_store.items:
            raise ValueError(f"delivery item already exists: {item_id}")

        original_path = self._uploaded_path(item_id, original_filename, source_path)
        converted_path = self.settings.media_dir / "converted" / f"{item_id}.mp4"

        original_path.parent.mkdir(parents=True, exist_ok=True)
        converted_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, original_path)

        self.state_store.create_uploaded_item(
            item_id=item_id,
            user_id=user_id,
            original_path=original_path,
        )
        self.state_store.mark_converting(item_id)

        self.converter(original_path, converted_path)
        sha256 = _sha256_file(converted_path)

        return self.state_store.mark_pending(
            item_id,
            converted_path=converted_path,
            channel_id=channel_id,
            filename=converted_path.name,
            sha256=sha256,
        )

    def _uploaded_path(
        self,
        item_id: str,
        original_filename: str,
        source_path: Path,
    ) -> Path:
        suffix = Path(original_filename).suffix or source_path.suffix
        return self.settings.media_dir / "uploaded" / f"{item_id}{suffix}"

    @staticmethod
    def _convert_to_ready_mp4(input_path: Path, output_path: Path) -> object:
        return convert_to_ready_mp4(input_path, output_path, ConversionProfile())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as media_file:
        for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
