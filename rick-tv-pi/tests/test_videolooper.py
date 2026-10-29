from rick_tv_pi.channels import Channel
from rick_tv_pi.videolooper import VideolooperController
from pathlib import Path
import os
import pytest


class FakeCommandWriter:
    def __init__(self) -> None:
        self.commands = []

    def __call__(self, command):
        self.commands.append(command)


@pytest.mark.parametrize('recovers', [True, False])
def test_video_navigation_waits_for_failed_channel_selection_to_recover(tmp_path, recovers):
    channels = []
    for name in ['01_A', '02_B']:
        path = tmp_path / name
        path.mkdir()
        (path / 'video.mp4').touch()
        channels.append(Channel(name, len(channels) + 1, None, path))
    delivered = []
    attempts = []

    def writer(command):
        if command.endswith('02_B.m3u'):
            attempts.append(command)
            if not recovers or len(attempts) == 1:
                raise OSError('FIFO unavailable')
        delivered.append(command)

    controller = VideolooperController(tmp_path / 'playlists', command_writer=writer)
    assert controller.select_channel(channels[0]) is True
    assert controller.select_channel(channels[1]) is False
    assert controller.next_video() is recovers
    assert [Path(command).name for command in delivered] == (
        ['01_A.m3u', '02_B.m3u', 'next_video'] if recovers else ['01_A.m3u']
    )


def test_unchanged_channel_does_not_repeat_directory_enumeration(tmp_path, monkeypatch):
    channel_path = tmp_path / 'media' / '01_Rock'
    channel_path.mkdir(parents=True)
    (channel_path / 'a.mp4').touch()
    channel = Channel('01_Rock', 1, None, channel_path)
    controller = VideolooperController(tmp_path / 'playlists', command_writer=FakeCommandWriter())
    controller.sync_channels([channel])
    controller.select_channel(channel)
    enumerations = []
    real_iterdir = Path.iterdir

    def counted_iterdir(path):
        if path == channel_path:
            enumerations.append(path)
        return real_iterdir(path)

    monkeypatch.setattr(Path, 'iterdir', counted_iterdir)
    for _ in range(5):
        controller.sync_channels([channel])
        controller.rescan_current_channel()
    assert enumerations == []


def test_cached_files_refresh_after_addition_and_removal(tmp_path):
    channel_path = tmp_path / '01_Rock'
    channel_path.mkdir()
    first = channel_path / 'a.mp4'
    first.touch()
    channel = Channel('01_Rock', 1, None, channel_path)
    controller = VideolooperController(tmp_path / 'playlists', command_writer=FakeCommandWriter())
    controller.select_channel(channel)
    second = channel_path / 'b.mp4'
    second.touch()
    controller.rescan_current_channel()
    playlist = tmp_path / 'playlists/channels/01_Rock.m3u'
    assert str(second) in playlist.read_text()
    first.unlink()
    second.unlink()
    controller.rescan_current_channel()
    assert controller.current_file is None
    assert playlist.read_text() == '#EXTM3U\n'


def test_cache_invalidates_recreated_directory_even_with_same_mtime(tmp_path):
    channel_path = tmp_path / '01_Rock'
    channel_path.mkdir()
    (channel_path / 'old.mp4').touch()
    channel = Channel('01_Rock', 1, None, channel_path)
    controller = VideolooperController(tmp_path / 'playlists', command_writer=FakeCommandWriter())
    controller.select_channel(channel)
    before = channel_path.stat()
    channel_path.rename(tmp_path / 'old')
    channel_path.mkdir()
    (channel_path / 'new.mp4').touch()
    os.utime(channel_path, ns=(before.st_atime_ns, before.st_mtime_ns))
    controller.rescan_current_channel()
    assert controller.current_file.path.name == 'new.mp4'


class FailingCommandWriter:
    def __call__(self, command):
        del command
        raise OSError("fifo unavailable")


class FailOnceCommandWriter:
    def __init__(self) -> None:
        self.commands = []
        self.calls = 0

    def __call__(self, command):
        self.calls += 1
        if self.calls == 1:
            raise OSError("fifo unavailable")
        self.commands.append(command)


