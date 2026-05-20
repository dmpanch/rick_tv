#!/usr/bin/env python3
from __future__ import annotations

"""Patch installed pi_video_looper with Rick TV FIFO playlist control."""

from pathlib import Path
import tempfile
import zipfile
import os
import re
from typing import List, Tuple


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
OMX_PLAYER = Path(
    "/usr/local/lib/python3.7/dist-packages/"
    "Adafruit_Video_Looper-1.0.21-py3.7.egg/"
    "Adafruit_Video_Looper/omxplayer.py"
)
OMX_PLAYER_EGG = VIDEO_LOOPER_EGG
OMX_PLAYER_ZIP_NAME = "Adafruit_Video_Looper/omxplayer.py"
OMX_STOP_MARKER = "self.stop(3)"

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
VIDEO_LOOPER_STOP_MARKER = "self._player.stop(3)"
RUN_EMPTY_GUARD = """\
                if movie is None:
                    self._print(\"Current playlist is empty\")
                    self._playlist = self._build_playlist()
                    movie = self._playlist.get_next()
                    if movie is None:
                        self._player.stop(0)
                        time.sleep(0.1)
                        continue

"""
INIT_PATCH = """\
        self._rick_tv_fifo_path = self._config.get(
            'rick_tv', 'command_fifo', fallback='/tmp/rick-tv-videolooper.fifo'
        )
        self._rick_tv_fifo = None
        self._rick_tv_open_fifo()
        self._rick_tv_playlist_reload = False
        self._rick_tv_current_playlist_path = None
        self._rick_tv_current_playlist_mtime = None
        self._rick_tv_transition_frame_path = '/home/pi/rick-tv/system/transition-placeholder.fb'
        self._rick_tv_transition_frame = None
        self._rick_tv_interstitial_frame_path = '/home/pi/rick-tv/system/interstitial-ad.fb'
        self._rick_tv_interstitial_frame = None
        self._rick_tv_skip_next_interstitial = False
        self._rick_tv_should_prime_interstitial_background = False
"""
LEGACY_INIT_PATCHES = (
    """\
        self._rick_tv_fifo_path = self._config.get(
            'rick_tv', 'command_fifo', fallback='/tmp/rick-tv-videolooper.fifo'
        )
        self._rick_tv_fifo = None
        self._rick_tv_open_fifo()
        self._rick_tv_playlist_reload = False
        self._rick_tv_current_playlist_path = None
        self._rick_tv_current_playlist_mtime = None
        self._rick_tv_transition_frame = self._rick_tv_build_transition_frame()
""",
    INIT_PATCH,
)
RUN_PLAYLIST_FILE_GUARD = """\
                    if movie is None:
                        continue

"""
RUN_INTERSTITIAL_OLD_PATCH = """\
                    if movie is None:
                        continue

                    if not self._firstStart and not self._rick_tv_skip_next_interstitial:
                        self._rick_tv_show_interstitial_ad()
                    self._rick_tv_skip_next_interstitial = False
                    movie.was_played() # type: ignore
"""
RUN_INTERSTITIAL_GUARDED_PATCH = """\
                    if movie is None:
                        continue

                    self._rick_tv_should_prime_interstitial_background = self._rick_tv_skip_next_interstitial
                    if not self._firstStart and not self._rick_tv_skip_next_interstitial:
                        self._rick_tv_show_interstitial_ad()
                    self._rick_tv_skip_next_interstitial = False
                    movie.was_played() # type: ignore
"""
PRIME_INTERSTITIAL_BACKGROUND_PATCH = """\
                    self._player.play(movie, loop=player_loop, vol = self._sound_vol)
                    self._rick_tv_prime_interstitial_background()
"""
PLAYER_PLAY_BLOCK = """\
                    self._player.play(movie, loop=player_loop, vol = self._sound_vol)
"""
RICK_TV_FRAME_METHODS = (
    "_rick_tv_framebuffer_bytes",
    "_rick_tv_frame_for_display",
    "_rick_tv_show_transition_placeholder",
    "_rick_tv_show_interstitial_ad",
    "_rick_tv_prepare_framebuffer_console",
    "_rick_tv_prime_interstitial_background",
    "_rick_tv_build_transition_frame",
    "_rick_tv_framebuffer_size",
    "_rick_tv_read_int",
    "_rick_tv_read_text",
    "_rick_tv_set_pixel",
    "_rick_tv_rect",
    "_rick_tv_rect_outline",
    "_rick_tv_draw_text",
    "_rick_tv_guess_frame_size",
    "_rick_tv_resize_frame_to_display",
)

