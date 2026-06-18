import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ReadyProfile:
    width: int = 640
    height: int = 480
    max_video_bit_rate: int = 800_000
    max_audio_bit_rate: int = 128_000
    video_codec: str = "h264"
    pixel_format: str = "yuv420p"
    audio_codec: str = "aac"


def probe_media(path, runner=subprocess.run):
    result = runner(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=format_name,bit_rate:stream=codec_type,codec_name,pix_fmt,width,height,bit_rate",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def validate_ready_profile(path, profile=ReadyProfile(), runner=subprocess.run):
    try:
        media = probe_media(path, runner=runner)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return False

    format_names = {
        name.strip()
        for name in media.get("format", {}).get("format_name", "").split(",")
    }
    if "mp4" not in format_names:
        return False

    streams = media.get("streams", [])
    video_stream = _first_stream(streams, "video")
    audio_stream = _first_stream(streams, "audio")
    if video_stream is None or audio_stream is None:
        return False

    width = _positive_int(video_stream.get("width"))
    height = _positive_int(video_stream.get("height"))
    if width is None or height is None:
        return False
    video_bit_rate = _positive_int(video_stream.get("bit_rate"))
    audio_bit_rate = _positive_int(audio_stream.get("bit_rate"))
    if video_bit_rate is None or audio_bit_rate is None:
        return False

    return (
        video_stream.get("codec_name") == profile.video_codec
        and video_stream.get("pix_fmt") == profile.pixel_format
        and audio_stream.get("codec_name") == profile.audio_codec
        and width == profile.width
        and height == profile.height
        and video_bit_rate <= profile.max_video_bit_rate
        and audio_bit_rate <= profile.max_audio_bit_rate
    )


def _first_stream(streams, codec_type):
    return next(
        (
            stream
            for stream in streams
            if stream.get("codec_type") == codec_type
        ),
        None,
    )


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None
    return parsed
