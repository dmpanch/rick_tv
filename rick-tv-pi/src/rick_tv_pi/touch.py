from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SwipeAction = Literal["next", "previous"]


@dataclass(frozen=True)
class TouchPoint:
    x: int
    y: int
    timestamp: float


class TouchInterpreter:
    def __init__(self, cooldown_seconds: float) -> None:
        self.cooldown_seconds = cooldown_seconds

    def interpret(self, start: TouchPoint, end: TouchPoint) -> SwipeAction | None:
        horizontal_delta = end.x - start.x
        vertical_delta = end.y - start.y

        if abs(horizontal_delta) < 80:
            return None
        if abs(horizontal_delta) <= abs(vertical_delta):
            return None
        if horizontal_delta < 0:
            return "next"
        return "previous"
