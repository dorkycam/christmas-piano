"""Creates, changes and backs up the Sound Packs stored on the Pi."""
import os
import re
import shutil
import subprocess
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MAX_KEY_NUMBER = 8
CONVERT_TIMEOUT_SECONDS = 30
VALID_PACK_NAME = re.compile(r"[a-z0-9][a-z0-9 _-]{0,39}")


class InvalidSound(ValueError):
    """Raised when an upload cannot be turned into a Note."""


class InvalidPack(ValueError):
    """Raised for a bad pack name, a missing pack or a forbidden change."""


@dataclass(frozen=True)
class PackInfo:
    """A Sound Pack and the Key numbers that have Notes."""

    name: str
    notes: frozenset[int]


def ffmpeg_convert(source: Path, destination: Path) -> None:
    """Convert an upload to the WAV format the piano plays."""
    command = ["ffmpeg", "-y", "-i", str(source), "-ac", "1", "-ar", "44100", "-sample_fmt", "s16", "-f", "wav", str(destination)]
    try:
        subprocess.run(command, capture_output=True, check=True, timeout=CONVERT_TIMEOUT_SECONDS)
    except (subprocess.SubprocessError, OSError) as error:
        raise InvalidSound("That file could not be read as audio.") from error


class PackStore:
    """The folder of Sound Packs."""

    def __init__(self, root: Path, convert: Callable[[Path, Path], None] = ffmpeg_convert) -> None:
        self._root = root
        self._convert = convert

    def _path(self, name: str) -> Path:
        if not VALID_PACK_NAME.fullmatch(name):
            raise InvalidPack("Pack names can use lowercase letters, numbers, spaces, - and _.")
        return self._root / name

    def _existing_path(self, name: str) -> Path:
        path = self._path(name)
        if not path.is_dir():
            raise InvalidPack(f"There is no pack called {name}.")
        return path

    def list_packs(self) -> list[PackInfo]:
        """Return every pack in name order."""
        if not self._root.is_dir():
            return []
        return [
            PackInfo(
                path.name,
                frozenset(n for n in range(1, MAX_KEY_NUMBER + 1) if (path / f"note{n}.wav").is_file()),
            )
            for path in sorted(self._root.iterdir())
            if path.is_dir()
        ]

    def create(self, name: str) -> None:
        """Create an empty pack."""
        path = self._path(name)
        if path.exists():
            raise InvalidPack(f"There is already a pack called {name}.")
        path.mkdir(parents=True)

    def delete(self, name: str, active: str) -> None:
        """Delete a pack, unless it is the one playing."""
        path = self._existing_path(name)
        if name == active:
            raise InvalidPack("The pack that is playing cannot be deleted.")
        shutil.rmtree(path)

    def replace_note(self, name: str, key_number: int, upload: Path) -> None:
        """Convert an upload and make it a Key's Note. The old Note survives any failure."""
        path = self._existing_path(name)
        if not 1 <= key_number <= MAX_KEY_NUMBER:
            raise InvalidPack(f"Key numbers go from 1 to {MAX_KEY_NUMBER}.")
        temp_path = path / f".note{key_number}.converting"
        try:
            self._convert(upload, temp_path)
            os.replace(temp_path, path / f"note{key_number}.wav")
        finally:
            temp_path.unlink(missing_ok=True)

    def export_zip(self, destination: Path) -> None:
        """Write every pack to one zip file."""
        with zipfile.ZipFile(destination, "w") as archive:
            for path in sorted(self._root.rglob("*.wav")):
                archive.write(path, path.relative_to(self._root).as_posix())
