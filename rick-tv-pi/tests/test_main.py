from pathlib import Path

from rick_tv_pi.config import PiSettings
from rick_tv_pi.main import (
    RuntimeState,
    TouchActionQueue,
    load_settings_from_env,
    load_touch_settings_from_env,
    load_videolooper_settings_from_env,
    run_runtime_cycle,
)


def test_load_settings_from_env_reads_required_and_optional_values(monkeypatch):
    monkeypatch.setenv("RICK_TV_SERVER_URL", "https://rick-tv.example")
    monkeypatch.setenv("RICK_TV_API_TOKEN", "test-token")
    monkeypatch.setenv("RICK_TV_MEDIA_ROOT", "/var/lib/rick-tv/media")
    monkeypatch.setenv("RICK_TV_METADATA_PATH", "/etc/rick-tv/channels.json")

    settings = load_settings_from_env()

    assert settings.server_base_url == "https://rick-tv.example"
    assert settings.api_token == "test-token"
    assert settings.media_root == Path("/var/lib/rick-tv/media")
    assert settings.metadata_path == Path("/etc/rick-tv/channels.json")
    assert settings.poll_interval_seconds == 60
    assert settings.remote_poll_interval_seconds == 2


def test_load_videolooper_settings_from_env_reads_playlist_root_and_command_path(monkeypatch):
    monkeypatch.setenv("RICK_TV_VIDEOLOOPER_PLAYLIST_ROOT", "/home/pi/rick-tv/playlists")
    monkeypatch.setenv("RICK_TV_VIDEOLOOPER_COMMAND_PATH", "/tmp/rick-tv.fifo")
    monkeypatch.setenv("RICK_TV_CHANNEL_SHUFFLE_SECONDS", "7200")

    settings = load_videolooper_settings_from_env()

    assert settings.playlist_root == Path("/home/pi/rick-tv/playlists")
    assert settings.command_path == Path("/tmp/rick-tv.fifo")
    assert settings.channel_shuffle_seconds == 7200


def test_load_touch_settings_from_env_supports_screen_size_and_axis_options(monkeypatch):
    monkeypatch.setenv("RICK_TV_TOUCH_SCREEN_WIDTH", "640")
    monkeypatch.setenv("RICK_TV_TOUCH_SCREEN_HEIGHT", "480")
    monkeypatch.setenv("RICK_TV_TOUCH_SWAP_AXES", "true")
    monkeypatch.setenv("RICK_TV_TOUCH_GESTURE_HORIZONTAL_AXIS", "y")
    monkeypatch.setenv("RICK_TV_TOUCH_INVERT_X", "1")
    monkeypatch.setenv("RICK_TV_TOUCH_INVERT_Y", "yes")
    monkeypatch.setenv("RICK_TV_TOUCH_DEVICE", "/dev/input/event4")

    settings = load_touch_settings_from_env()

    assert settings.screen_width == 640
    assert settings.screen_height == 480
    assert settings.swap_axes == "true"
    assert settings.gesture_horizontal_axis == "y"
    assert settings.invert_x is True
    assert settings.invert_y is True
    assert settings.device_path == "/dev/input/event4"


def test_load_touch_settings_from_env_defaults_axis_swap_to_auto(monkeypatch):
    monkeypatch.delenv("RICK_TV_TOUCH_SWAP_AXES", raising=False)

    settings = load_touch_settings_from_env()

    assert settings.swap_axes == "auto"


def test_runtime_cycle_logs_poll_failure_and_rescans_channel(tmp_path, caplog):
    channel_path = tmp_path / "01_Citadel"
    channel_path.mkdir()
    (channel_path / "episode.mp4").touch()
    settings = PiSettings(
        server_base_url="https://rick-tv.example",
        api_token="test-token",
        media_root=tmp_path,
    )
    player = FakePlayer()
    poller = FailingPoller()
    state = RuntimeState()

    run_runtime_cycle(settings=settings, player=player, poller=poller, state=state)

    assert poller.poll_count == 1
    assert player.rescan_count == 1
    assert "Pi runtime poll failed" in caplog.text


