from __future__ import annotations

import pytest

from rick_tv_pi.power_button import PowerButtonController


class FakeGPIO:
    BCM = 11
    IN = 1
    PUD_UP = 22

    def __init__(self, button_level: int) -> None:
        self.button_level = button_level
        self.mode = None
        self.setups = []

    def setmode(self, mode: int) -> None:
        self.mode = mode

    def setup(self, pin: int, mode: int, pull_up_down: int) -> None:
        self.setups.append((pin, mode, pull_up_down))

    def input(self, pin: int) -> int:
        assert pin == 26
        return self.button_level


def test_pwm_power_button_applies_active_low_on_state() -> None:
    gpio = FakeGPIO(button_level=0)
    commands = []
    display_states = []
    controller = PowerButtonController(
        gpio=gpio,
        command_runner=commands.append,
        display_power_setter=display_states.append,
        audio_profile="pwm",
    )

    controller.setup()
    changed = controller.poll_once()

    assert gpio.mode == gpio.BCM
    assert gpio.setups == [(26, gpio.IN, gpio.PUD_UP)]
    assert changed is True
    assert commands == [
        ("raspi-gpio", "set", "19", "op", "a5"),
        ("raspi-gpio", "set", "18", "ip"),
    ]
    assert display_states == [True]


def test_pwm_power_button_applies_off_transition_only_once() -> None:
    gpio = FakeGPIO(button_level=0)
    commands = []
    display_states = []
    controller = PowerButtonController(
        gpio=gpio,
        command_runner=commands.append,
        display_power_setter=display_states.append,
        audio_profile="pwm",
    )
    controller.setup()
    controller.poll_once()
    commands.clear()

    gpio.button_level = 1
    first_changed = controller.poll_once()
    second_changed = controller.poll_once()

    assert first_changed is True
    assert second_changed is False
    assert commands == [
        ("raspi-gpio", "set", "19", "ip"),
        ("raspi-gpio", "set", "18", "op", "dl"),
    ]
    assert display_states == [True, False]


def test_usb_dac_power_button_mutes_audio_without_changing_gpio19() -> None:
    gpio = FakeGPIO(button_level=0)
    commands = []
    display_states = []
    controller = PowerButtonController(
        gpio=gpio,
        command_runner=commands.append,
        display_power_setter=display_states.append,
        audio_profile="usb-dac",
    )
    controller.setup()

    controller.poll_once()
    gpio.button_level = 1
    controller.poll_once()

    assert commands == [
        ("raspi-gpio", "set", "18", "ip"),
        ("amixer", "-q", "-c", "1", "sset", "PCM", "unmute"),
        ("amixer", "-q", "-c", "1", "sset", "PCM", "mute"),
        ("raspi-gpio", "set", "18", "op", "dl"),
    ]
    assert display_states == [True, False]


def test_power_button_rejects_unknown_audio_profile() -> None:
    with pytest.raises(ValueError, match="unsupported audio profile: bluetooth"):
        PowerButtonController(
            gpio=FakeGPIO(button_level=1),
            command_runner=lambda command: None,
            display_power_setter=lambda enabled: None,
            audio_profile="bluetooth",
        )
