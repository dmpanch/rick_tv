#!/usr/bin/env python3
from __future__ import annotations

"""Draw a Rick TV transition card directly to the Linux framebuffer."""

import os
import sys
import time
from pathlib import Path


FB_DEVICE = Path("/dev/fb0")
FB_SYS = Path("/sys/class/graphics/fb0")
BAR_COLORS = [
    (190, 190, 190),
    (190, 190, 0),
    (0, 190, 190),
    (0, 190, 0),
    (190, 0, 190),
    (190, 0, 0),
    (0, 0, 190),
]


def main() -> None:
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    width, height = _read_virtual_size()
    bpp = _read_int(FB_SYS / "bits_per_pixel")
    stride = _read_int(FB_SYS / "stride")
    if bpp != 32:
        raise SystemExit(f"Unsupported framebuffer depth: {bpp}")

    if output_path is not None:
        frame = _build_frame(width, height, stride)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(frame)
        return

    end_at = time.time() + duration
    while True:
        _draw_frame(width, height, stride)
        if duration <= 0 or time.time() >= end_at:
            break
        time.sleep(0.18)


def _draw_frame(width: int, height: int, stride: int) -> None:
    frame = _build_frame(width, height, stride)
    fd = os.open(str(FB_DEVICE), os.O_WRONLY)
    try:
        os.write(fd, frame)
    finally:
        os.close(fd)


def _build_frame(width: int, height: int, stride: int) -> bytes:
    row = bytearray(stride)
    bar_width = max(1, width // len(BAR_COLORS))
    for x in range(width):
        color = BAR_COLORS[min(x // bar_width, len(BAR_COLORS) - 1)]
        _set_pixel(row, stride, x, 0, color)

    frame = bytearray(row * height)
    band_h = max(120, height // 5)
    band_y = height - band_h
    _rect(frame, stride, 0, band_y, width, band_h, (0, 0, 0))
    _draw_text(frame, stride, width // 2 - 330, band_y + 64, "INTERDIMENSIONAL", scale=5)
    _draw_text(frame, stride, width // 2 - 108, band_y + 118, "CABLE", scale=5)

    return bytes(frame)


def _set_pixel(frame: bytearray, stride: int, x: int, y: int, rgb: tuple[int, int, int]) -> None:
    r, g, b = rgb
    offset = y * stride + x * 4
    frame[offset : offset + 4] = bytes((b, g, r, 0))


def _rect(
    frame: bytearray,
    stride: int,
    x: int,
    y: int,
    w: int,
    h: int,
    rgb: tuple[int, int, int],
) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            _set_pixel(frame, stride, xx, yy, rgb)


def _rect_outline(frame: bytearray, stride: int, x: int, y: int, w: int, h: int) -> None:
    for i in range(4):
        _rect(frame, stride, x + i, y + i, w - i * 2, 1, (255, 255, 255))
        _rect(frame, stride, x + i, y + h - i - 1, w - i * 2, 1, (255, 255, 255))
        _rect(frame, stride, x + i, y + i, 1, h - i * 2, (255, 255, 255))
        _rect(frame, stride, x + w - i - 1, y + i, 1, h - i * 2, (255, 255, 255))


FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}


def _draw_text(frame: bytearray, stride: int, x: int, y: int, text: str, *, scale: int) -> None:
    cursor = x
    for char in text:
        glyph = FONT.get(char.upper(), FONT[" "])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == "1":
                    _rect(
                        frame,
                        stride,
                        cursor + col * scale,
                        y + row * scale,
                        scale,
                        scale,
                        (255, 255, 255),
                    )
        cursor += 6 * scale


def _read_virtual_size() -> tuple[int, int]:
    width, height = (FB_SYS / "virtual_size").read_text().strip().split(",", 1)
    return int(width), int(height)


def _read_int(path: Path) -> int:
    return int(path.read_text().strip())


if __name__ == "__main__":
    main()
