from __future__ import annotations

import importlib.util
from pathlib import Path


PATCHER_PATH = (
    Path(__file__).parents[1]
    / "provisioning"
    / "videolooper"
    / "rick_tv_fifo_patch.py"
)


def load_patcher():
    spec = importlib.util.spec_from_file_location("rick_tv_fifo_patch", PATCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fifo_patch_ignores_unchanged_duplicate_playlist_commands():
    patcher = load_patcher()

    patched = patcher.patch_text(
        "import urllib.parse\n"
        "class VideoLooper:\n"
        "    def __init__(self):\n"
        "        self._playbackStopped = not self._play_on_startup\n"
        "\n"
        "    def _handle_keyboard_shortcuts(self):\n"
        "        self._print(\"keyboard control thread started\")\n"
        "        while self._running:\n"
        "            event = pygame.event.wait()\n"
        "\n"
        "    def run(self):\n"
        "        while self._running:\n"
        "            if not self._player.is_playing() and not self._playbackStopped:\n"
        "                if movie is not None: #just to avoid errors\n"
        "                    movie.was_played() # type: ignore\n"
        "                    self._player.play(movie, loop=player_loop, vol = self._sound_vol)\n"
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            time.sleep(0.002)\n"
    )

    assert "_rick_tv_playlist_mtime(command)" in patched
    assert "Rick TV playlist command unchanged; ignoring" in patched


def test_fifo_patch_draws_transition_placeholder_after_stopping_player():
    patcher = load_patcher()

    patched = patcher.patch_text(
        "import urllib.parse\n"
        "class VideoLooper:\n"
        "    def __init__(self):\n"
        "        self._playbackStopped = not self._play_on_startup\n"
        "\n"
        "    def _handle_keyboard_shortcuts(self):\n"
        "        self._print(\"keyboard control thread started\")\n"
        "        while self._running:\n"
        "            event = pygame.event.wait()\n"
        "\n"
        "    def run(self):\n"
        "        while self._running:\n"
        "            if not self._player.is_playing() and not self._playbackStopped:\n"
        "                if movie is not None: #just to avoid errors\n"
        "                    movie.was_played() # type: ignore\n"
        "                    self._player.play(movie, loop=player_loop, vol = self._sound_vol)\n"
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            time.sleep(0.002)\n"
    )

    stop_index = patched.index("self._player.stop(0)")
    placeholder_index = patched.index("self._rick_tv_show_transition_placeholder()")
    assert stop_index < placeholder_index
    assert "def _rick_tv_show_transition_placeholder(self):" in patched
    assert "def _rick_tv_build_transition_frame(self):" in patched


def test_fifo_patch_draws_interstitial_ad_between_playlist_videos_only():
    patcher = load_patcher()

    patched = patcher.patch_text(
        "import urllib.parse\n"
        "class VideoLooper:\n"
        "    def __init__(self):\n"
        "        self._playbackStopped = not self._play_on_startup\n"
        "\n"
        "    def _handle_keyboard_shortcuts(self):\n"
        "        self._print(\"keyboard control thread started\")\n"
        "        while self._running:\n"
        "            event = pygame.event.wait()\n"
        "\n"
        "    def run(self):\n"
        "        while self._running:\n"
        "            if not self._player.is_playing() and not self._playbackStopped:\n"
        "                if movie is not None: #just to avoid errors\n"
        "                    movie.was_played() # type: ignore\n"
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            time.sleep(0.002)\n"
    )

    assert "_rick_tv_interstitial_frame_path = '/home/pi/rick-tv/system/interstitial-ad.fb'" in patched
    assert "self._rick_tv_skip_next_interstitial = True" in patched
    assert "def _rick_tv_show_interstitial_ad(self):" in patched
    interstitial_index = patched.index("self._rick_tv_show_interstitial_ad()")
    played_index = patched.index("movie.was_played()")
    assert interstitial_index < played_index


def test_fifo_patch_hides_framebuffer_console_before_drawing_raw_frames():
    patcher = load_patcher()

    patched = patcher.patch_text(
        "import urllib.parse\n"
        "class VideoLooper:\n"
        "    def __init__(self):\n"
        "        self._playbackStopped = not self._play_on_startup\n"
        "\n"
        "    def _handle_keyboard_shortcuts(self):\n"
        "        self._print(\"keyboard control thread started\")\n"
        "        while self._running:\n"
        "            event = pygame.event.wait()\n"
        "\n"
        "    def run(self):\n"
        "        while self._running:\n"
        "            if not self._player.is_playing() and not self._playbackStopped:\n"
        "                if movie is not None: #just to avoid errors\n"
        "                    movie.was_played() # type: ignore\n"
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            time.sleep(0.002)\n"
    )

    assert "def _rick_tv_prepare_framebuffer_console(self):" in patched
    assert patched.count("self._rick_tv_prepare_framebuffer_console()") >= 2


def test_fifo_patch_primes_interstitial_background_after_starting_video():
    patcher = load_patcher()

    patched = patcher.patch_text(
        "import urllib.parse\n"
        "class VideoLooper:\n"
        "    def __init__(self):\n"
        "        self._playbackStopped = not self._play_on_startup\n"
        "\n"
        "    def _handle_keyboard_shortcuts(self):\n"
        "        self._print(\"keyboard control thread started\")\n"
        "        while self._running:\n"
        "            event = pygame.event.wait()\n"
        "\n"
        "    def run(self):\n"
        "        while self._running:\n"
        "            if not self._player.is_playing() and not self._playbackStopped:\n"
        "                if movie is not None: #just to avoid errors\n"
        "                    self._player.play(movie, loop=player_loop, vol = self._sound_vol)\n"
        "                    movie.was_played() # type: ignore\n"
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            time.sleep(0.002)\n"
    )

    play_index = patched.index("self._player.play(movie, loop=player_loop, vol = self._sound_vol)")
    prime_index = patched.index("self._rick_tv_prime_interstitial_background()")
    assert play_index < prime_index
    assert "def _rick_tv_prime_interstitial_background(self):" in patched
    assert "if not self._rick_tv_should_prime_interstitial_background:" in patched
    assert "self._rick_tv_should_prime_interstitial_background = (" in patched


def test_fifo_patch_is_idempotent_for_rick_tv_runtime_hooks():
    patcher = load_patcher()
    source = (
        "import urllib.parse\n"
        "class VideoLooper:\n"
        "    def __init__(self):\n"
        "        self._playbackStopped = not self._play_on_startup\n"
        "\n"
        "    def _handle_keyboard_shortcuts(self):\n"
        "        self._print(\"keyboard control thread started\")\n"
        "        while self._running:\n"
        "            event = pygame.event.wait()\n"
        "\n"
        "    def run(self):\n"
        "        while self._running:\n"
        "            if not self._player.is_playing() and not self._playbackStopped:\n"
        "                if movie is not None: #just to avoid errors\n"
        "                    movie.was_played() # type: ignore\n"
        "                    self._player.play(movie, loop=player_loop, vol = self._sound_vol)\n"
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            time.sleep(0.002)\n"
    )

    patched = patcher.patch_text(patcher.patch_text(source))

    assert patched.count("_rick_tv_fifo_path = self._config.get") == 1
    assert patched.count("_rick_tv_interstitial_frame_path =") == 1
    assert (
        patched.splitlines().count("        self._rick_tv_should_prime_interstitial_background = False")
        == 1
    )
    assert patched.count("self._rick_tv_should_prime_interstitial_background = (") == 1
    assert patched.count("if self._rick_tv_should_prime_interstitial_background:") == 1
    assert patched.count("def _rick_tv_frame_for_display(self, frame_path):") == 1
    assert patched.count("def _rick_tv_show_transition_placeholder(self):") == 1
    assert patched.count("def _rick_tv_show_interstitial_ad(self):") == 1
    assert patched.count("def _rick_tv_prime_interstitial_background(self):") == 1
    assert patched.count("self._rick_tv_prime_interstitial_background()") == 1
    assert patched.count("if movie is None:\n                        continue") <= 1


def test_fifo_patch_does_not_prime_interstitial_after_skipped_channel_transition():
    patcher = load_patcher()

    patched = patcher.patch_text(
        "import urllib.parse\n"
        "class VideoLooper:\n"
        "    def __init__(self):\n"
        "        self._playbackStopped = not self._play_on_startup\n"
        "\n"
        "    def _handle_keyboard_shortcuts(self):\n"
        "        self._print(\"keyboard control thread started\")\n"
        "        while self._running:\n"
        "            event = pygame.event.wait()\n"
        "\n"
        "    def run(self):\n"
        "        while self._running:\n"
        "            if not self._player.is_playing() and not self._playbackStopped:\n"
        "                if movie is not None: #just to avoid errors\n"
        "                    movie.was_played() # type: ignore\n"
        "                    self._player.play(movie, loop=player_loop, vol = self._sound_vol)\n"
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            time.sleep(0.002)\n"
    )

    flag_index = patched.index("self._rick_tv_should_prime_interstitial_background = (")
    skip_index = patched.index("self._rick_tv_skip_next_interstitial = False", flag_index)
    play_index = patched.index("self._player.play(movie, loop=player_loop, vol = self._sound_vol)")
    assert flag_index < skip_index < play_index
