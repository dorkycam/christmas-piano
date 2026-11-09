"""Decides what the lights should show at each moment. It does no network or clock work itself."""
from dataclasses import dataclass

from christmas_piano.config import RGB, PianoConfig

DEFAULT_UPDATE_INTERVAL = 0.1
CHORD_WINDOW_SECONDS = 0.15


@dataclass(frozen=True)
class LightCommand:
    """A look to send to the lights. Non-empty `bands` means stripes in place of one color."""

    color: RGB
    brightness: int
    bands: tuple[RGB, ...] = ()


def _blend(start: LightCommand, end: LightCommand, progress: float) -> LightCommand:
    """Return the look part of the way from start to end."""

    def mix(first: int, second: int) -> int:
        return round(first + (second - first) * progress)

    red, green, blue = (mix(first, second) for first, second in zip(start.color, end.color))
    bands = tuple(
        (mix(band[0], end.color[0]), mix(band[1], end.color[1]), mix(band[2], end.color[2]))
        for band in start.bands
    )
    return LightCommand((red, green, blue), mix(start.brightness, end.brightness), bands)


class LightDirector:
    """Tracks the latest Key or Chord and works out the hold, fade and Resting Look."""

    def __init__(self, update_interval: float = DEFAULT_UPDATE_INTERVAL) -> None:
        self._update_interval = update_interval
        self._keys: set[int] = set()
        self._chord_started_at = 0.0
        self._pressed_at = 0.0
        self._sent_at: float | None = None
        self._last_command: LightCommand | None = None

    def press(self, key_index: int, now: float) -> None:
        """Record a Key press. Keys pressed within a moment of the first form a Chord."""
        if self._keys and now - self._chord_started_at <= CHORD_WINDOW_SECONDS:
            self._keys.add(key_index)
        else:
            self._keys = {key_index}
            self._chord_started_at = now
        self._pressed_at = now

    def _desired(self, now: float, config: PianoConfig) -> LightCommand:
        resting = LightCommand(config.resting_look.color, config.resting_look.brightness)
        colors = tuple(config.keys[key].color for key in sorted(self._keys) if key < len(config.keys))
        if not colors:
            self._keys.clear()
            return resting
        key_look = LightCommand(colors[0], config.key_brightness, colors if len(colors) > 1 else ())
        elapsed = now - self._pressed_at
        if elapsed < config.hold_seconds:
            return key_look
        fade_elapsed = elapsed - config.hold_seconds
        if fade_elapsed < config.fade_seconds:
            return _blend(key_look, resting, fade_elapsed / config.fade_seconds)
        self._keys.clear()
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
