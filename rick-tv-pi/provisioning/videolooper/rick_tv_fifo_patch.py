#!/usr/bin/env python3
"""Patch installed pi_video_looper with Rick TV FIFO playlist control."""

from pathlib import Path
import tempfile
import zipfile
import os


VIDEO_LOOPER = Path(
    "/usr/local/lib/python3.7/dist-packages/"
    "Adafruit_Video_Looper-1.0.21-py3.7.egg/"
    "Adafruit_Video_Looper/video_looper.py"
)
VIDEO_LOOPER_EGG = Path(
    "/usr/local/lib/python3.7/dist-packages/"
    "Adafruit_Video_Looper-1.0.21-py3.7.egg"
)
VIDEO_LOOPER_ZIP_NAME = "Adafruit_Video_Looper/video_looper.py"

IMPORT_MARKER = "import urllib.parse\n"
INIT_MARKER = "        self._playbackStopped = not self._play_on_startup\n"
RUN_MARKER = "            # Give the CPU some time to do other tasks."
METHOD_MARKER = "    def _handle_keyboard_shortcuts(self):\n"
NESTED_PLAYLIST_BUG = "                        self._playlist_path = movie.filename # type: ignore\n"
ABSOLUTE_PLAYLIST_BUG = """\
            if os.path.isabs(self._playlist_path):
                if not os.path.isfile(self._playlist_path):
"""
ABSOLUTE_PLAYLIST_FIX = """\
            if os.path.isabs(self._playlist_path):
                playlist_path = self._playlist_path
                if not os.path.isfile(self._playlist_path):
"""
PYGAME_DISPLAY_BLOCK = """\
        # Initialize pygame and display a blank screen.
        pygame.display.init()
        pygame.font.init()
        pygame.mouse.set_visible(False)
        self._screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN | pygame.NOFRAME)
        self._size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
        self._bgimage = self._load_bgimage() #a tupple with pyimage, xpos, ypos
        self._blank_screen()
"""
PYGAME_DISPLAY_PATCH = """\
        # Initialize pygame display only when videolooper's own OSD is enabled.
        if self._osd:
            pygame.display.init()
            pygame.font.init()
            pygame.mouse.set_visible(False)
            self._screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN | pygame.NOFRAME)
            self._size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
            self._bgimage = self._load_bgimage() #a tupple with pyimage, xpos, ypos
            self._blank_screen()
        else:
            self._screen = None
            self._size = (0, 0)
            self._bgimage = (None, 0, 0)
"""
BLANK_SCREEN_BLOCK = """\
        self._screen.fill(self._bgcolor)
        if self._bgimage[0] is not None:
            self._screen.blit(self._bgimage[0], (self._bgimage[1], self._bgimage[2]))
        pygame.display.flip()
"""
BLANK_SCREEN_PATCH = """\
        if not self._osd:
            return
        self._screen.fill(self._bgcolor)
        if self._bgimage[0] is not None:
            self._screen.blit(self._bgimage[0], (self._bgimage[1], self._bgimage[2]))
        pygame.display.flip()
"""
FONT_BLOCK = """\
        self._small_font = pygame.font.Font(None, 50)
        self._medium_font   = pygame.font.Font(None, 96)
        self._big_font   = pygame.font.Font(None, 250)
"""
FONT_PATCH = """\
        if self._osd:
            self._small_font = pygame.font.Font(None, 50)
            self._medium_font   = pygame.font.Font(None, 96)
            self._big_font   = pygame.font.Font(None, 250)
        else:
            self._small_font = None
            self._medium_font = None
            self._big_font = None
"""

