import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ConversionProfile:
    width: int = 640
    height: int = 480
    video_bitrate: str = "700k"
    audio_bitrate: str = "96k"


def build_ffmpeg_command(
    input_path: str | Path,
    output_path: str | Path,
    profile: ConversionProfile,
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-f",
        "mp4",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        f"scale={profile.width}:{profile.height}",
        "-b:v",
        profile.video_bitrate,
        "-c:a",
        "aac",
        "-b:a",
        profile.audio_bitrate,
        str(output_path),
    ]


def convert_to_ready_mp4(
    input_path: str | Path,
    output_path: str | Path,
    profile: ConversionProfile,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> subprocess.CompletedProcess:
    if Path(output_path).suffix.lower() != ".mp4":
        raise ValueError("converted output must use .mp4 extension")

    command = build_ffmpeg_command(input_path, output_path, profile)
    return runner(command, check=True)
