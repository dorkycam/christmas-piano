"""The piano's config: one file on the Pi that the settings page edits and the piano follows."""
import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

RGB = tuple[int, int, int]

DEFAULT_DATA_DIR = Path("/var/lib/christmas-piano")
DEFAULT_PINS = (26, 17, 13, 22, 4, 5, 6, 27)
RAINBOW: tuple[RGB, ...] = (
    (255, 0, 0),
    (255, 127, 0),
    (255, 255, 0),
    (0, 255, 0),
    (0, 255, 255),
    (0, 0, 255),
    (75, 0, 130),
    (148, 0, 211),
)
WARM_WHITE: RGB = (255, 180, 107)
DEFAULT_BRIGHTNESS = 20
DEFAULT_HOLD_SECONDS = 10
DEFAULT_FADE_SECONDS = 2
DEFAULT_SOUND_PACK = "meow"
MAX_BRIGHTNESS = 100
MAX_COLOR_VALUE = 255


class ConfigError(ValueError):
    """Raised when config values are missing or out of range."""


@dataclass(frozen=True)
class KeyConfig:
    """One Key: the wiring pin it uses and the color it shows."""

    pin: int
    color: RGB


@dataclass(frozen=True)
class RestingLook:
    """What the lights return to when nobody has played for a while."""

    color: RGB
    brightness: int


@dataclass(frozen=True)
class PianoConfig:
    """Everything the owner can change. `light_ids` of None means every light found."""

    keys: tuple[KeyConfig, ...]
    key_brightness: int
    hold_seconds: float
    fade_seconds: float
    resting_look: RestingLook
    light_ids: tuple[str, ...] | None
    sound_pack: str


def data_dir() -> Path:
    """Return the directory holding the config, login and uploaded sounds."""
    return Path(os.environ.get("CHRISTMAS_PIANO_DATA", DEFAULT_DATA_DIR))


def default_config() -> PianoConfig:
    """Return the config used before the owner has changed anything."""
    return PianoConfig(
        keys=tuple(KeyConfig(pin, color) for pin, color in zip(DEFAULT_PINS, RAINBOW)),
        key_brightness=DEFAULT_BRIGHTNESS,
        hold_seconds=DEFAULT_HOLD_SECONDS,
        fade_seconds=DEFAULT_FADE_SECONDS,
        resting_look=RestingLook(WARM_WHITE, DEFAULT_BRIGHTNESS),
        light_ids=None,
        sound_pack=DEFAULT_SOUND_PACK,
    )


def _integer(value: object, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ConfigError(f"{label} must be a whole number from {low} to {high}")
    return value


def _seconds(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ConfigError(f"{label} must be zero or more seconds")
    return value


def _color(value: object, label: str) -> RGB:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ConfigError(f"{label} must have red, green and blue values")
    red, green, blue = (_integer(part, label, 0, MAX_COLOR_VALUE) for part in value)
    return (red, green, blue)


def _keys(value: object) -> tuple[KeyConfig, ...]:
    if not isinstance(value, list):
        raise ConfigError("keys must be a list")
    keys: list[KeyConfig] = []
    for item in value:
        if not isinstance(item, dict):
            raise ConfigError("each key needs a pin and a color")
        keys.append(KeyConfig(_integer(item.get("pin"), "pin", 0, 27), _color(item.get("color"), "key color")))
    pins = [key.pin for key in keys]
    if len(set(pins)) != len(pins):
        raise ConfigError("two keys cannot share a pin")
    return tuple(keys)


def _resting_look(value: object) -> RestingLook:
    if not isinstance(value, dict):
        raise ConfigError("resting_look needs a color and a brightness")
    return RestingLook(
        _color(value.get("color"), "resting color"),
        _integer(value.get("brightness"), "resting brightness", 0, MAX_BRIGHTNESS),
    )


def _light_ids(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError("light_ids must be a list of device IDs or null")
    return tuple(value)


def _sound_pack(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError("sound_pack must be a name")
    return value


def parse_config(raw: dict[str, object]) -> PianoConfig:
    """Build a config from decoded JSON, raising ConfigError if anything is invalid."""
    missing = {"keys", "key_brightness", "hold_seconds", "fade_seconds", "resting_look", "light_ids", "sound_pack"} - raw.keys()
    if missing:
        raise ConfigError(f"missing settings: {sorted(missing)}")
    return PianoConfig(
        keys=_keys(raw["keys"]),
        key_brightness=_integer(raw["key_brightness"], "key_brightness", 0, MAX_BRIGHTNESS),
        hold_seconds=_seconds(raw["hold_seconds"], "hold_seconds"),
        fade_seconds=_seconds(raw["fade_seconds"], "fade_seconds"),
        resting_look=_resting_look(raw["resting_look"]),
        light_ids=_light_ids(raw["light_ids"]),
        sound_pack=_sound_pack(raw["sound_pack"]),
    )


def config_to_dict(config: PianoConfig) -> dict[str, object]:
    """Return a config in the shape stored as JSON."""
    return {
        "keys": [{"pin": key.pin, "color": list(key.color)} for key in config.keys],
        "key_brightness": config.key_brightness,
        "hold_seconds": config.hold_seconds,
        "fade_seconds": config.fade_seconds,
        "resting_look": {"color": list(config.resting_look.color), "brightness": config.resting_look.brightness},
        "light_ids": None if config.light_ids is None else list(config.light_ids),
        "sound_pack": config.sound_pack,
    }


def load_config(path: Path) -> PianoConfig:
    """Read the config, using defaults if it is missing or damaged so the piano can still play."""
    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict):
            raise ConfigError("config must be a JSON object")
        return parse_config(raw)
    except FileNotFoundError:
        return default_config()
    except (OSError, ValueError) as error:
        logger.warning("Using default config because %s could not be read: %s", path, error)
        return default_config()


def save_config(path: Path, config: PianoConfig) -> None:
    """Replace the config in one step, so a reader never sees a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w") as temp_file:
            json.dump(config_to_dict(config), temp_file, indent=2)
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, path)
    except BaseException:
        os.unlink(temp_name)
        raise


class ConfigWatcher:
    """Keeps the latest config, re-reading the file only when it changes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._stamp: int | None = None
        self._config = load_config(path)
        self._stamp = self._read_stamp()

    def _read_stamp(self) -> int | None:
        try:
            return self._path.stat().st_mtime_ns
        except OSError:
            return None

    def current(self) -> PianoConfig:
        """Return the latest config."""
        stamp = self._read_stamp()
        if stamp != self._stamp:
            self._stamp = stamp
            self._config = load_config(self._path)
        return self._config