OPEN_METHOD_PATCH = """\
    def _rick_tv_open_fifo(self):
        if not self._rick_tv_fifo_path:
            return
        try:
            if not os.path.exists(self._rick_tv_fifo_path):
                os.mkfifo(self._rick_tv_fifo_path)
            os.chmod(self._rick_tv_fifo_path, 0o666)
            self._rick_tv_fifo = os.open(self._rick_tv_fifo_path, os.O_RDONLY | os.O_NONBLOCK)
            self._print(f\"Rick TV command FIFO ready: {self._rick_tv_fifo_path}\")
        except OSError as exc:
            self._rick_tv_fifo = None
            self._print(f\"Rick TV command FIFO unavailable: {exc}\")
"""

HANDLE_METHOD_PATCH = """\
    def _rick_tv_handle_fifo_commands(self):
        if self._rick_tv_fifo is None:
            return
        readable, _, _ = select.select([self._rick_tv_fifo], [], [], 0)
        if not readable:
            return
        try:
            payload = os.read(self._rick_tv_fifo, 4096).decode('utf-8')
        except OSError as exc:
            self._print(f\"Rick TV command FIFO read failed: {exc}\")
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
                playlist_mtime = self._rick_tv_playlist_mtime(command)
                if (
                    command == self._rick_tv_current_playlist_path
                    and playlist_mtime == self._rick_tv_current_playlist_mtime
                ):
                    self._print(f\"Rick TV playlist command unchanged; ignoring: {command}\")
                    continue
                self._print(f\"Rick TV loading playlist: {command}\")
                self._playlist_path = command
                self._player.stop(0)
                self._rick_tv_show_transition_placeholder()
                self._rick_tv_skip_next_interstitial = True
                self._playbackStopped = False
                self._playlist = None
                self._rick_tv_playlist_reload = True
                self._rick_tv_current_playlist_path = command
                self._rick_tv_current_playlist_mtime = playlist_mtime

"""

PLAYLIST_MTIME_METHOD_PATCH = """\
    def _rick_tv_playlist_mtime(self, playlist_path):
        try:
            return os.path.getmtime(playlist_path)
        except OSError:
            return None

"""

