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
    video_maxrate: str | None = None
    video_bufsize: str | None = None
    frame_rate: str | None = None
    audio_channels: int | None = None
    audio_sample_rate: str | None = None
    movflags: str | None = None


def strict_conversion_profile() -> ConversionProfile:
    return ConversionProfile(
        video_bitrate="650k",
        audio_bitrate="96k",
        video_maxrate="700k",
        video_bufsize="1400k",
        frame_rate="30",
        audio_channels=2,
        audio_sample_rate="44100",
        movflags="+faststart",
    )


def build_ffmpeg_command(
    input_path: str | Path,
    output_path: str | Path,
    profile: ConversionProfile,
) -> list[str]:
    command = [
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
    ]
    if profile.video_maxrate is not None:
        command.extend(["-maxrate", profile.video_maxrate])
    if profile.video_bufsize is not None:
        command.extend(["-bufsize", profile.video_bufsize])
    if profile.frame_rate is not None:
        command.extend(["-r", profile.frame_rate])
    command.extend(["-c:a", "aac", "-b:a", profile.audio_bitrate])
    if profile.audio_channels is not None:
        command.extend(["-ac", str(profile.audio_channels)])
    if profile.audio_sample_rate is not None:
        command.extend(["-ar", profile.audio_sample_rate])
    if profile.movflags is not None:
        command.extend(["-movflags", profile.movflags])
    command.append(str(output_path))
    return command


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
