from rick_tv_pi.touch_source import (
    AbsInfo,
    EvdevTouchSource,
    TouchDevice,
    TouchEvent,
    TouchEventCodes,
    choose_touch_device,
)


def test_choose_touch_device_prefers_env_override():
    devices = [
        TouchDevice(path="/dev/input/event0", name="keyboard", capabilities={}),
        TouchDevice(path="/dev/input/event4", name="Waveshare Touch", capabilities={}),
    ]

    selected = choose_touch_device(devices, override_path="/dev/input/event4")

    assert selected == devices[1]


def test_choose_touch_device_detects_touchscreen_capabilities():
    keyboard = TouchDevice(
        path="/dev/input/event0",
        name="keyboard",
        capabilities={TouchEventCodes.EV_KEY: [TouchEventCodes.KEY_A]},
    )
    touchscreen = TouchDevice(
        path="/dev/input/event2",
        name="Waveshare 2.8 DPI touchscreen",
        capabilities={
            TouchEventCodes.EV_KEY: [TouchEventCodes.BTN_TOUCH],
            TouchEventCodes.EV_ABS: [
                TouchEventCodes.ABS_MT_POSITION_X,
                TouchEventCodes.ABS_MT_POSITION_Y,
            ],
        },
    )

    selected = choose_touch_device([keyboard, touchscreen], override_path=None)

    assert selected == touchscreen


def test_evdev_touch_source_emits_swipe_points_from_multitouch_events():
    device = FakeInputDevice(
        events=[
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_X, 200, 1.0),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_Y, 100, 1.0),
            TouchEvent(TouchEventCodes.EV_KEY, TouchEventCodes.BTN_TOUCH, 1, 1.0),
            TouchEvent(TouchEventCodes.EV_SYN, TouchEventCodes.SYN_REPORT, 0, 1.0),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_X, 20, 1.2),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_Y, 110, 1.2),
            TouchEvent(TouchEventCodes.EV_KEY, TouchEventCodes.BTN_TOUCH, 0, 1.2),
            TouchEvent(TouchEventCodes.EV_SYN, TouchEventCodes.SYN_REPORT, 0, 1.2),
        ]
    )
    source = EvdevTouchSource(input_device=device)

    gestures = list(source.gestures())

    assert len(gestures) == 1
    start, end = gestures[0]
    assert (start.x, start.y, start.timestamp) == (200, 100, 1.0)
    assert (end.x, end.y, end.timestamp) == (20, 110, 1.2)


def test_evdev_touch_source_scales_absolute_coordinates_to_screen():
    device = FakeInputDevice(
        events=[
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_X, 960, 1.0),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_Y, 320, 1.0),
            TouchEvent(TouchEventCodes.EV_KEY, TouchEventCodes.BTN_TOUCH, 1, 1.0),
            TouchEvent(TouchEventCodes.EV_SYN, TouchEventCodes.SYN_REPORT, 0, 1.0),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_X, 0, 1.2),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_Y, 320, 1.2),
            TouchEvent(TouchEventCodes.EV_KEY, TouchEventCodes.BTN_TOUCH, 0, 1.2),
            TouchEvent(TouchEventCodes.EV_SYN, TouchEventCodes.SYN_REPORT, 0, 1.2),
        ],
        absinfo={
            TouchEventCodes.ABS_MT_POSITION_X: AbsInfo(min=0, max=960),
            TouchEventCodes.ABS_MT_POSITION_Y: AbsInfo(min=0, max=640),
        },
    )
    source = EvdevTouchSource(input_device=device, screen_width=480, screen_height=640, swap_axes=False)

    gestures = list(source.gestures())

    assert gestures[0][0].x == 480
    assert gestures[0][0].y == 320
    assert gestures[0][1].x == 0
    assert gestures[0][1].y == 320


def test_evdev_touch_source_swaps_axes_when_enabled():
    device = FakeInputDevice(
        events=[
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_X, 100, 1.0),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_Y, 400, 1.0),
            TouchEvent(TouchEventCodes.EV_KEY, TouchEventCodes.BTN_TOUCH, 1, 1.0),
            TouchEvent(TouchEventCodes.EV_SYN, TouchEventCodes.SYN_REPORT, 0, 1.0),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_X, 200, 1.2),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_Y, 300, 1.2),
            TouchEvent(TouchEventCodes.EV_KEY, TouchEventCodes.BTN_TOUCH, 0, 1.2),
            TouchEvent(TouchEventCodes.EV_SYN, TouchEventCodes.SYN_REPORT, 0, 1.2),
        ],
        absinfo={
            TouchEventCodes.ABS_MT_POSITION_X: AbsInfo(min=0, max=639),
            TouchEventCodes.ABS_MT_POSITION_Y: AbsInfo(min=0, max=479),
        },
    )
    source = EvdevTouchSource(
        input_device=device,
        screen_width=480,
        screen_height=640,
        swap_axes=True,
    )

    gestures = list(source.gestures())

    assert gestures[0][0].x == round(400 / 479 * 480)
    assert gestures[0][0].y == round(100 / 639 * 640)
    assert gestures[0][1].x == round(300 / 479 * 480)
    assert gestures[0][1].y == round(200 / 639 * 640)


def test_evdev_touch_source_auto_swaps_axes_for_portait_display():
    device = FakeInputDevice(
        events=[
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_X, 100, 1.0),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_Y, 400, 1.0),
            TouchEvent(TouchEventCodes.EV_KEY, TouchEventCodes.BTN_TOUCH, 1, 1.0),
            TouchEvent(TouchEventCodes.EV_SYN, TouchEventCodes.SYN_REPORT, 0, 1.0),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_X, 200, 1.2),
            TouchEvent(TouchEventCodes.EV_ABS, TouchEventCodes.ABS_MT_POSITION_Y, 300, 1.2),
            TouchEvent(TouchEventCodes.EV_KEY, TouchEventCodes.BTN_TOUCH, 0, 1.2),
            TouchEvent(TouchEventCodes.EV_SYN, TouchEventCodes.SYN_REPORT, 0, 1.2),
        ],
        absinfo={
            TouchEventCodes.ABS_MT_POSITION_X: AbsInfo(min=0, max=639),
            TouchEventCodes.ABS_MT_POSITION_Y: AbsInfo(min=0, max=479),
        },
    )
    source = EvdevTouchSource(
        input_device=device,
        screen_width=480,
        screen_height=640,
        swap_axes="auto",
    )

    gestures = list(source.gestures())

    assert gestures[0][0].x == round(400 / 479 * 480)
    assert gestures[0][0].y == round(100 / 639 * 640)


class FakeInputDevice:
    def __init__(self, events, absinfo=None):
        self._events = events
        self._absinfo = absinfo or {}

    def read_loop(self):
        yield from self._events

    def absinfo(self, code):
        return self._absinfo.get(code)
