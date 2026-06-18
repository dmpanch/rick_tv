from __future__ import annotations

import importlib.util
from pathlib import Path
import zipfile


ROOT = Path(__file__).parents[1]
PATCHER_PATH = ROOT / "provisioning" / "videolooper" / "rick_tv_fifo_patch.py"
OVERRIDES = ROOT / "provisioning" / "videolooper" / "overrides"
VIDEO_LOOPER_OVERRIDE = OVERRIDES / "video_looper.py"
OMX_PLAYER_OVERRIDE = OVERRIDES / "omxplayer.py"


def load_installer():
    spec = importlib.util.spec_from_file_location("rick_tv_fifo_patch", PATCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_videolooper_override_is_valid_python():
    source = VIDEO_LOOPER_OVERRIDE.read_text()

    compile(source, str(VIDEO_LOOPER_OVERRIDE), "exec")


def test_omxplayer_override_is_valid_python():
    source = OMX_PLAYER_OVERRIDE.read_text()

    compile(source, str(OMX_PLAYER_OVERRIDE), "exec")


def test_videolooper_override_has_fifo_channel_switch_and_transition_frame():
    source = VIDEO_LOOPER_OVERRIDE.read_text()

    stop_index = source.index("self._player.stop(0)")
    placeholder_index = source.index("self._rick_tv_show_transition_placeholder()")
    assert stop_index < placeholder_index
    assert "_rick_tv_playlist_mtime(command)" in source
    assert "Rick TV playlist command unchanged; ignoring" in source
    assert "_rick_tv_interstitial_frame_path = '/home/pi/rick-tv/system/interstitial-ad.fb'" in source
    assert "self._rick_tv_skip_next_interstitial = True" in source


def test_videolooper_override_suppresses_transition_for_same_channel_playlist_refresh():
    source = VIDEO_LOOPER_OVERRIDE.read_text()

    assert "same_playlist = command == self._rick_tv_current_playlist_path" in source
    assert "Rick TV same-channel playlist refresh; transition placeholder suppressed" in source
    assert "if not same_playlist:" in source

    same_playlist_index = source.index("same_playlist = command == self._rick_tv_current_playlist_path")
    transition_index = source.index("self._rick_tv_show_transition_placeholder()")
    suppress_index = source.index("self._rick_tv_skip_next_interstitial = True")
    reload_index = source.index("self._rick_tv_playlist_reload = True")
    assert same_playlist_index < transition_index < reload_index
    assert same_playlist_index < suppress_index < reload_index


def test_videolooper_override_logs_placeholder_and_playback_diagnostics():
    source = VIDEO_LOOPER_OVERRIDE.read_text()

    expected_messages = [
        "Rick TV FIFO command received",
        "Rick TV stopping player for playlist command",
        "Rick TV showing transition placeholder",
        "Rick TV suppressing next interstitial after channel switch",
        "Rick TV same-channel playlist refresh; transition placeholder suppressed",
        "Rick TV playlist reload requested; rebuilding playlist",
        "Rick TV showing interstitial ad",
        "Rick TV skipping interstitial after channel switch",
        "Rick TV player.play starting",
    ]
    for message in expected_messages:
        assert message in source


def test_videolooper_override_draws_interstitial_once_before_next_video():
    source = VIDEO_LOOPER_OVERRIDE.read_text()

    assert source.count("def _rick_tv_show_interstitial_ad(self):") == 1
    assert source.count("if not self._firstStart:") == 1
    assert source.count("if self._rick_tv_skip_next_interstitial:") == 1
    assert source.count("self._rick_tv_show_interstitial_ad()") == 1
    assert "_rick_tv_prime_interstitial_background" not in source
    assert "_rick_tv_should_prime_interstitial_background" not in source

    interstitial_index = source.index("self._rick_tv_show_interstitial_ad()")
    played_index = source.index("movie.was_played() # type: ignore")
    play_index = source.index("self._player.play(movie, loop=player_loop, vol = self._sound_vol)")
    assert interstitial_index < played_index < play_index


def test_videolooper_override_hides_framebuffer_console_before_raw_frame_writes():
    source = VIDEO_LOOPER_OVERRIDE.read_text()

    assert "def _rick_tv_prepare_framebuffer_console(self):" in source
    assert source.count("self._rick_tv_prepare_framebuffer_console()") >= 2
    assert "/sys/class/graphics/fbcon/cursor_blink" in source
    assert "/dev/tty1" in source


def test_videolooper_override_can_disable_raw_framebuffer_placeholders_for_ab_testing():
    source = VIDEO_LOOPER_OVERRIDE.read_text()

    assert "RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS" in source
    assert "def _rick_tv_framebuffer_placeholders_enabled(self):" in source

    transition_method = source.index("def _rick_tv_show_transition_placeholder(self):")
    transition_skip = source.index(
        "Rick TV transition placeholder disabled by RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS"
    )
    transition_write = source.index("os.open('/dev/fb0', os.O_WRONLY)", transition_method)
    assert transition_method < transition_skip < transition_write

    interstitial_method = source.index("def _rick_tv_show_interstitial_ad(self):")
    interstitial_skip = source.index(
        "Rick TV interstitial ad disabled by RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS"
    )
    interstitial_write = source.index("os.open('/dev/fb0', os.O_WRONLY)", interstitial_method)
    assert interstitial_method < interstitial_skip < interstitial_write


def test_videolooper_override_reads_framebuffer_flag_from_pi_env_file_for_supervisor():
    source = VIDEO_LOOPER_OVERRIDE.read_text()

    assert "def _rick_tv_env_value(self, name):" in source
    assert "def _rick_tv_env_truthy(self, name):" in source
    assert "/etc/rick-tv-pi.env" in source
    assert "os.environ.get(name)" in source
    assert "self._rick_tv_env_truthy('RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS')" in source


def test_videolooper_override_clears_stale_framebuffer_when_raw_placeholders_disabled():
    source = VIDEO_LOOPER_OVERRIDE.read_text()

    assert "def _rick_tv_clear_stale_framebuffer(self):" in source
    assert "self._rick_tv_clear_stale_framebuffer()" in source
    assert "Rick TV cleared stale framebuffer because RICK_TV_DISABLE_FRAMEBUFFER_PLACEHOLDERS is enabled" in source

    flag_index = source.index("self._rick_tv_disable_framebuffer_placeholders =")
    clear_call_index = source.index("self._rick_tv_clear_stale_framebuffer()")
    playback_state_index = source.index("self._playbackStopped = not self._play_on_startup")
    assert flag_index < clear_call_index < playback_state_index


def test_videolooper_override_quit_does_not_post_pygame_event_when_osd_disabled():
    source = VIDEO_LOOPER_OVERRIDE.read_text()

    assert "if self._osd and pygame.get_init():" in source
    assert source.count("pygame.event.post(pygame.event.Event(pygame.QUIT))") == 1


def test_omxplayer_override_uses_nonblocking_stop():
    source = OMX_PLAYER_OVERRIDE.read_text()

    assert "self.stop(0)  # Up to 3 second delay to let the old player stop." in source
    assert "self.stop(3)  # Up to 3 second delay to let the old player stop." not in source


def test_omxplayer_override_keeps_original_centered_srt_title_overlay():
    source = OMX_PLAYER_OVERRIDE.read_text()

    assert "video_looper.srt" in source
    assert "f.write(self._subtitle_header)" in source
    assert "args.extend(['--align', 'left'])" not in source
    assert "video_looper.ass" not in source
    assert "[V4+ Styles]" not in source


def test_installer_replaces_zip_entries_and_removes_stale_bytecode(tmp_path):
    installer = load_installer()
    egg_path = tmp_path / "Adafruit_Video_Looper-1.0.21-py3.7.egg"

    with zipfile.ZipFile(egg_path, "w") as egg:
        egg.writestr("Adafruit_Video_Looper/video_looper.py", "old video")
        egg.writestr("Adafruit_Video_Looper/omxplayer.py", "old omx")
        egg.writestr("Adafruit_Video_Looper/__pycache__/video_looper.cpython-37.pyc", b"old")
        egg.writestr("Adafruit_Video_Looper/__pycache__/omxplayer.cpython-37.pyc", b"old")
        egg.writestr("Adafruit_Video_Looper/model.py", "kept")

    installer.install_overrides(
        egg_path,
        {
            "Adafruit_Video_Looper/video_looper.py": VIDEO_LOOPER_OVERRIDE,
            "Adafruit_Video_Looper/omxplayer.py": OMX_PLAYER_OVERRIDE,
        },
    )

    with zipfile.ZipFile(egg_path) as egg:
        assert egg.read("Adafruit_Video_Looper/video_looper.py") == VIDEO_LOOPER_OVERRIDE.read_bytes()
        assert egg.read("Adafruit_Video_Looper/omxplayer.py") == OMX_PLAYER_OVERRIDE.read_bytes()
        assert egg.read("Adafruit_Video_Looper/model.py") == b"kept"
        assert "Adafruit_Video_Looper/__pycache__/video_looper.cpython-37.pyc" not in egg.namelist()
        assert "Adafruit_Video_Looper/__pycache__/omxplayer.cpython-37.pyc" not in egg.namelist()
