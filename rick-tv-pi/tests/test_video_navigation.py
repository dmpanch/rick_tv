import ast
import importlib.util
import os
from pathlib import Path
import select
from types import SimpleNamespace

import pytest

from rick_tv_pi.config import PiSettings
from rick_tv_pi.main import RuntimeState, TouchActionQueue, run_runtime_cycle
from rick_tv_pi.videolooper import VideolooperController


ROOT = Path(__file__).parents[1]


def test_runtime_routes_video_swipes_without_switching_the_only_channel(tmp_path):
    channel = tmp_path / 'media' / '01_Rock'
    channel.mkdir(parents=True)
    (channel / 'one.mp4').touch()
    commands = []
    player = VideolooperController(tmp_path / 'playlists', command_writer=commands.append)
    settings = PiSettings(server_base_url='http://test', api_token='test', media_root=channel.parent)
    state = RuntimeState(next_poll_at=100, next_remote_poll_at=100)
    run_runtime_cycle(settings, player, None, state, now=0)
    commands.clear()
    actions = TouchActionQueue()
    for action in ['next_video', 'previous_video', 'next', 'previous']:
        actions.put(action)
    run_runtime_cycle(settings, player, None, state, touch_actions=actions, now=0.1)
    assert commands == ['next_video', 'previous_video']
    assert state.navigator.current_channel.id == '01_Rock'


def load_looper_class(clock):
    source = ROOT / 'provisioning/videolooper/overrides/video_looper.py'
    tree = ast.parse(source.read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    model = load_playlist_model()
    namespace = {'os': os, 'select': select, 'time': clock, 'pygame': SimpleNamespace(quit=lambda: None),
                 'Playlist': model.Playlist, 'Movie': model.Movie}
    exec(compile(tree, str(source), 'exec'), namespace)
    return namespace['VideoLooper']


def load_playlist_model():
    path = Path(__file__).parent / 'fixtures/videolooper_model.py'
    spec = importlib.util.spec_from_file_location('videolooper_model_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('batches,expected', [
    ([['next_video'], ['previous_video']], ['a.mp4', 'b.mp4', 'a.mp4']),
    ([['previous_video']], ['a.mp4', 'c.mp4']),
    ([['next_video'], ['next_video'], ['next_video']], ['a.mp4', 'b.mp4', 'c.mp4', 'a.mp4']),
    ([['next_video', 'next_video']], ['a.mp4', 'c.mp4']),
    ([['previous_video'], ['previous_video']], ['a.mp4', 'c.mp4', 'b.mp4']),
    ([['channel.m3u', 'next_video']], ['a.mp4', 'y.mp4']),
    ([['next_video', 'channel.m3u']], ['a.mp4', 'x.mp4']),
    ([['unknown_command']] * 21, ['a.mp4']),
])
def test_fifo_moves_actual_playlist_position_without_extra_skip(batches, expected):
    model = load_playlist_model()
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    played, interstitials, reader_checks = [], [], []
    tick = [0]
    batches = list(batches)

    def sleep(_seconds):
        tick[0] += _seconds
        if batches:
            os.write(write_fd, ('\n'.join(batches.pop(0)) + '\n').encode())
        else:
            looper._running = False

    clock = SimpleNamespace(sleep=sleep, monotonic=lambda: tick[0])
    looper = object.__new__(load_looper_class(clock))
    playing = [False]

    def play(movie, **kwargs):
        played.append(movie.filename)
        playing[0] = True

    looper._player = SimpleNamespace(is_playing=lambda: playing[0], can_loop_count=lambda: False,
        play=play, stop=lambda _timeout: playing.__setitem__(0, False))
    looper._reader = SimpleNamespace(is_changed=lambda: reader_checks.append(tick[0]) or False)
    looper._build_playlist = lambda: model.Playlist(
        [model.Movie(n) for n in (['x.mp4', 'y.mp4'] if looper._playlist_path == 'channel.m3u' else ['a.mp4', 'b.mp4', 'c.mp4'])],
        False, False, False)
    looper._playlist_path = 'initial.m3u'
    looper._rick_tv_fifo = read_fd
    looper._rick_tv_current_playlist_path = 'initial.m3u'
    looper._rick_tv_current_playlist_mtime = 1
    looper._rick_tv_playlist_mtime = lambda _: 2
    looper._rick_tv_pending_video_steps = []
    looper._rick_tv_playlist_reload = False
    looper._rick_tv_skip_next_interstitial = False
    looper._rick_tv_next_reader_check = 0
    looper._print = lambda _: None
    looper._prepare_to_run_playlist = lambda _: None
    looper._set_hardware_volume = lambda: None
    looper._rick_tv_show_transition_placeholder = lambda: None
    looper._rick_tv_show_interstitial_ad = lambda: interstitials.append(True)
    looper._running = True
    looper._playbackStopped = False
    looper._firstStart = True
    looper._is_random = False
    looper._is_random_unique = False
    looper._wait_time = 0
    looper._one_shot_playback = False
    looper._sound_vol = 0
    try:
        looper.run()
    finally:
        os.close(read_fd)
        os.close(write_fd)
    assert played == expected
    assert interstitials == []
    assert len(reader_checks) <= 2
