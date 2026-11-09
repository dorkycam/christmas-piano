"""Decides what the lights should show at each moment. It does no network or clock work itself."""
from dataclasses import dataclass

from christmas_piano.config import RGB, PianoConfig

DEFAULT_UPDATE_INTERVAL = 0.1


@dataclass(frozen=True)
class LightCommand:
    """A color and brightness to send to the lights."""

    color: RGB
    brightness: int


def _blend(start: LightCommand, end: LightCommand, progress: float) -> LightCommand:
    """Return the look part of the way from start to end."""

    def mix(first: int, second: int) -> int:
        return round(first + (second - first) * progress)

    red, green, blue = (mix(first, second) for first, second in zip(start.color, end.color))
    return LightCommand((red, green, blue), mix(start.brightness, end.brightness))


class LightDirector:
    """Tracks the latest Key and works out the hold, fade and Resting Look."""

    def __init__(self, update_interval: float = DEFAULT_UPDATE_INTERVAL) -> None:
        self._update_interval = update_interval
        self._key_index: int | None = None
        self._pressed_at = 0.0
        self._sent_at: float | None = None
        self._last_command: LightCommand | None = None

    def press(self, key_index: int, now: float) -> None:
        """Record a Key press. Only the latest Key is remembered."""
        self._key_index = key_index
        self._pressed_at = now

    def _desired(self, now: float, config: PianoConfig) -> LightCommand:
        resting = LightCommand(config.resting_look.color, config.resting_look.brightness)
        if self._key_index is None or self._key_index >= len(config.keys):
            self._key_index = None
            return resting
        key_look = LightCommand(config.keys[self._key_index].color, config.key_brightness)
        elapsed = now - self._pressed_at
        if elapsed < config.hold_seconds:
            return key_look
        fade_elapsed = elapsed - config.hold_seconds
        if fade_elapsed < config.fade_seconds:
            return _blend(key_look, resting, fade_elapsed / config.fade_seconds)
        self._key_index = None
        return resting

    def tick(self, now: float, config: PianoConfig) -> LightCommand | None:
        """Return the next look to send, or None if nothing needs sending yet."""
        desired = self._desired(now, config)
        if desired == self._last_command:
            return None
        if self._sent_at is not None and now - self._sent_at < self._update_interval:
            return None
        self._sent_at = now
        self._last_command = desired
        return desired
