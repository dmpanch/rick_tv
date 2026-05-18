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
