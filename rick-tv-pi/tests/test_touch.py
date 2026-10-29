import pytest

from rick_tv_pi.touch import TouchInterpreter, TouchPoint


def test_right_swipe_returns_next():
    interpreter = TouchInterpreter(cooldown_seconds=0.5)

    action = interpreter.interpret(
        TouchPoint(x=20, y=100, timestamp=1.0),
        TouchPoint(x=200, y=100, timestamp=1.1),
    )

    assert action == "next_video"


def test_left_swipe_returns_previous():
    interpreter = TouchInterpreter(cooldown_seconds=0.5)

    action = interpreter.interpret(
        TouchPoint(x=200, y=100, timestamp=1.0),
        TouchPoint(x=20, y=100, timestamp=1.1),
    )

    assert action == "previous_video"


def test_right_swipe_returned_when_y_axis_used_for_gesture():
    interpreter = TouchInterpreter(cooldown_seconds=0.5, gesture_horizontal_axis="y")

    action = interpreter.interpret(
        TouchPoint(x=100, y=20, timestamp=1.0),
        TouchPoint(x=120, y=200, timestamp=1.1),
    )

    assert action == "next_video"


def test_tap_movement_under_threshold_returns_none():
    interpreter = TouchInterpreter(cooldown_seconds=0.5)

    action = interpreter.interpret(
        TouchPoint(x=100, y=100, timestamp=1.0),
        TouchPoint(x=130, y=110, timestamp=1.1),
    )

    assert action is None


def test_cooldown_blocks_repeated_swipes():
    interpreter = TouchInterpreter(cooldown_seconds=0.5)

    first_action = interpreter.interpret(
        TouchPoint(x=20, y=100, timestamp=1.0),
        TouchPoint(x=200, y=100, timestamp=1.1),
    )
    second_action = interpreter.interpret(
        TouchPoint(x=20, y=100, timestamp=1.3),
        TouchPoint(x=200, y=100, timestamp=1.4),
    )
    third_action = interpreter.interpret(
        TouchPoint(x=20, y=100, timestamp=1.6),
        TouchPoint(x=200, y=100, timestamp=1.7),
    )

    assert first_action == "next_video"
    assert second_action is None
    assert third_action == "next_video"


@pytest.mark.parametrize('end,expected', [
    ((300, 200), 'next_video'), ((100, 200), 'previous_video'),
    ((200, 100), 'next'), ((200, 300), 'previous'),
    ((250, 200), None), ((200, 250), None),
    ((300, 300), None), ((270, 260), None),
    ((260, 200), 'next_video'),
])
def test_four_directions_and_ambiguous_gestures(end, expected):
    interpreter = TouchInterpreter(cooldown_seconds=0.5)
    assert interpreter.interpret(TouchPoint(200, 200, 1), TouchPoint(*end, 1.2)) == expected


@pytest.mark.parametrize('end,expected', [
    ((200, 300), 'next_video'), ((200, 100), 'previous_video'),
    ((100, 200), 'next'), ((300, 200), 'previous'),
])
def test_four_directions_respect_configured_horizontal_axis(end, expected):
    interpreter = TouchInterpreter(0.5, gesture_horizontal_axis='y')
    assert interpreter.interpret(TouchPoint(200, 200, 1), TouchPoint(*end, 1.2)) == expected


def test_cooldown_is_shared_across_video_and_channel_swipes():
    interpreter = TouchInterpreter(0.5)
    assert interpreter.interpret(TouchPoint(100, 100, 1), TouchPoint(200, 100, 1.1)) == 'next_video'
    assert interpreter.interpret(TouchPoint(100, 100, 1.3), TouchPoint(100, 0, 1.4)) is None
    assert interpreter.interpret(TouchPoint(100, 100, 1.5), TouchPoint(100, 0, 1.6)) == 'next'
