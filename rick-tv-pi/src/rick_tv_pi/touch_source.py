from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

try:
    from typing import Protocol
except ImportError:  # pragma: no cover - Python 3.7 runtime compatibility.
    from typing_extensions import Protocol

from rick_tv_pi.touch import TouchPoint

logger = logging.getLogger(__name__)


class TouchEventCodes:
    EV_SYN = 0
    EV_KEY = 1
    EV_ABS = 3
    SYN_REPORT = 0
    KEY_A = 30
    BTN_TOUCH = 330
    ABS_X = 0
    ABS_Y = 1
    ABS_MT_POSITION_X = 53
    ABS_MT_POSITION_Y = 54
    ABS_MT_TRACKING_ID = 57


@dataclass(frozen=True)
class AbsInfo:
    min: int
    max: int


@dataclass(frozen=True)
class TouchEvent:
    type: int
    code: int
    value: int
    timestamp: float


@dataclass(frozen=True)
class TouchDevice:
    path: str
    name: str
    capabilities: dict[int, list[int]]


class InputDeviceLike(Protocol):
    def read_loop(self) -> Iterable[TouchEvent]: ...

    def absinfo(self, code: int) -> AbsInfo | None: ...


def choose_touch_device(
    devices: list[TouchDevice],
    override_path: str | None,
) -> TouchDevice | None:
    if override_path:
        return next((device for device in devices if device.path == override_path), None)

    return next((device for device in devices if _looks_like_touchscreen(device)), None)


def discover_touch_device(override_path: str | None = None) -> object | None:
    evdev = _load_evdev()
    if evdev is None:
        return None

    paths = [override_path] if override_path else sorted(str(path) for path in Path("/dev/input").glob("event*"))
    candidates = []
    raw_devices = []
    for path in paths:
        if path is None:
            continue
        try:
            raw_device = evdev.InputDevice(path)
            capabilities = raw_device.capabilities(absinfo=False)
        except OSError:
            continue
        raw_devices.append(raw_device)
        candidates.append(
            TouchDevice(
                path=path,
                name=getattr(raw_device, "name", ""),
                capabilities={
                    event_type: list(codes)
                    for event_type, codes in capabilities.items()
                    if isinstance(codes, list)
                },
            )
        )

    selected = choose_touch_device(candidates, override_path=override_path)
    if selected is None:
        return None

    index = candidates.index(selected)
    return raw_devices[index]