TRANSITION_PLACEHOLDER_METHOD_PATCH = """\
    def _rick_tv_framebuffer_bytes(self):
        try:
            width, height = self._rick_tv_framebuffer_size()
            stride = self._rick_tv_read_int('/sys/class/graphics/fb0/stride')
        except OSError as exc:
            self._print(f\"Rick TV transition placeholder framebuffer size unavailable: {exc}\")
            return None
        return stride * height

    def _rick_tv_frame_for_display(self, frame_path):
        expected_bytes = self._rick_tv_framebuffer_bytes()
        if expected_bytes is None:
            return None

        try:
            fd = os.open(frame_path, os.O_RDONLY)
            try:
                frame = os.read(fd, 8 * 1024 * 1024)
            finally:
                os.close(fd)
        except OSError as exc:
            self._print(f\"Rick TV transition/interstitial frame unavailable: {exc}\")
            return None

        if len(frame) == expected_bytes:
            return frame
        if len(frame) > expected_bytes:
            self._print(
                f\"Rick TV frame too large: got {len(frame)} bytes, expected {expected_bytes} bytes. Truncating.\"
            )
            return frame[:expected_bytes]
        self._print(
            f\"Rick TV frame too small: got {len(frame)} bytes, expected {expected_bytes} bytes. Zero-padding.\"
        )
        return frame + b\"\\0\" * (expected_bytes - len(frame))

    def _rick_tv_show_transition_placeholder(self):
        frame = self._rick_tv_transition_frame
        expected_bytes = self._rick_tv_framebuffer_bytes()
        if expected_bytes is None:
            return
        if frame is None:
            frame = self._rick_tv_frame_for_display(self._rick_tv_transition_frame_path)
            if frame is None:
                return
            if len(frame) != expected_bytes:
                return
            self._rick_tv_transition_frame = frame
        elif len(frame) != expected_bytes:
            frame = self._rick_tv_frame_for_display(self._rick_tv_transition_frame_path)
            if frame is None or len(frame) != expected_bytes:
                return
            self._rick_tv_transition_frame = frame
        if not frame:
            return
        self._rick_tv_prepare_framebuffer_console()
        try:
            fd = os.open('/dev/fb0', os.O_WRONLY)
            try:
                os.write(fd, frame)
            finally:
                os.close(fd)
        except OSError as exc:
            self._print(f\"Rick TV transition placeholder unavailable: {exc}\")

    def _rick_tv_show_interstitial_ad(self):
        frame = self._rick_tv_interstitial_frame
        expected_bytes = self._rick_tv_framebuffer_bytes()
        if expected_bytes is None:
            return
        if frame is None:
            frame = self._rick_tv_frame_for_display(self._rick_tv_interstitial_frame_path)
            if frame is None:
                return
            if len(frame) != expected_bytes:
                return
            self._rick_tv_interstitial_frame = frame
        elif len(frame) != expected_bytes:
            frame = self._rick_tv_frame_for_display(self._rick_tv_interstitial_frame_path)
            if frame is None or len(frame) != expected_bytes:
                return
            self._rick_tv_interstitial_frame = frame
        if not frame:
            return
        self._rick_tv_prepare_framebuffer_console()
        try:
            fd = os.open('/dev/fb0', os.O_WRONLY)
            try:
                os.write(fd, frame)
            finally:
                os.close(fd)
        except OSError as exc:
            self._print(f\"Rick TV interstitial ad unavailable: {exc}\")

    def _rick_tv_prepare_framebuffer_console(self):
        try:
            fd = os.open('/sys/class/graphics/fbcon/cursor_blink', os.O_WRONLY)
            try:
                os.write(fd, b'0')
            finally:
                os.close(fd)
        except OSError:
            pass
        try:
            fd = os.open('/dev/tty1', os.O_WRONLY | os.O_NONBLOCK)
            try:
                os.write(fd, b'\\033[?25l\\033[2J\\033[H')
            finally:
                os.close(fd)
        except OSError:
            pass

    def _rick_tv_prime_interstitial_background(self):
        try:
            if not self._rick_tv_should_prime_interstitial_background:
                return
            self._rick_tv_should_prime_interstitial_background = False
            time.sleep(1.0)
            if self._player.is_playing():
                self._rick_tv_show_interstitial_ad()
        except Exception as exc:
            self._print(f\"Rick TV interstitial background prime failed: {exc}\")

    def _rick_tv_build_transition_frame(self):
        try:
            width, height = self._rick_tv_framebuffer_size()
            bpp = self._rick_tv_read_int('/sys/class/graphics/fb0/bits_per_pixel')
            stride = self._rick_tv_read_int('/sys/class/graphics/fb0/stride')
        except OSError as exc:
            self._print(f\"Rick TV transition placeholder init failed: {exc}\")
            return None
        if bpp != 32:
            self._print(f\"Rick TV transition placeholder unsupported bpp: {bpp}\")
            return None

        frame = bytearray(stride * height)
        colors = (
            (190, 190, 190),
            (190, 190, 0),
            (0, 190, 190),
            (0, 190, 0),
            (190, 0, 190),
            (190, 0, 0),
            (0, 0, 190),
        )
        bar_width = max(1, width // len(colors))
        for y in range(height):
            for x in range(width):
                self._rick_tv_set_pixel(frame, stride, x, y, colors[min(x // bar_width, len(colors) - 1)])

        for i in range((width * height) // 24):
            x = (i * 1103515245 + 12345) % width
            y = (i * 214013 + 2531011) % height
            shade = (i * 37) % 256
            self._rick_tv_set_pixel(frame, stride, x, y, (shade, shade, shade))

        band_h = max(120, height // 5)
        band_y = height - band_h
        self._rick_tv_rect(frame, stride, 0, band_y, width, band_h, (0, 0, 0))
        self._rick_tv_rect_outline(frame, stride, width // 12, band_y + 24, width * 5 // 6, band_h - 48)
        self._rick_tv_draw_text(frame, stride, width // 2 - 110, band_y + 48, 'RICK TV', 7)
        self._rick_tv_draw_text(frame, stride, width // 2 - 144, band_y + 112, 'CHANNEL SYNC', 4)
        return bytes(frame)

    def _rick_tv_framebuffer_size(self):
        raw = self._rick_tv_read_text('/sys/class/graphics/fb0/virtual_size')
        width, height = raw.split(',', 1)
        return int(width), int(height)

    def _rick_tv_read_int(self, path):
        return int(self._rick_tv_read_text(path))

    def _rick_tv_read_text(self, path):
        fd = os.open(path, os.O_RDONLY)
        try:
            return os.read(fd, 128).decode('ascii').strip()
        finally:
            os.close(fd)

    def _rick_tv_set_pixel(self, frame, stride, x, y, rgb):
        r, g, b = rgb
        offset = y * stride + x * 4
        frame[offset:offset + 4] = bytes((b, g, r, 0))

    def _rick_tv_rect(self, frame, stride, x, y, w, h, rgb):
        for yy in range(max(0, y), max(0, y) + max(0, h)):
            for xx in range(max(0, x), max(0, x) + max(0, w)):
                self._rick_tv_set_pixel(frame, stride, xx, yy, rgb)

    def _rick_tv_rect_outline(self, frame, stride, x, y, w, h):
        for i in range(4):
            self._rick_tv_rect(frame, stride, x + i, y + i, w - i * 2, 1, (255, 255, 255))
            self._rick_tv_rect(frame, stride, x + i, y + h - i - 1, w - i * 2, 1, (255, 255, 255))
            self._rick_tv_rect(frame, stride, x + i, y + i, 1, h - i * 2, (255, 255, 255))
            self._rick_tv_rect(frame, stride, x + w - i - 1, y + i, 1, h - i * 2, (255, 255, 255))

    def _rick_tv_draw_text(self, frame, stride, x, y, text, scale):
        font = {
            'A': ('01110', '10001', '10001', '11111', '10001', '10001', '10001'),
            'C': ('01111', '10000', '10000', '10000', '10000', '10000', '01111'),
            'E': ('11111', '10000', '10000', '11110', '10000', '10000', '11111'),
            'H': ('10001', '10001', '10001', '11111', '10001', '10001', '10001'),
            'I': ('11111', '00100', '00100', '00100', '00100', '00100', '11111'),
            'K': ('10001', '10010', '10100', '11000', '10100', '10010', '10001'),
            'L': ('10000', '10000', '10000', '10000', '10000', '10000', '11111'),
            'N': ('10001', '11001', '10101', '10011', '10001', '10001', '10001'),
            'R': ('11110', '10001', '10001', '11110', '10100', '10010', '10001'),
            'S': ('01111', '10000', '10000', '01110', '00001', '00001', '11110'),
            'T': ('11111', '00100', '00100', '00100', '00100', '00100', '00100'),
            'V': ('10001', '10001', '10001', '10001', '10001', '01010', '00100'),
            'Y': ('10001', '10001', '01010', '00100', '00100', '00100', '00100'),
            ' ': ('00000', '00000', '00000', '00000', '00000', '00000', '00000'),
        }
        cursor = x
        for char in text:
            glyph = font.get(char.upper(), font[' '])
            for row, bits in enumerate(glyph):
                for col, bit in enumerate(bits):
                    if bit == '1':
                        self._rick_tv_rect(frame, stride, cursor + col * scale, y + row * scale, scale, scale, (255, 255, 255))
            cursor += 6 * scale

"""