def test_sync_channels_writes_master_playlist_with_channel_playlists(tmp_path):
    channel_path = tmp_path / "media" / "01_Citadel"
    channel_path.mkdir(parents=True)
    episode = channel_path / "episode.mp4"
    episode.touch()
    channel = Channel("01_Citadel", 1, "Citadel TV", channel_path)
    controller = VideolooperController(
        playlist_root=tmp_path / "playlists",
        command_writer=FakeCommandWriter(),
    )

    controller.sync_channels([channel])

    channel_playlist = tmp_path / "playlists" / "channels" / "01_Citadel.m3u"
    assert (tmp_path / "playlists" / "channels.m3u").read_text() == (
        "#EXTM3U\n"
        "#EXTINF:0,Channel 1 - Citadel TV\n"
        f"{channel_playlist}\n"
    )
    assert channel_playlist.read_text() == (
        "#EXTM3U\n"
        "#EXTINF:0,Channel 1 - Citadel TV\n"
        f"{episode}\n"
    )


def test_sync_channels_skips_empty_channel_playlists(tmp_path):
    media_root = tmp_path / "media"
    empty_channel_path = media_root / "02_Empty"
    empty_channel_path.mkdir(parents=True)
    nonempty_channel_path = media_root / "01_Citadel"
    nonempty_channel_path.mkdir(parents=True)
    episode = nonempty_channel_path / "episode.mp4"
    episode.touch()
    channels = [
        Channel("01_Citadel", 1, "Citadel TV", nonempty_channel_path),
        Channel("02_Empty", 2, "Empty", empty_channel_path),
    ]
    controller = VideolooperController(
        playlist_root=tmp_path / "playlists",
        command_writer=FakeCommandWriter(),
    )

    controller.sync_channels(channels)

    master = tmp_path / "playlists" / "channels.m3u"
    assert master.read_text() == (
        "#EXTM3U\n"
        "#EXTINF:0,Channel 1 - Citadel TV\n"
        f"{tmp_path / 'playlists' / 'channels' / '01_Citadel.m3u'}\n"
    )


def test_select_channel_sends_channel_playlist_without_restart(tmp_path):
    channel_path = tmp_path / "media" / "01_Citadel"
    channel_path.mkdir(parents=True)
    episode = channel_path / "episode.mp4"
    episode.touch()
    channel = Channel("01_Citadel", 1, "Citadel TV", channel_path)
    writer = FakeCommandWriter()
    controller = VideolooperController(
        playlist_root=tmp_path / "playlists",
        command_writer=writer,
    )

    controller.select_channel(channel)

    channel_playlist = tmp_path / "playlists" / "channels" / "01_Citadel.m3u"
    assert writer.commands == [str(channel_playlist)]
    assert controller.screen_state == "playing"
    assert controller.current_file is not None
    assert controller.current_file.path == episode


def test_select_channel_reports_failure_when_command_pipe_is_unavailable(tmp_path):
    channel_path = tmp_path / "media" / "01_Citadel"
    channel_path.mkdir(parents=True)
    (channel_path / "episode.mp4").touch()
    channel = Channel("01_Citadel", 1, "Citadel TV", channel_path)
    controller = VideolooperController(
        playlist_root=tmp_path / "playlists",
        command_writer=FailingCommandWriter(),
    )

    assert controller.select_channel(channel) is False


def test_select_channel_retries_same_channel_after_command_pipe_failure(tmp_path):
    channel_path = tmp_path / "media" / "01_Citadel"
    channel_path.mkdir(parents=True)
    (channel_path / "episode.mp4").touch()
    channel = Channel("01_Citadel", 1, "Citadel TV", channel_path)
    writer = FailOnceCommandWriter()
    controller = VideolooperController(
        playlist_root=tmp_path / "playlists",
        command_writer=writer,
    )

    assert controller.select_channel(channel) is False
    assert controller.select_channel(channel) is True

    channel_playlist = tmp_path / "playlists" / "channels" / "01_Citadel.m3u"
    assert writer.commands == [str(channel_playlist)]


