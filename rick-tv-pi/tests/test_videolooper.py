from pathlib import Path

from rick_tv_pi.channels import Channel
from rick_tv_pi.videolooper import VideolooperController


class FakeCommandWriter:
    def __init__(self) -> None:
        self.commands = []

    def __call__(self, command):
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