def _find_method_blocks(text: str, method_name: str) -> List[Tuple[int, int]]:
    marker = f"    def {method_name}(self):\n"
    starts: List[int] = []
    index = 0
    while True:
        index = text.find(marker, index)
        if index == -1:
            break
        starts.append(index)
        index += len(marker)

    if len(starts) <= 1:
        return []

    blocks: List[Tuple[int, int]] = []
    for start in starts:
        end = text.find("\n    def ", start + 1)
        if end == -1:
            end = len(text)
        blocks.append((start, end))
    return blocks


def _method_block_indices(lines: list[str], method_name: str) -> Tuple[int, int] | None:
    start_pattern = f"    def {method_name}(self):"
    for index, line in enumerate(lines):
        if line.startswith(start_pattern):
            start = index
            break
    else:
        return None

    for end in range(start + 1, len(lines)):
        candidate = lines[end]
        if candidate.startswith("    def ") and not candidate.startswith("        "):
            return start, end

    return start, len(lines)


def _remove_method(text: str, method_name: str) -> Tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    marker = f"    def {method_name}(self"
    start = None
    for index, line in enumerate(lines):
        if line.startswith(marker):
            start = index
            break
    if start is None:
        return text, False

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("    def "):
            end = index
            break
    if start > 0 and lines[start - 1].strip() == "":
        start -= 1
    return "".join(lines[:start] + lines[end:]), True


