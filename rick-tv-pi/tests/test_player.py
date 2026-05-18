from rick_tv_pi.channels import Channel
from rick_tv_pi.player import PlaybackController


def test_empty_channel_is_selectable(tmp_path):
    channel_path = tmp_path / "01_Empty"
    channel_path.mkdir()
    channel = Channel(
        id="01_Empty",
        number=1,
        display_name=None,
        path=channel_path,
    )
    controller = PlaybackController()

    controller.select_channel(channel)

    assert controller.screen_state == "empty"
    assert controller.current_file is None


def test_empty_channel_autostarts_when_file_appears(tmp_path):
    channel_path = tmp_path / "01_Empty"
    channel_path.mkdir()
    channel = Channel(
        id="01_Empty",
        number=1,
        display_name=None,
        path=channel_path,
    )
    controller = PlaybackController()
    controller.select_channel(channel)
    (channel_path / "episode.mp4").touch()

    controller.rescan_current_channel()

    assert controller.screen_state == "playing"
    assert controller.current_file is not None
    assert controller.current_file.path.name == "episode.mp4"
