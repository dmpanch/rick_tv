from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Callable

from rick_tv_server.config import ServerSettings
from rick_tv_server.converter import (
    ConversionProfile,
    convert_to_ready_mp4,
    strict_conversion_profile,
)
from rick_tv_server.library_paths import upload_library_paths
from rick_tv_server.state import DeliveryItem, DeliveryStateStore
from rick_tv_server.validator import validate_ready_profile

UploadConverter = Callable[[Path, Path], object]
UploadValidator = Callable[[Path], bool]
ItemIdFactory = Callable[[], str]


class UploadProcessingError(RuntimeError):
    pass


class UploadProcessor:
    def __init__(
        self,
        *,
        settings: ServerSettings,
        state_store: DeliveryStateStore,
        converter: UploadConverter | None = None,
        retry_converter: UploadConverter | None = None,
        validator: UploadValidator | None = None,
        item_id_factory: ItemIdFactory | None = None,
    ):
        self.settings = settings
        self.state_store = state_store
        self.converter = converter or self._convert_to_ready_mp4
        self.retry_converter = retry_converter or self._convert_to_strict_ready_mp4
        self.validator = validator or validate_ready_profile
        self.item_id_factory = item_id_factory or (lambda: uuid.uuid4().hex)

    def process_upload(
        self,
        *,
        channel_id: str,
        source_path: Path,
        original_filename: str,
    ) -> DeliveryItem:
        item_id = self.item_id_factory()
        if self.state_store.get_item(item_id) is not None:
            raise ValueError(f"delivery item already exists: {item_id}")

        original_path, converted_path = upload_library_paths(
            self.settings,
            channel_id=channel_id,
            item_id=item_id,
            original_filename=original_filename,
        )

        original_path.parent.mkdir(parents=True, exist_ok=True)
        converted_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, original_path)

        self.state_store.create_uploaded_item(
            item_id=item_id,
            channel_id=channel_id,
            original_path=original_path,
        )
        self.state_store.mark_converting(item_id)

        try:
            self.converter(original_path, converted_path)
            if not self.validator(converted_path):
                self.retry_converter(original_path, converted_path)
                if not self.validator(converted_path):
                    raise UploadProcessingError(
                        "Video could not be prepared for Rick TV playback."
                    )
        except UploadProcessingError as exc:
            self.state_store.mark_failed(
                item_id,
                message=str(exc),
            )
            raise
        except Exception as exc:
            message = "Video could not be prepared for Rick TV playback."
            self.state_store.mark_failed(
                item_id,
                message=message,
            )
            raise UploadProcessingError(message) from exc

        sha256 = _sha256_file(converted_path)

        return self.state_store.mark_pending(
            item_id,
            converted_path=converted_path,
            filename=converted_path.name,
            sha256=sha256,
        )

    @staticmethod
    def _convert_to_ready_mp4(input_path: Path, output_path: Path) -> object:
        return convert_to_ready_mp4(input_path, output_path, ConversionProfile())

    @staticmethod
    def _convert_to_strict_ready_mp4(input_path: Path, output_path: Path) -> object:
        return convert_to_ready_mp4(
            input_path,
            output_path,
            strict_conversion_profile(),
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as media_file:
        for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
