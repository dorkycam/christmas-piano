"""Tests for playing Notes from a Sound Pack."""
import os
from pathlib import Path

import pytest

from christmas_piano.audio import SoundBoard, pack_stamp


class FakeSound:
    """Records each time it is played."""

    def __init__(self, path: Path, played: list[str]) -> None:
        self.path = path
        self.played = played

    def play(self) -> None:
        self.played.append(self.path.name)


def pack_with(directory: Path, *numbers: int) -> Path:
    for number in numbers:
        (directory / f"note{number}.wav").write_bytes(b"sound")
    return directory


@pytest.fixture
def played() -> list[str]:
    return []


@pytest.fixture
def board(played: list[str]) -> SoundBoard:
    return SoundBoard(lambda path: FakeSound(path, played))


def test_note_n_belongs_to_key_n(board: SoundBoard, played: list[str], tmp_path: Path) -> None:
    board.load_pack(pack_with(tmp_path, 1, 2, 3), 3)
    board.play(2)
    assert played == ["note3.wav"]


def test_missing_note_is_silent(board: SoundBoard, played: list[str], tmp_path: Path) -> None:
    board.load_pack(pack_with(tmp_path, 1), 2)
    board.play(1)
    assert played == []


def test_other_keys_work_when_one_note_is_missing(board: SoundBoard, played: list[str], tmp_path: Path) -> None:
    board.load_pack(pack_with(tmp_path, 1), 2)
    board.play(0)
    assert played == ["note1.wav"]


def test_unreadable_note_is_silent(played: list[str], tmp_path: Path) -> None:
    def load(path: Path) -> FakeSound:
        if path.name == "note1.wav":
            raise RuntimeError("not a sound file")
        return FakeSound(path, played)

    board = SoundBoard(load)
    board.load_pack(pack_with(tmp_path, 1, 2), 2)
    board.play(0)
    board.play(1)
    assert played == ["note2.wav"]


def test_missing_pack_is_silent(board: SoundBoard, played: list[str], tmp_path: Path) -> None:
    board.load_pack(tmp_path / "gone", 2)
    board.play(0)
    assert played == []


def test_key_beyond_pack_is_silent(board: SoundBoard, played: list[str], tmp_path: Path) -> None:
    board.load_pack(pack_with(tmp_path, 1), 1)
    board.play(5)
    assert played == []


def test_pack_stamp_changes_when_a_note_is_replaced(tmp_path: Path) -> None:
    pack_with(tmp_path, 1)
    before = pack_stamp(tmp_path)
    (tmp_path / "upload.tmp").write_bytes(b"new")
    os.utime(tmp_path, (1, 1))
    assert pack_stamp(tmp_path) != before


def test_pack_stamp_of_missing_pack_is_none(tmp_path: Path) -> None:
    assert pack_stamp(tmp_path / "gone") is None


def test_loading_new_pack_replaces_old(board: SoundBoard, played: list[str], tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    board.load_pack(pack_with(first, 1), 1)
    board.load_pack(second, 1)
    board.play(0)
    assert played == []
