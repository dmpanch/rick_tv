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
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            time.sleep(0.002)\n"
    )

    stop_index = patched.index("self._player.stop(0)")
    placeholder_index = patched.index("self._rick_tv_show_transition_placeholder()")
    assert stop_index < placeholder_index
    assert "def _rick_tv_show_transition_placeholder(self):" in patched
    assert "def _rick_tv_build_transition_frame(self):" in patched
