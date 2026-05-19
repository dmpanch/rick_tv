from rick_tv_pi.channels import Channel
from rick_tv_pi.player import PlaybackController


class FakeProcess:
    def __init__(self) -> None:
        self.terminated = False

    def poll(self):
        return None if not self.terminated else 0

    def terminate(self) -> None:
        self.terminated = True


class FakeProcessFactory:
    def __init__(self) -> None:
        self.commands = []
        self.processes = []

    def __call__(self, command):
        self.commands.append(command)
        process = FakeProcess()
        self.processes.append(process)
        return process


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
    process_factory = FakeProcessFactory()
    controller = PlaybackController(
        player_command="mpv --fs",
        process_factory=process_factory,
    )
    controller.select_channel(channel)
    (channel_path / "episode.mp4").touch()

    controller.rescan_current_channel()

    assert controller.screen_state == "playing"
    assert controller.current_file is not None
    assert controller.current_file.path.name == "episode.mp4"
    assert process_factory.commands == [["mpv", "--fs", str(channel_path / "episode.mp4")]]


def test_playback_is_not_restarted_for_same_running_file(tmp_path):
    channel_path = tmp_path / "01_Empty"
    channel_path.mkdir()
    (channel_path / "episode.mp4").touch()
    channel = Channel(id="01_Empty", number=1, display_name=None, path=channel_path)
    process_factory = FakeProcessFactory()
    controller = PlaybackController(process_factory=process_factory)

    controller.select_channel(channel)
    controller.rescan_current_channel()

    assert len(process_factory.commands) == 1


def test_playback_stops_when_channel_becomes_empty(tmp_path):
    channel_path = tmp_path / "01_Empty"
    channel_path.mkdir()
    episode = channel_path / "episode.mp4"
    episode.touch()
    channel = Channel(id="01_Empty", number=1, display_name=None, path=channel_path)
    process_factory = FakeProcessFactory()
    controller = PlaybackController(process_factory=process_factory)
    controller.select_channel(channel)

    episode.unlink()
    controller.rescan_current_channel()

    assert controller.screen_state == "empty"
    assert controller.current_file is None
    assert process_factory.processes[0].terminated is True