def test_runtime_cycle_does_not_reselect_initial_channel(tmp_path):
    channel_path = tmp_path / "01_Citadel"
    channel_path.mkdir()
    (channel_path / "episode.mp4").touch()
    settings = PiSettings(
        server_base_url="https://rick-tv.example",
        api_token="test-token",
        media_root=tmp_path,
    )
    player = FakePlayer()
    poller = SuccessfulPoller()
    state = RuntimeState()

    run_runtime_cycle(settings=settings, player=player, poller=poller, state=state)
    run_runtime_cycle(settings=settings, player=player, poller=poller, state=state)

    assert player.select_count == 1
    assert player.rescan_count == 2


def test_runtime_cycle_rescans_playing_channel_to_restart_dead_player(tmp_path):
    channel_path = tmp_path / "01_Citadel"
    channel_path.mkdir()
    (channel_path / "episode.mp4").touch()
    settings = PiSettings(
        server_base_url="https://rick-tv.example",
        api_token="test-token",
        media_root=tmp_path,
    )
    player = FakePlayer()
    player.screen_state = "playing"
    poller = SuccessfulPoller()
    state = RuntimeState()

    run_runtime_cycle(settings=settings, player=player, poller=poller, state=state)

    assert player.rescan_count == 1


def test_runtime_cycle_applies_touch_navigation_before_rescan(tmp_path):
    (tmp_path / "01_Citadel").mkdir()
    (tmp_path / "02_Cable").mkdir()
    (tmp_path / "01_Citadel" / "episode.mp4").touch()
    (tmp_path / "02_Cable" / "episode.mp4").touch()
    settings = PiSettings(
        server_base_url="https://rick-tv.example",
        api_token="test-token",
        media_root=tmp_path,
    )
    player = FakePlayer()
    poller = SuccessfulPoller()
    touch_actions = FakeTouchActions(["next", "previous"])
    state = RuntimeState()

    run_runtime_cycle(
        settings=settings,
        player=player,
        poller=poller,
        state=state,
        touch_actions=touch_actions,
    )
    run_runtime_cycle(
        settings=settings,
        player=player,
        poller=poller,
        state=state,
        touch_actions=touch_actions,
    )

    assert [channel.id for channel in player.selected_channels] == [
        "01_Citadel",
        "02_Cable",
        "01_Citadel",
    ]


def test_runtime_cycle_applies_touch_navigation_between_server_polls(tmp_path):
    (tmp_path / "01_Citadel").mkdir()
    (tmp_path / "02_Cable").mkdir()
    (tmp_path / "01_Citadel" / "episode.mp4").touch()
    (tmp_path / "02_Cable" / "episode.mp4").touch()
    settings = PiSettings(
        server_base_url="https://rick-tv.example",
        api_token="test-token",
        media_root=tmp_path,
        poll_interval_seconds=60,
    )
    player = FakePlayer()
    poller = SuccessfulPoller()
    state = RuntimeState()

    run_runtime_cycle(
        settings=settings,
        player=player,
        poller=poller,
        state=state,
        now=0.0,
    )
    run_runtime_cycle(
        settings=settings,
        player=player,
        poller=poller,
        state=state,
        touch_actions=FakeTouchActions(["next"]),
        now=0.1,
    )

    assert poller.poll_count == 1
    assert [channel.id for channel in player.selected_channels] == [
        "01_Citadel",
        "02_Cable",
    ]


def test_runtime_cycle_applies_remote_navigation_between_delivery_polls(tmp_path):
    (tmp_path / "01_Citadel").mkdir()
    (tmp_path / "02_Cable").mkdir()
    (tmp_path / "01_Citadel" / "episode.mp4").touch()
    (tmp_path / "02_Cable" / "episode.mp4").touch()
    settings = PiSettings(
        server_base_url="https://rick-tv.example",
        api_token="test-token",
        media_root=tmp_path,
        poll_interval_seconds=60,
        remote_poll_interval_seconds=2,
    )
    player = FakePlayer()
    poller = RemoteCommandPoller(
        [
            [],
            [FakeRemoteCommand("cmd-1", "select_channel", "02_Cable")],
        ]
    )
    state = RuntimeState()

    run_runtime_cycle(settings=settings, player=player, poller=poller, state=state, now=0.0)
    run_runtime_cycle(settings=settings, player=player, poller=poller, state=state, now=2.1)

    assert poller.poll_count == 1
    assert poller.remote_poll_count == 2
    assert poller.acked_commands == ["cmd-1"]
    assert [channel.id for channel in player.selected_channels] == [
        "01_Citadel",
        "02_Cable",
    ]


