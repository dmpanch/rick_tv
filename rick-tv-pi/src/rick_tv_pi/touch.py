from __future__ import annotations

from dataclasses import dataclass

try:
    from typing import Literal
except ImportError:  # pragma: no cover - Python 3.7 runtime compatibility.
    from typing_extensions import Literal


SwipeAction = Literal["next", "previous"]


@dataclass(frozen=True)
class TouchPoint:
    x: int
    y: int
    timestamp: float


class TouchInterpreter:
    def __init__(
        self,
        cooldown_seconds: float,
        gesture_horizontal_axis: Literal["x", "y"] = "x",
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.gesture_horizontal_axis = gesture_horizontal_axis
        self._last_action_at: float | None = None

    def interpret(self, start: TouchPoint, end: TouchPoint) -> SwipeAction | None:
        if self.gesture_horizontal_axis == "x":
            horizontal_delta = end.x - start.x
            vertical_delta = end.y - start.y
        else:
            horizontal_delta = end.y - start.y
            vertical_delta = end.x - start.x

        if abs(horizontal_delta) < 60:
            return None
        if abs(horizontal_delta) <= abs(vertical_delta) * 1.3:
            return None
        if horizontal_delta > 0:
            action: SwipeAction = "next"
        else:
            action = "previous"

        if (
            self._last_action_at is not None
            and start.timestamp - self._last_action_at < self.cooldown_seconds
        ):
            return None

        self._last_action_at = start.timestamp
        return action
