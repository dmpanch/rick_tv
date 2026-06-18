import subprocess

import pytest

from rick_tv_server.converter import (
    ConversionProfile,
    build_ffmpeg_command,
    convert_to_ready_mp4,
    strict_conversion_profile,
)


def test_ffmpeg_command_targets_pi_ready_profile():
    command = build_ffmpeg_command(
        input_path="/tmp/uploads/source.mov",
        output_path="/tmp/converted/ready.mp4",
        profile=ConversionProfile(),
    )

    assert command[:2] == ["ffmpeg", "-y"]
    assert "-f" in command
    assert command[command.index("-f") + 1] == "mp4"
    assert "-c:v" in command
    assert command[command.index("-c:v") + 1] == "libx264"
    assert "-pix_fmt" in command
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert "-c:a" in command
    assert command[command.index("-c:a") + 1] == "aac"
    assert "-vf" in command
    assert command[command.index("-vf") + 1] == "scale=640:480"
    assert "-b:v" in command
    assert command[command.index("-b:v") + 1] == "700k"
    assert command[-1] == "/tmp/converted/ready.mp4"


def test_convert_to_ready_mp4_runs_ffmpeg_with_check():
    calls = []

    def runner(command, check):
        calls.append((command, check))
        return subprocess.CompletedProcess(command, 0)

    convert_to_ready_mp4(
        input_path="/tmp/uploads/source.mov",
        output_path="/tmp/converted/ready.mp4",
        profile=ConversionProfile(),
        runner=runner,
    )

    assert len(calls) == 1
    command, check = calls[0]
    assert command[0] == "ffmpeg"
    assert "-i" in command
    assert command[command.index("-i") + 1] == "/tmp/uploads/source.mov"
    assert command[-1] == "/tmp/converted/ready.mp4"
    assert check is True


def test_convert_to_ready_mp4_requires_mp4_output():
    with pytest.raises(ValueError, match="mp4"):
        convert_to_ready_mp4(
            input_path="/tmp/uploads/source.mov",
            output_path="/tmp/converted/ready.webm",
            profile=ConversionProfile(),
            runner=lambda command, check: None,
        )


def test_convert_to_ready_mp4_raises_on_ffmpeg_failure():
    expected = subprocess.CalledProcessError(1, ["ffmpeg"])

    def runner(command, check):
        raise expected

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        convert_to_ready_mp4(
            input_path="/tmp/uploads/source.mov",
            output_path="/tmp/converted/ready.mp4",
            profile=ConversionProfile(),
            runner=runner,
        )

    assert exc_info.value is expected


def test_strict_ffmpeg_command_adds_bitrate_caps_and_faststart():
    command = build_ffmpeg_command(
        input_path="/tmp/uploads/source.mov",
        output_path="/tmp/converted/ready.mp4",
        profile=strict_conversion_profile(),
    )

    assert command[command.index("-b:v") + 1] == "650k"
    assert "-maxrate" in command
    assert command[command.index("-maxrate") + 1] == "700k"
    assert "-bufsize" in command
    assert command[command.index("-bufsize") + 1] == "1400k"
    assert "-r" in command
    assert command[command.index("-r") + 1] == "30"
    assert "-ac" in command
    assert command[command.index("-ac") + 1] == "2"
    assert "-ar" in command
    assert command[command.index("-ar") + 1] == "44100"
    assert "-movflags" in command
    assert command[command.index("-movflags") + 1] == "+faststart"
