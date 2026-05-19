from pathlib import Path

from rick_tv_pi.channels import Channel
from rick_tv_pi.navigation import ChannelNavigator


def test_select_initial_channel_once():
    channels = [
        Channel("01_Citadel", 1, None, Path("/media/01_Citadel")),
        Channel("02_Cable", 2, None, Path("/media/02_Cable")),
    ]
    player = FakePlayer()
    navigator = ChannelNavigator()

    navigator.refresh_channels(channels)
    navigator.select_initial(player)
    navigator.select_initial(player)

    assert navigator.current_channel == channels[0]
    assert player.selected == [channels[0]]


def test_next_and_previous_wrap_around():
    channels = [
        Channel("01_Citadel", 1, None, Path("/media/01_Citadel")),
        Channel("02_Cable", 2, None, Path("/media/02_Cable")),
    ]
    player = FakePlayer()
    navigator = ChannelNavigator()
    navigator.refresh_channels(channels)
    navigator.select_initial(player)

    navigator.apply_action("next", player)
    navigator.apply_action("next", player)
    navigator.apply_action("previous", player)

    assert player.selected == [channels[0], channels[1], channels[0], channels[1]]
    assert navigator.current_channel == channels[1]


def test_navigator_ignores_actions_without_channels():
    player = FakePlayer()
    navigator = ChannelNavigator()

    navigator.apply_action("next", player)

    assert player.selected == []
    assert navigator.current_channel is None


class FakePlayer:
    def __init__(self):
        self.selected = []

    def select_channel(self, channel):
        self.selected.append(channel)