def _remove_methods(text: str, method_names: Tuple[str, ...]) -> str:
    for method_name in method_names:
        while True:
            text, removed = _remove_method(text, method_name)
            if not removed:
                break
    return text


def _inject_run_fifo_realtime(text: str) -> str:
    lines = text.splitlines()
    run_block = _method_block_indices(lines, "run")
    if run_block is None:
        return text
    run_start, run_end = run_block

    while_index = None
    for i in range(run_start, run_end):
        if lines[i].strip() == "while self._running:":
            while_index = i
            break
    if while_index is None:
        return text

    for line in lines[while_index + 1 : while_index + 10]:
        if line.strip() == "self._rick_tv_handle_fifo_commands()":
            return text

    snippet = [
        "            self._rick_tv_handle_fifo_commands()",
        "            if self._rick_tv_playlist_reload:",
        "                self._playlist = self._build_playlist()",
        "                movie = self._playlist.get_next()",
        "                self._rick_tv_playlist_reload = False",
        "",
    ]
    insert_index = while_index + 1
    lines = lines[:insert_index] + snippet + lines[insert_index:]
    return "\n".join(lines)


def _remove_keyboard_fifo_injection(text: str) -> str:
    lines = text.splitlines()
    keyboard_block = _method_block_indices(lines, "_handle_keyboard_shortcuts")
    if keyboard_block is None:
        return text

    block_start, block_end = keyboard_block
    cleaned: list[str] = []
    removed = False
    i = block_start
    while i < block_end:
        line = lines[i]
        if "_rick_tv_handle_fifo_commands" in line:
            removed = True
            i += 1
            continue
        if "if self._rick_tv_playlist_reload:" in line:
            removed = True
            indent = len(line) - len(line.lstrip(" "))
            i += 1
            while i < block_end:
                next_line = lines[i]
                next_indent = len(next_line) - len(next_line.lstrip(" "))
                if next_line.strip() == "":
                    i += 1
                    continue
                if next_indent <= indent:
                    break
                i += 1
            continue
        cleaned.append(line)
        i += 1

    if not removed:
        return text
    return "\n".join(lines[:block_start] + cleaned + lines[block_end:])


