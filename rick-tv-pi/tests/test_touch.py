from rick_tv_pi.touch import TouchInterpreter, TouchPoint


def test_left_swipe_returns_next():
    interpreter = TouchInterpreter(cooldown_seconds=0.5)

    action = interpreter.interpret(
        TouchPoint(x=200, y=100, timestamp=1.0),
        TouchPoint(x=20, y=100, timestamp=1.1),
    )

    assert action == "next"


def test_right_swipe_returns_previous():
    interpreter = TouchInterpreter(cooldown_seconds=0.5)

    action = interpreter.interpret(
        TouchPoint(x=20, y=100, timestamp=1.0),
        TouchPoint(x=200, y=100, timestamp=1.1),
    )

    assert action == "previous"


def test_left_swipe_returned_when_y_axis_used_for_gesture():
    interpreter = TouchInterpreter(cooldown_seconds=0.5, gesture_horizontal_axis="y")

    action = interpreter.interpret(
        TouchPoint(x=100, y=200, timestamp=1.0),
        TouchPoint(x=120, y=20, timestamp=1.1),
    )

    assert action == "next"


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
        TouchPoint(x=200, y=100, timestamp=1.0),
        TouchPoint(x=20, y=100, timestamp=1.1),
    )
    second_action = interpreter.interpret(
        TouchPoint(x=200, y=100, timestamp=1.3),
        TouchPoint(x=20, y=100, timestamp=1.4),
    )
    third_action = interpreter.interpret(
        TouchPoint(x=200, y=100, timestamp=1.6),
        TouchPoint(x=20, y=100, timestamp=1.7),
    )

    assert first_action == "next"
    assert second_action is None
    assert third_action == "next"
