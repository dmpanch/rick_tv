from __future__ import annotations

import re
from pathlib import Path

from rick_tv_server.config import ServerSettings


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_REPEATED_UNDERSCORES = re.compile(r"_+")


def library_item_dir(settings: ServerSettings, channel_id: str, item_id: str) -> Path:
    return settings.media_dir / "library" / channel_id / item_id


def safe_filename(filename: str, *, default_stem: str = "media") -> str:
    name = Path(filename).name
    suffix = Path(name).suffix
    stem = Path(name).stem if suffix else name
    safe_stem = _sanitize_stem(stem, default_stem=default_stem)
    safe_suffix = _sanitize_suffix(suffix)
    return f"{safe_stem}{safe_suffix}"


def upload_delivery_filename(original_filename: str, item_id: str) -> str:
    safe_original = safe_filename(original_filename, default_stem="upload")
    stem = _sanitize_stem(Path(safe_original).stem, default_stem="upload")
    return f"{stem}--{item_id[:8]}.mp4"


def upload_library_paths(
    settings: ServerSettings,
    *,
    channel_id: str,
    item_id: str,
    original_filename: str,
) -> tuple[Path, Path]:
    item_dir = library_item_dir(settings, channel_id, item_id)
    original_path = item_dir / "original" / safe_filename(
        original_filename,
        default_stem="upload",
    )
    converted_path = item_dir / "converted" / upload_delivery_filename(
        original_filename,
        item_id,
    )
    return original_path, converted_path


def legacy_library_paths(
    settings: ServerSettings,
    *,
    channel_id: str,
    item_id: str,
    original_filename: str,
    delivery_filename: str,
) -> tuple[Path, Path]:
    item_dir = library_item_dir(settings, channel_id, item_id)
    return (
        item_dir / "original" / safe_filename(original_filename, default_stem=item_id),
        item_dir / "converted" / safe_filename(delivery_filename, default_stem=item_id),
    )


def relative_media_path(settings: ServerSettings, path: Path) -> str:
    return str(path.resolve(strict=False).relative_to(settings.media_dir.resolve(strict=False)))


def resolve_media_path(settings: ServerSettings, stored_path: str) -> Path:
    path = Path(stored_path)
    if path.is_absolute():
        return path
    return settings.media_dir / path


def unique_delivery_filename(
    *,
    filename: str,
    item_id: str,
    used_filenames: set[str],
) -> str:
    candidate = safe_filename(filename, default_stem=item_id)
    if candidate not in used_filenames:
        used_filenames.add(candidate)
        return candidate

    path = Path(candidate)
    suffix = path.suffix or ".mp4"
    stem = path.stem if path.suffix else candidate
    candidate = f"{stem}--{item_id[:8]}{suffix}"
    counter = 2
    while candidate in used_filenames:
        candidate = f"{stem}--{item_id[:8]}-{counter}{suffix}"
        counter += 1
    used_filenames.add(candidate)
    return candidate


def _sanitize_stem(stem: str, *, default_stem: str) -> str:
    sanitized = _UNSAFE_FILENAME_CHARS.sub("_", stem)
    sanitized = _REPEATED_UNDERSCORES.sub("_", sanitized).strip("._-")
    return sanitized or default_stem


def _sanitize_suffix(suffix: str) -> str:
    if not suffix:
        return ""
    sanitized = _UNSAFE_FILENAME_CHARS.sub("", suffix)
    return sanitized if sanitized.startswith(".") and len(sanitized) > 1 else ""
