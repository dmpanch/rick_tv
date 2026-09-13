from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional, Tuple


Command = Tuple[str, ...]
CommandRunner = Callable[[Command], None]
DisplayPowerSetter = Callable[[bool], None]
SUPPORTED_AUDIO_PROFILES = {"pwm", "usb-dac"}
BACKLIGHT_POWER_PATH = Path("/sys/class/backlight/rpi_backlight/bl_power")


class PowerButtonController:
    def __init__(
        self,
        gpio: Any,
        command_runner: CommandRunner,
        display_power_setter: DisplayPowerSetter,
        audio_profile: str,
    ) -> None:
        normalized_profile = audio_profile.strip().lower()
        if normalized_profile not in SUPPORTED_AUDIO_PROFILES:
            raise ValueError(
                "unsupported audio profile: {}".format(normalized_profile)
            )
        self._gpio = gpio
        self._run_command = command_runner
        self._set_display_power = display_power_setter
        self._audio_profile = normalized_profile
        self._screen_on: Optional[bool] = None

    def setup(self) -> None:
        self._gpio.setmode(self._gpio.BCM)
        self._gpio.setup(26, self._gpio.IN, pull_up_down=self._gpio.PUD_UP)

    def poll_once(self) -> bool:
        screen_on = not bool(self._gpio.input(26))
        if screen_on == self._screen_on:
            return False

        if screen_on:
            self._turn_on()
        else:
            self._turn_off()
        self._screen_on = screen_on
        return True

    def _turn_on(self) -> None:
        if self._audio_profile == "pwm":
            self._run_command(("raspi-gpio", "set", "19", "op", "a5"))
        self._run_command(("raspi-gpio", "set", "18", "ip"))
        self._set_display_power(True)
        if self._audio_profile == "usb-dac":
            self._run_command(
                ("amixer", "-q", "-c", "1", "sset", "PCM", "unmute")
            )

    def _turn_off(self) -> None:
        if self._audio_profile == "usb-dac":
            self._run_command(
                ("amixer", "-q", "-c", "1", "sset", "PCM", "mute")
            )
        if self._audio_profile == "pwm":
            self._run_command(("raspi-gpio", "set", "19", "ip"))
        self._run_command(("raspi-gpio", "set", "18", "op", "dl"))
        self._set_display_power(False)


def run_system_command(command: Command) -> None:
    subprocess.run(command, check=False)


def set_backlight_power(enabled: bool) -> None:
    BACKLIGHT_POWER_PATH.write_text("0\n" if enabled else "1\n", encoding="ascii")


def main() -> None:
    import RPi.GPIO as GPIO

    controller = PowerButtonController(
        gpio=GPIO,
        command_runner=run_system_command,
        display_power_setter=set_backlight_power,
        audio_profile=os.environ.get("RICK_TV_AUDIO_PROFILE", "usb-dac"),
    )
    controller.setup()
    while True:
        controller.poll_once()
        time.sleep(0.3)


if __name__ == "__main__":
    main()