def test_select_channel_writes_empty_playlist_for_empty_channel(tmp_path):
    channel_path = tmp_path / "media" / "03_Empty"
    channel_path.mkdir(parents=True)
    channel = Channel("03_Empty", 3, None, channel_path)
    writer = FakeCommandWriter()
    controller = VideolooperController(
        playlist_root=tmp_path / "playlists",
        command_writer=writer,
    )

    controller.select_channel(channel)

    channel_playlist = tmp_path / "playlists" / "channels" / "03_Empty.m3u"
    assert channel_playlist.read_text() == "#EXTM3U\n"
    assert writer.commands == []
    assert controller.screen_state == "empty"
    assert controller.current_file is None


def test_rescan_does_not_send_command_when_playlist_is_unchanged(tmp_path):
    channel_path = tmp_path / "media" / "01_Citadel"
    channel_path.mkdir(parents=True)
    (channel_path / "episode.mp4").touch()
    channel = Channel("01_Citadel", 1, None, channel_path)
    writer = FakeCommandWriter()
    controller = VideolooperController(
        playlist_root=tmp_path / "playlists",
        command_writer=writer,
    )

    controller.select_channel(channel)
    controller.rescan_current_channel()

    assert writer.commands == [str(tmp_path / "playlists" / "channels" / "01_Citadel.m3u")]


def test_rescan_sends_command_when_channel_files_change(tmp_path):
    channel_path = tmp_path / "media" / "01_Citadel"
    channel_path.mkdir(parents=True)
    channel = Channel("01_Citadel", 1, None, channel_path)
    writer = FakeCommandWriter()
    controller = VideolooperController(
        playlist_root=tmp_path / "playlists",
        command_writer=writer,
    )
    controller.select_channel(channel)

    (channel_path / "episode.mp4").touch()
    controller.rescan_current_channel()

    assert writer.commands == [
        str(tmp_path / "playlists" / "channels" / "01_Citadel.m3u"),
    ]
    assert str(channel_path / "episode.mp4") in (
        tmp_path / "playlists" / "channels" / "01_Citadel.m3u"
    ).read_text()


def test_sync_channels_keeps_channel_order_but_shuffles_files_on_interval(tmp_path):
    channel_path = tmp_path / "media" / "01_Citadel"
    channel_path.mkdir(parents=True)
    first = channel_path / "a.mp4"
    second = channel_path / "b.mp4"
    first.touch()
    second.touch()
    channel = Channel("01_Citadel", 1, None, channel_path)
    shuffle_orders = [
        [second, first],
        [first, second],
    ]
    controller = VideolooperController(
        playlist_root=tmp_path / "playlists",
        command_writer=FakeCommandWriter(),
        shuffle_interval_seconds=3600,
        shuffler=lambda files: shuffle_orders.pop(0),
    )

    controller.sync_channels([channel], now=0)
    controller.sync_channels([channel], now=3599)
    playlist = tmp_path / "playlists" / "channels" / "01_Citadel.m3u"

    assert playlist.read_text() == (
        "#EXTM3U\n"
        "#EXTINF:0,Channel 1\n"
        f"{second}\n"
        "#EXTINF:0,Channel 1\n"
        f"{first}\n"
    )

    controller.sync_channels([channel], now=3600)

    assert playlist.read_text() == (
        "#EXTM3U\n"
        "#EXTINF:0,Channel 1\n"
        f"{first}\n"
        "#EXTINF:0,Channel 1\n"
        f"{second}\n"
    )


def test_select_and_rescan_preserve_shuffled_channel_playlist(tmp_path):
    channel_path = tmp_path / "media" / "01_Citadel"
    channel_path.mkdir(parents=True)
    first = channel_path / "a.mp4"
    second = channel_path / "b.mp4"
    first.touch()
    second.touch()
    channel = Channel("01_Citadel", 1, None, channel_path)
    writer = FakeCommandWriter()
    controller = VideolooperController(
        playlist_root=tmp_path / "playlists",
        command_writer=writer,
        shuffle_interval_seconds=3600,
        shuffler=lambda files: [second, first],
    )

    controller.sync_channels([channel], now=0)
    controller.select_channel(channel)
    controller.rescan_current_channel()

    channel_playlist = tmp_path / "playlists" / "channels" / "01_Citadel.m3u"
    assert channel_playlist.read_text() == (
        "#EXTM3U\n"
        "#EXTINF:0,Channel 1\n"
        f"{second}\n"
        "#EXTINF:0,Channel 1\n"
        f"{first}\n"
    )
    assert writer.commands == [str(channel_playlist)]
