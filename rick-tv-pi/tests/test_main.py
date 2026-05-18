from pathlib import Path

from rick_tv_pi.config import PiSettings
from rick_tv_pi.main import RuntimeState, load_settings_from_env, run_runtime_cycle


def test_load_settings_from_env_reads_required_and_optional_values(monkeypatch):
    monkeypatch.setenv("RICK_TV_SERVER_URL", "https://rick-tv.example")
    monkeypatch.setenv("RICK_TV_API_TOKEN", "test-token")
    monkeypatch.setenv("RICK_TV_MEDIA_ROOT", "/var/lib/rick-tv/media")
    monkeypatch.setenv("RICK_TV_METADATA_PATH", "/etc/rick-tv/channels.yml")

    settings = load_settings_from_env()

    assert settings.server_base_url == "https://rick-tv.example"
    assert settings.api_token == "test-token"
    assert settings.media_root == Path("/var/lib/rick-tv/media")
    assert settings.metadata_path == Path("/etc/rick-tv/channels.yml")
    assert settings.poll_interval_seconds == 60


def test_runtime_cycle_logs_poll_failure_and_rescans_empty_channel(tmp_path, caplog):
    channel_path = tmp_path / "01_Citadel"
    channel_path.mkdir()
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


def test_runtime_cycle_does_not_reselect_initial_empty_channel(tmp_path):
    channel_path = tmp_path / "01_Citadel"
    channel_path.mkdir()
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


class FakePlayer:
    screen_state = "empty"

    def __init__(self) -> None:
        self.select_count = 0
        self.rescan_count = 0

    def select_channel(self, channel):
        self.select_count += 1

    def rescan_current_channel(self):
        self.rescan_count += 1


class FailingPoller:
    def __init__(self) -> None:
        self.poll_count = 0

    def poll_once(self, channels):
        self.poll_count += 1
        raise RuntimeError("server unavailable")


class SuccessfulPoller:
    def poll_once(self, channels):
        return []
