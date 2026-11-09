"""Turns pin readings into Key presses."""
from collections.abc import Callable, Sequence


class KeyWatcher:
    """Reports each Key once per press, by its position in the config."""

    def __init__(self, pins: Sequence[int], read_pin: Callable[[int], bool]) -> None:
        self._pins = list(pins)
        self._read_pin = read_pin
        self._was_pressed = [False] * len(self._pins)

    def poll(self) -> list[int]:
        """Return the indexes of Keys pressed since the last poll."""
        pressed: list[int] = []
        for index, pin in enumerate(self._pins):
            is_pressed = self._read_pin(pin)
            if is_pressed and not self._was_pressed[index]:
                pressed.append(index)
            self._was_pressed[index] = is_pressed
        return pressed
