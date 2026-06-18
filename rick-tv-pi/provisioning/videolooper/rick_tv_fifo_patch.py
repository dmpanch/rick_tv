#!/usr/bin/env python3
from __future__ import annotations

"""Install Rick TV's pinned pi_video_looper overrides."""

from pathlib import Path
import os
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent
OVERRIDES = ROOT / "overrides"

DEFAULT_VIDEO_LOOPER_EGG = Path(
    "/usr/local/lib/python3.7/dist-packages/"
    "Adafruit_Video_Looper-1.0.21-py3.7.egg"
)
VIDEO_LOOPER_ZIP_NAME = "Adafruit_Video_Looper/video_looper.py"
VIDEO_LOOPER_OVERRIDE = OVERRIDES / "video_looper.py"

OMX_PLAYER_EGG = DEFAULT_VIDEO_LOOPER_EGG
OMX_PLAYER_ZIP_NAME = "Adafruit_Video_Looper/omxplayer.py"
OMX_PLAYER_OVERRIDE = OVERRIDES / "omxplayer.py"

PYC_SUFFIXES = (".pyc", ".pyo")


def main() -> None:
    egg_path = Path(
        os.environ.get("RICK_TV_VIDEOLOOPER_EGG_PATH", str(DEFAULT_VIDEO_LOOPER_EGG))
    )
    install_overrides(
        egg_path,
        {
            VIDEO_LOOPER_ZIP_NAME: VIDEO_LOOPER_OVERRIDE,
            OMX_PLAYER_ZIP_NAME: OMX_PLAYER_OVERRIDE,
        },
    )


def install_overrides(egg_path: Path, replacements: dict[str, Path]) -> None:
    for zip_name, source_path in replacements.items():
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing override for {zip_name}: {source_path}")
        compile(source_path.read_text(), str(source_path), "exec")

    if egg_path.is_dir():
        _install_into_directory(egg_path, replacements)
        return

    if not egg_path.is_file():
        raise FileNotFoundError(f"Missing pi_video_looper egg: {egg_path}")

    _install_into_zip(egg_path, replacements)


def _install_into_directory(egg_path: Path, replacements: dict[str, Path]) -> None:
    for zip_name, source_path in replacements.items():
        target_path = egg_path / zip_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(source_path.read_bytes())

    for pycache in egg_path.rglob("__pycache__"):
        for compiled in pycache.iterdir():
            if compiled.suffix in PYC_SUFFIXES:
                compiled.unlink()


def _install_into_zip(egg_path: Path, replacements: dict[str, Path]) -> None:
    with zipfile.ZipFile(str(egg_path), "r") as source:
        existing_names = {item.filename for item in source.infolist()}
        missing = sorted(set(replacements) - existing_names)
        if missing:
            raise RuntimeError(
                f"Cannot install pi_video_looper overrides; missing egg entries: {', '.join(missing)}"
            )

        fd, tmp_name = tempfile.mkstemp(prefix="rick-tv-videolooper-", suffix=".egg")
        os.close(fd)
        tmp_path = Path(tmp_name)

        try:
            with zipfile.ZipFile(str(tmp_path), "w") as target:
                for item in source.infolist():
                    if _is_stale_bytecode(item.filename, replacements):
                        continue
                    data = source.read(item.filename)
                    if item.filename in replacements:
                        data = replacements[item.filename].read_bytes()
                    target.writestr(item, data)
            tmp_path.replace(egg_path)
            os.chmod(str(egg_path), 0o644)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise


def _is_stale_bytecode(filename: str, replacements: dict[str, Path]) -> bool:
    if not filename.endswith(PYC_SUFFIXES):
        return False
    if "/__pycache__/" not in filename:
        return False

    for zip_name in replacements:
        module = Path(zip_name).stem
        if f"/__pycache__/{module}." in filename:
            return True
    return False


if __name__ == "__main__":
    main()