def test_runtime_cycle_acks_remote_navigation_for_missing_local_channel(tmp_path):
    (tmp_path / "01_Citadel").mkdir()
    (tmp_path / "01_Citadel" / "episode.mp4").touch()
    settings = PiSettings(
        server_base_url="https://rick-tv.example",
        api_token="test-token",
        media_root=tmp_path,
        remote_poll_interval_seconds=2,
    )
    player = FakePlayer()
    poller = RemoteCommandPoller(
        [[FakeRemoteCommand("cmd-1", "select_channel", "99_Missing")]]
    )
    state = RuntimeState()

    run_runtime_cycle(settings=settings, player=player, poller=poller, state=state, now=0.0)

    assert poller.acked_commands == ["cmd-1"]
    assert [channel.id for channel in player.selected_channels] == ["01_Citadel"]


def test_runtime_cycle_does_not_ack_remote_navigation_when_player_rejects_channel(
    tmp_path,
):
    (tmp_path / "01_Citadel").mkdir()
    (tmp_path / "02_Cable").mkdir()
    (tmp_path / "01_Citadel" / "episode.mp4").touch()
    (tmp_path / "02_Cable" / "episode.mp4").touch()
    settings = PiSettings(
        server_base_url="https://rick-tv.example",
        api_token="test-token",
        media_root=tmp_path,
        remote_poll_interval_seconds=2,
    )
    player = FakePlayer(rejected_channel_ids={"02_Cable"})
    poller = RemoteCommandPoller(
        [[FakeRemoteCommand("cmd-1", "select_channel", "02_Cable")]]
    )
    state = RuntimeState()

    run_runtime_cycle(settings=settings, player=player, poller=poller, state=state, now=0.0)

    assert poller.acked_commands == []
    assert [channel.id for channel in player.selected_channels] == [
        "01_Citadel",
        "02_Cable",
    ]


def test_touch_action_queue_returns_none_without_blocking_when_empty():
    queue = TouchActionQueue()

    assert queue.next_action() is None


class FakePlayer:
    screen_state = "empty"

    def __init__(self, rejected_channel_ids=None) -> None:
        self.select_count = 0
        self.rescan_count = 0
        self.synced_channels = []
        self.selected_channels = []
        self.rejected_channel_ids = set(rejected_channel_ids or [])

    def sync_channels(self, channels, now=None):
        self.synced_channels.append([channel.id for channel in channels])

    def select_channel(self, channel):
        self.select_count += 1
        self.selected_channels.append(channel)
        if channel.id in self.rejected_channel_ids:
            return False
        return True

    def rescan_current_channel(self, now=None):
        self.rescan_count += 1


class FailingPoller:
    def __init__(self) -> None:
        self.poll_count = 0

    def poll_once(self, channels):
        self.poll_count += 1
        raise RuntimeError("server unavailable")


class SuccessfulPoller:
    def __init__(self) -> None:
        self.poll_count = 0

    def poll_once(self, channels):
        self.poll_count += 1
        return []

    def poll_remote_commands(self):
        return []

    def ack_remote_command(self, command_id):
        del command_id


class FakeRemoteCommand:
    def __init__(self, command_id: str, command_type: str, channel_id: str):
        self.id = command_id
        self.type = command_type
        self.channel_id = channel_id


class RemoteCommandPoller(SuccessfulPoller):
    def __init__(self, remote_batches):
        super().__init__()
        self._remote_batches = list(remote_batches)
        self.remote_poll_count = 0
        self.acked_commands = []

    def poll_remote_commands(self):
        self.remote_poll_count += 1
        if not self._remote_batches:
            return []
        return self._remote_batches.pop(0)

    def ack_remote_command(self, command_id):
        self.acked_commands.append(command_id)


class FakeTouchActions:
    def __init__(self, actions):
        self._actions = list(actions)

    def next_action(self):
        if not self._actions:
            return None
        return self._actions.pop(0)