def _remove_rick_tv_init_patch(text: str) -> str:
    marker_index = text.find(INIT_MARKER)
    if marker_index == -1:
        return text

    block_start = text.find(
        "        self._rick_tv_fifo_path = self._config.get(",
        0,
        marker_index,
    )
    if block_start == -1:
        return text

    return text[:block_start] + text[marker_index:]


def _upsert_method(text: str, method_name: str, replacement: str) -> str:
    blocks = _find_method_blocks(text, method_name)
    if not blocks:
        return insert_once(text, METHOD_MARKER, replacement, after=False)

    replacement_with_trailing = replacement.rstrip("\n") + "\n"
    start, end = blocks[-1]
    text = text[:start] + replacement_with_trailing + "\n" + text[end:]

    if len(blocks) > 1:
        for block_start, block_end in reversed(blocks[:-1]):
            text = text[:block_start] + text[block_end:]

    return text


def insert_once(text: str, marker: str, patch: str, *, after: bool) -> str:
    if patch.strip() in text:
        return text
    index = text.index(marker)
    if after:
        index += len(marker)
    return text[:index] + patch + text[index:]


def main() -> None:
    _patch_target(VIDEO_LOOPER, patch_text, VIDEO_LOOPER_EGG, VIDEO_LOOPER_ZIP_NAME)
    _patch_target(OMX_PLAYER, patch_omxplayer_text, OMX_PLAYER_EGG, OMX_PLAYER_ZIP_NAME)


def _patch_target(
    target_path: Path,
    patch_fn,
    egg_path: Path,
    zip_name: str,
) -> None:
    if target_path.exists():
        target_path.write_text(patch_fn(target_path.read_text()))
        return

    if not egg_path.exists():
        return

    with zipfile.ZipFile(str(egg_path), "r") as source:
        names = {item.filename for item in source.infolist()}
        if zip_name not in names:
            return
        patched_text = patch_fn(source.read(zip_name).decode("utf-8"))
        with tempfile.NamedTemporaryFile(delete=False) as target_file:
            out_path = Path(target_file.name)
        with zipfile.ZipFile(str(out_path), "w") as target:
            for item in source.infolist():
                if item.filename == "Adafruit_Video_Looper/__pycache__/video_looper.cpython-37.pyc":
                    continue
                data = source.read(item.filename)
                if item.filename == zip_name:
                    data = patched_text.encode("utf-8")
                target.writestr(item, data)

    out_path.replace(egg_path)
    os.chmod(str(egg_path), 0o644)