IMPORT_PATCH = "import select\n"
INIT_PATCH = """\
        self._rick_tv_fifo_path = self._config.get(
            'rick_tv', 'command_fifo', fallback='/tmp/rick-tv-videolooper.fifo'
        )
        self._rick_tv_fifo = None
        self._rick_tv_open_fifo()
"""
RUN_PATCH = """\
            self._rick_tv_handle_fifo_commands()

"""
METHOD_PATCH = """\
    def _rick_tv_open_fifo(self):
        if not self._rick_tv_fifo_path:
            return
        try:
            if not os.path.exists(self._rick_tv_fifo_path):
                os.mkfifo(self._rick_tv_fifo_path)
            self._rick_tv_fifo = os.open(self._rick_tv_fifo_path, os.O_RDONLY | os.O_NONBLOCK)
            self._print(f"Rick TV command FIFO ready: {self._rick_tv_fifo_path}")
        except OSError as exc:
            self._rick_tv_fifo = None
            self._print(f"Rick TV command FIFO unavailable: {exc}")

    def _rick_tv_handle_fifo_commands(self):
        if self._rick_tv_fifo is None:
            return
        readable, _, _ = select.select([self._rick_tv_fifo], [], [], 0)
        if not readable:
            return
        try:
            payload = os.read(self._rick_tv_fifo, 4096).decode('utf-8')
        except OSError as exc:
            self._print(f"Rick TV command FIFO read failed: {exc}")
            return
        if payload == '':
            os.close(self._rick_tv_fifo)
            self._rick_tv_fifo = None
            self._rick_tv_open_fifo()
            return
        for command in payload.splitlines():
            command = command.strip()
            if not command:
                continue
            if '.m3u' in command:
                self._print(f"Rick TV loading playlist: {command}")
                self._playlist_path = command
                self._playlist = self._build_playlist()
                self._player.stop(0)
                self._playbackStopped = False

"""


def insert_once(text: str, marker: str, patch: str, *, after: bool) -> str:
    if patch.strip() in text:
        return text
    index = text.index(marker)
    if after:
        index += len(marker)
    return text[:index] + patch + text[index:]


def main() -> None:
    if VIDEO_LOOPER.exists():
        text = VIDEO_LOOPER.read_text()
        VIDEO_LOOPER.write_text(patch_text(text))
        return

    with zipfile.ZipFile(str(VIDEO_LOOPER_EGG), "r") as source:
        text = source.read(VIDEO_LOOPER_ZIP_NAME).decode("utf-8")
        patched_text = patch_text(text)
        with tempfile.NamedTemporaryFile(delete=False) as target_file:
            target_path = Path(target_file.name)
        with zipfile.ZipFile(str(target_path), "w") as target:
            for item in source.infolist():
                if item.filename == "Adafruit_Video_Looper/__pycache__/video_looper.cpython-37.pyc":
                    continue
                data = source.read(item.filename)
                if item.filename == VIDEO_LOOPER_ZIP_NAME:
                    data = patched_text.encode("utf-8")
                target.writestr(item, data)

    target_path.replace(VIDEO_LOOPER_EGG)
    os.chmod(str(VIDEO_LOOPER_EGG), 0o644)


def patch_text(text: str) -> str:
    text = insert_once(text, IMPORT_MARKER, IMPORT_PATCH, after=True)
    text = insert_once(text, INIT_MARKER, INIT_PATCH, after=False)
    text = insert_once(text, RUN_MARKER, RUN_PATCH, after=False)
    text = insert_once(text, METHOD_MARKER, METHOD_PATCH, after=False)
    text = text.replace(
        NESTED_PLAYLIST_BUG,
        "                        self._playlist_path = movie.target # type: ignore\n",
    )
    text = text.replace(ABSOLUTE_PLAYLIST_BUG, ABSOLUTE_PLAYLIST_FIX)
    text = text.replace(PYGAME_DISPLAY_BLOCK, PYGAME_DISPLAY_PATCH)
    text = text.replace(BLANK_SCREEN_BLOCK, BLANK_SCREEN_PATCH)
    text = text.replace(FONT_BLOCK, FONT_PATCH)
    return text


if __name__ == "__main__":
    main()
