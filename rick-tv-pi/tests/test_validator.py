import json
import subprocess

from rick_tv_pi.validator import validate_ready_profile


def _completed_probe(payload):
    return subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )


def _ready_probe(
    *,
    pixel_format="yuv420p",
    width=640,
    height=480,
    video_bit_rate="700000",
    audio_bit_rate="96000",
    format_bit_rate="796000",
):
    return {
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "bit_rate": format_bit_rate,
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "pix_fmt": pixel_format,
                "width": width,
                "height": height,
                "bit_rate": video_bit_rate,
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "bit_rate": audio_bit_rate,
            },
        ],
    }


def test_validate_ready_profile_accepts_target_mp4_h264_aac():
    def runner(*args, **kwargs):
        return _completed_probe(_ready_probe())

    assert validate_ready_profile("episode.mp4", runner=runner) is True


def test_validate_ready_profile_rejects_wrong_pixel_format():
    def runner(*args, **kwargs):
        return _completed_probe(_ready_probe(pixel_format="yuv422p"))

    assert validate_ready_profile("episode.mp4", runner=runner) is False


def test_validate_ready_profile_rejects_non_target_dimensions():
    def runner(*args, **kwargs):
        return _completed_probe(_ready_probe(width=480, height=320))

    assert validate_ready_profile("episode.mp4", runner=runner) is False


def test_validate_ready_profile_rejects_excessive_video_bitrate():
    def runner(*args, **kwargs):
        return _completed_probe(_ready_probe(video_bit_rate="1400000"))

    assert validate_ready_profile("episode.mp4", runner=runner) is False


def test_validate_ready_profile_rejects_missing_video_bitrate():
    payload = _ready_probe()
    del payload["streams"][0]["bit_rate"]

    def runner(*args, **kwargs):
        return _completed_probe(payload)

    assert validate_ready_profile("episode.mp4", runner=runner) is False


def test_validate_ready_profile_rejects_missing_dimensions():
    payload = _ready_probe()
    del payload["streams"][0]["width"]

    def runner(*args, **kwargs):
        return _completed_probe(payload)

    assert validate_ready_profile("episode.mp4", runner=runner) is False


def test_validate_ready_profile_rejects_malformed_dimensions():
    payload = _ready_probe()
    payload["streams"][0]["width"] = "N/A"

    def runner(*args, **kwargs):
        return _completed_probe(payload)

    assert validate_ready_profile("episode.mp4", runner=runner) is False