def patch_text(text: str) -> str:
    for init_patch in LEGACY_INIT_PATCHES:
        text = text.replace(init_patch, "")
    text = _remove_methods(text, RICK_TV_FRAME_METHODS)
    text = _remove_rick_tv_init_patch(text)
    text = insert_once(text, IMPORT_MARKER, IMPORT_PATCH, after=True)
    text = insert_once(text, INIT_MARKER, INIT_PATCH, after=False)
    text = text.replace(INIT_PATCH + INIT_PATCH, INIT_PATCH)
    if "self._rick_tv_should_prime_interstitial_background = False" not in text:
        text = text.replace(
            "        self._rick_tv_skip_next_interstitial = False\n",
            "        self._rick_tv_skip_next_interstitial = False\n"
            "        self._rick_tv_should_prime_interstitial_background = False\n",
        )
    text = _remove_keyboard_fifo_injection(text)
    text = _inject_run_fifo_realtime(text)
    text = _upsert_method(text, "_rick_tv_open_fifo", OPEN_METHOD_PATCH)
    text = _upsert_method(text, "_rick_tv_handle_fifo_commands", HANDLE_METHOD_PATCH)
    text = _upsert_method(text, "_rick_tv_playlist_mtime", PLAYLIST_MTIME_METHOD_PATCH)
    text = _upsert_method(
        text,
        "_rick_tv_show_transition_placeholder",
        TRANSITION_PLACEHOLDER_METHOD_PATCH,
    )
    text = text.replace(
        "            if not self._player.is_playing() and not self._playbackStopped:\n"
        "                if movie is not None: #just to avoid errors\n"
        "                    if self._rick_tv_playlist_reload:\n"
        "                        self._playlist = self._build_playlist()\n"
        "                        movie = self._playlist.get_next()\n"
        "                        self._rick_tv_playlist_reload = False\n",
        "            if not self._player.is_playing() and not self._playbackStopped:\n"
        "                if self._rick_tv_playlist_reload:\n"
        "                    self._playlist = self._build_playlist()\n"
        "                    movie = self._playlist.get_next()\n"
        "                    self._rick_tv_playlist_reload = False\n"
        "                if movie is not None: #just to avoid errors\n",
    )
    text = text.replace(
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            # but increase CPU usage\n"
        "            # since keyboard commands are handled in a seperate thread this sleeptime mostly influences the pause between files\n"
        "\n"
        "            self._rick_tv_handle_fifo_commands()\n"
        "            if self._rick_tv_playlist_reload:\n"
        "                self._playlist = self._build_playlist()\n"
        "                movie = self._playlist.get_next()\n"
        "                self._rick_tv_playlist_reload = False\n"
        "\n"
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            # but increase CPU usage\n"
        "            # since keyboard commands are handled in a seperate thread this sleeptime mostly influences the pause between files\n"
        "\n"
        "            time.sleep(0.002)\n",
        "            # Give the CPU some time to do other tasks. low values increase \"responsiveness to changes\" and reduce the pause between files\n"
        "            # but increase CPU usage\n"
        "            # since keyboard commands are handled in a seperate thread this sleeptime mostly influences the pause between files\n"
        "\n"
        "            time.sleep(0.002)\n",
    )
    text = re.sub(
        r"\n(\s*self._rick_tv_handle_fifo_commands\(\)\n)\s*self._rick_tv_handle_fifo_commands\(\)\n(\s*if self._rick_tv_playlist_reload:\n)",
        r"\n\1\2",
        text,
    )
    text = text.replace(
        "            if not self._player.is_playing() and not self._playbackStopped:\n                if movie is not None: #just to avoid errors\n",
        "            if not self._player.is_playing() and not self._playbackStopped:\n"
        + RUN_EMPTY_GUARD
        + "                if movie is not None: #just to avoid errors\n",
    )
    text = text.replace(
        NESTED_PLAYLIST_BUG,
        "                        self._playlist_path = movie.target # type: ignore\n",
    )
    text = text.replace(ABSOLUTE_PLAYLIST_BUG, ABSOLUTE_PLAYLIST_FIX)
    text = text.replace(PYGAME_DISPLAY_BLOCK, PYGAME_DISPLAY_PATCH)
    text = text.replace(BLANK_SCREEN_BLOCK, BLANK_SCREEN_PATCH)
    text = text.replace(FONT_BLOCK, FONT_PATCH)
    text = text.replace(VIDEO_LOOPER_STOP_MARKER, "self._player.stop(0)")
    text = text.replace(
        "                    if \".m3u\" in movie.filename: # type: ignore\n",
        "                    if movie is not None and \".m3u\" in movie.filename: # type: ignore\n",
    )
    text = text.replace(PRIME_INTERSTITIAL_BACKGROUND_PATCH, PLAYER_PLAY_BLOCK)
    text = text.replace(PLAYER_PLAY_BLOCK, PRIME_INTERSTITIAL_BACKGROUND_PATCH)
    text = text.replace(RUN_INTERSTITIAL_OLD_PATCH, RUN_INTERSTITIAL_GUARDED_PATCH)
    if "self._rick_tv_should_prime_interstitial_background = self._rick_tv_skip_next_interstitial" not in text:
        text = text.replace(
            "                    movie.was_played() # type: ignore\n",
            RUN_INTERSTITIAL_GUARDED_PATCH,
        )
    return text


def patch_omxplayer_text(text: str) -> str:
    return text.replace(OMX_STOP_MARKER, "self.stop(0)")


if __name__ == "__main__":
    main()
