"""Loads a Sound Pack and plays its Notes."""
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

MIXER_CHANNELS = 16
MIXER_RATE = 44100
MIXER_BUFFER = 512


class Playable(Protocol):
    """A loaded Note."""

    def play(self) -> object: ...


def pack_stamp(directory: Path) -> int | None:
    """Return a value that changes when a pack's Notes change, or None if the pack is gone."""
    try:
        return directory.stat().st_mtime_ns
    except OSError:
        return None


class SoundBoard:
    """Holds the active Notes. A Note that cannot be loaded leaves its Key silent."""

    def __init__(self, load_sound: Callable[[Path], Playable]) -> None:
        self._load_sound = load_sound
        self._notes: dict[int, Playable] = {}

    def load_pack(self, directory: Path, key_count: int) -> None:
        """Load `note1.wav` onward, replacing the current Notes."""
        notes: dict[int, Playable] = {}
        for key_index in range(key_count):
            path = directory / f"note{key_index + 1}.wav"
            if not path.is_file():
                logger.warning("No Note at %s", path)
                continue
            try:
                notes[key_index] = self._load_sound(path)
            except (OSError, RuntimeError, ValueError) as error:
                logger.warning("Could not load %s: %s", path, error)
        self._notes = notes

    def play(self, key_index: int) -> None:
        """Play a Key's Note, if it has one."""
        note = self._notes.get(key_index)
        if note is not None:
            note.play()


def open_pygame_loader() -> Callable[[Path], Playable]:
    """Start the audio mixer and return a function that loads Notes into it."""
    import pygame

    pygame.mixer.pre_init(MIXER_RATE, -16, 2, MIXER_BUFFER)
    pygame.mixer.init()
    pygame.mixer.set_num_channels(MIXER_CHANNELS)

    def load(path: Path) -> Playable:
        return pygame.mixer.Sound(str(path))

    return load