class EvdevTouchSource:
    def __init__(
        self,
        input_device: InputDeviceLike | None = None,
        *,
        screen_width: int = 480,
        screen_height: int = 640,
        device_path: str | None = None,
        swap_axes: bool | str = "auto",
        invert_x: bool = False,
        invert_y: bool = False,
    ) -> None:
        self._input_device = input_device or discover_touch_device(
            device_path or os.environ.get("RICK_TV_TOUCH_DEVICE")
        )
        self._screen_width = screen_width
        self._screen_height = screen_height
        if self._input_device is not None:
            self._x_abs_info = self._first_abs_info(
                TouchEventCodes.ABS_MT_POSITION_X,
                TouchEventCodes.ABS_X,
            )
            self._y_abs_info = self._first_abs_info(
                TouchEventCodes.ABS_MT_POSITION_Y,
                TouchEventCodes.ABS_Y,
            )
        else:
            self._x_abs_info = None
            self._y_abs_info = None
        self._swap_axes = self._resolve_swap_axes(swap_axes)
        self._invert_x = invert_x
        self._invert_y = invert_y
        self._touch_device_name = (
            getattr(self._input_device, "name", "unknown") if self._input_device else ""
        )

        logger.info(
            "Touch source init: device=%s swap_axes=%s invert_x=%s invert_y=%s "
            "raw_x=%s raw_y=%s screen=%sx%s",
            self._touch_device_name,
            self._swap_axes,
            self._invert_x,
            self._invert_y,
            self._abs_range(self._x_abs_info),
            self._abs_range(self._y_abs_info),
            self._screen_width,
            self._screen_height,
        )

    def gestures(self) -> Iterator[tuple[TouchPoint, TouchPoint]]:
        if self._input_device is None:
            return

        current_x: int | None = None
        current_y: int | None = None
        start: TouchPoint | None = None
        last: TouchPoint | None = None
        tracking_active = False

        for event in self._input_device.read_loop():
            event_timestamp = event.timestamp() if callable(event.timestamp) else event.timestamp

            if event.type == TouchEventCodes.EV_ABS:
                if event.code in (TouchEventCodes.ABS_MT_POSITION_X, TouchEventCodes.ABS_X):
                    current_x = event.value
                elif event.code in (TouchEventCodes.ABS_MT_POSITION_Y, TouchEventCodes.ABS_Y):
                    current_y = event.value
                elif event.code == TouchEventCodes.ABS_MT_TRACKING_ID:
                    if event.value < 0:
                        if start is not None and last is not None:
                            yield (start, TouchPoint(last.x, last.y, event_timestamp))
                        start = None
                        tracking_active = False
                    elif current_x is not None and current_y is not None:
                        start = self._to_screen_points((current_x, current_y), event_timestamp)
                        last = start
                        tracking_active = True
                if current_x is not None and current_y is not None:
                    last = self._to_screen_points((current_x, current_y), event_timestamp)

            elif event.type == TouchEventCodes.EV_KEY and event.code == TouchEventCodes.BTN_TOUCH:
                if event.value == 1 and current_x is not None and current_y is not None:
                    start = self._to_screen_points((current_x, current_y), event_timestamp)
                    last = start
                    tracking_active = True
                elif event.value == 0 and (start is not None or tracking_active) and last is not None:
                    fallback_start = start or TouchPoint(last.x, last.y, event_timestamp)
                    yield (fallback_start, TouchPoint(last.x, last.y, event_timestamp))
                    start = None
                    tracking_active = False

    def _to_screen_points(
        self,
        point: tuple[int, int],
        timestamp: float,
    ) -> TouchPoint:
        x, y = point
        if self._swap_axes:
            x, y = y, x
            raw_x_range = self._y_abs_info
            raw_y_range = self._x_abs_info
        else:
            raw_x_range = self._x_abs_info
            raw_y_range = self._y_abs_info

        scaled_x = self._scale_axis_value(x, raw_x_range, self._screen_width)
        scaled_y = self._scale_axis_value(y, raw_y_range, self._screen_height)

        if self._invert_x:
            scaled_x = self._screen_width - scaled_x
        if self._invert_y:
            scaled_y = self._screen_height - scaled_y
        return TouchPoint(x=scaled_x, y=scaled_y, timestamp=timestamp)

    def _scale_axis_value(
        self,
        value: int,
        absinfo: AbsInfo | None,
        target_max: int,
    ) -> int:
        if absinfo is None or absinfo.max <= absinfo.min:
            return value

        ratio = (value - absinfo.min) / (absinfo.max - absinfo.min)
        return round(max(0.0, min(1.0, ratio)) * target_max)

    def _first_abs_info(self, *codes: int) -> AbsInfo | None:
        if self._input_device is None:
            return None
        for code in codes:
            absinfo = self._input_device.absinfo(code)
            if absinfo is not None and absinfo.max > absinfo.min:
                return absinfo
        return None

    def _abs_range(self, absinfo: AbsInfo | None) -> str:
        if absinfo is None:
            return "<unknown>"
        return f"{absinfo.min}..{absinfo.max}"

    def _resolve_swap_axes(self, value: bool | str) -> bool:
        if isinstance(value, bool):
            return value
        if str(value).lower() in {"true", "1", "on", "yes"}:
            return True
        if str(value).lower() in {"false", "0", "off", "no"}:
            return False
        if self._x_abs_info is None or self._y_abs_info is None:
            return False
        x_range = self._x_abs_info.max - self._x_abs_info.min
        y_range = self._y_abs_info.max - self._y_abs_info.min
        return (x_range > y_range and self._screen_width < self._screen_height) or (
            x_range < y_range and self._screen_width > self._screen_height
        )


def _looks_like_touchscreen(device: TouchDevice) -> bool:
    keys = set(device.capabilities.get(TouchEventCodes.EV_KEY, []))
    axes = set(device.capabilities.get(TouchEventCodes.EV_ABS, []))
    has_touch_button = TouchEventCodes.BTN_TOUCH in keys
    has_multitouch_axes = {
        TouchEventCodes.ABS_MT_POSITION_X,
        TouchEventCodes.ABS_MT_POSITION_Y,
    }.issubset(axes)
    has_single_touch_axes = {
        TouchEventCodes.ABS_X,
        TouchEventCodes.ABS_Y,
    }.issubset(axes)
    name_hint = "touch" in device.name.lower() or "waveshare" in device.name.lower()
    return has_touch_button and (has_multitouch_axes or has_single_touch_axes or name_hint)


def _load_evdev():
    try:
        import evdev
    except ImportError:
        return None
    return evdev
