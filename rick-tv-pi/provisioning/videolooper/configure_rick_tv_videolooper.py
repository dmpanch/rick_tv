#!/usr/bin/env python3
"""Configure /boot/video_looper.ini for Rick TV channel playlists."""

import configparser
import os
from pathlib import Path


CONFIG_PATH = Path(os.environ.get("RICK_TV_VIDEOLOOPER_CONFIG_PATH", "/boot/video_looper.ini"))
DEFAULT_AUDIO_PROFILE = "usb-dac"
SUPPORTED_AUDIO_PROFILES = {"pwm", "usb-dac"}


def configure_audio(config: configparser.ConfigParser, profile: str) -> None:
    if profile not in SUPPORTED_AUDIO_PROFILES:
        raise SystemExit("unsupported RICK_TV_AUDIO_PROFILE: {}".format(profile))

    if not config.has_section("omxplayer"):
        config.add_section("omxplayer")
    if not config.has_section("alsa"):
        config.add_section("alsa")

    if profile == "pwm":
        config.set("omxplayer", "sound", "both")
        config.set("alsa", "hw_device", "")
        config.remove_option("alsa", "hw_vol")
        config.set("alsa", "hw_vol_control", "PCM")
        return

    config.set("omxplayer", "sound", "alsa")
    config.set("alsa", "hw_device", "1,0")
    config.set("alsa", "hw_vol", "100%")
    config.set("alsa", "hw_vol_control", "PCM")


def main() -> None:
    audio_profile = os.environ.get(
        "RICK_TV_AUDIO_PROFILE", DEFAULT_AUDIO_PROFILE
    ).strip().lower()
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(str(CONFIG_PATH))

    if not config.has_section("video_looper"):
        config.add_section("video_looper")
    config.set("video_looper", "video_player", "omxplayer")
    config.set("video_looper", "file_reader", "directory")
    config.set("video_looper", "osd", "false")
    config.set("video_looper", "countdown_time", "0")
    config.set("video_looper", "wait_time", "0")
    config.set("video_looper", "datetime_display", "false")
    config.set("video_looper", "is_random", "false")
    config.set("video_looper", "console_output", "true")

    if not config.has_section("directory"):
        config.add_section("directory")
    config.set("directory", "path", "/home/pi/rick-tv")

    if not config.has_section("playlist"):
        config.add_section("playlist")
    config.set("playlist", "path", "playlists/channels.m3u")

    if not config.has_section("control"):
        config.add_section("control")
    config.set("control", "keyboard_control", "false")
    config.set("control", "gpio_pin_mode", "true")
    config.set("control", "gpio_pin_map", "")

    configure_audio(config, audio_profile)
    config.set("omxplayer", "show_titles", "true")

    if not config.has_section("rick_tv"):
        config.add_section("rick_tv")
    config.set("rick_tv", "command_fifo", "/tmp/rick-tv-videolooper.fifo")

    with CONFIG_PATH.open("w") as config_file:
        config.write(config_file)


if __name__ == "__main__":
    main()
