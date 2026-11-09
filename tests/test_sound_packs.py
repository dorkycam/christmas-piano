"""Tests for managing Sound Packs."""
import shutil
import zipfile
from pathlib import Path

import pytest

from christmas_piano.sound_packs import InvalidPack, InvalidSound, PackInfo, PackStore, ffmpeg_convert

REPO_NOTE = Path(__file__).parent.parent / "sounds" / "random" / "note1.wav"


def copy_convert(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)


def failing_convert(source: Path, destination: Path) -> None:
    raise InvalidSound("not audio")


@pytest.fixture
def store(tmp_path: Path) -> PackStore:
    return PackStore(tmp_path / "sounds", copy_convert)


@pytest.fixture
def upload(tmp_path: Path) -> Path:
    path = tmp_path / "upload.mp3"
    path.write_bytes(b"new sound")
    return path


def test_create_and_list(store: PackStore) -> None:
    store.create("carols")
    assert store.list_packs() == [PackInfo("carols", frozenset())]


def test_packs_are_sorted(store: PackStore) -> None:
    store.create("zebra")
    store.create("carols")
    assert [pack.name for pack in store.list_packs()] == ["carols", "zebra"]


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".hidden", "..", "A" * 41])
def test_rejects_unsafe_names(store: PackStore, bad: str) -> None:
    with pytest.raises(InvalidPack):
        store.create(bad)


def test_creating_existing_pack_is_rejected(store: PackStore) -> None:
    store.create("carols")
    with pytest.raises(InvalidPack):
        store.create("carols")


def test_cannot_delete_active(store: PackStore) -> None:
    store.create("carols")
    with pytest.raises(InvalidPack):
        store.delete("carols", active="carols")


def test_delete_removes_pack(store: PackStore) -> None:
    store.create("carols")
    store.delete("carols", active="meow")
    assert store.list_packs() == []


def test_delete_with_unsafe_name_is_rejected(store: PackStore) -> None:
    with pytest.raises(InvalidPack):
        store.delete("../outside", active="meow")


def test_replace_note_becomes_note_n(store: PackStore, upload: Path, tmp_path: Path) -> None:
    store.create("carols")
    store.replace_note("carols", 3, upload)
    assert (tmp_path / "sounds" / "carols" / "note3.wav").read_bytes() == b"new sound"


def test_list_shows_which_notes_exist(store: PackStore, upload: Path) -> None:
    store.create("carols")
    store.replace_note("carols", 3, upload)
    assert store.list_packs() == [PackInfo("carols", frozenset({3}))]


def test_failed_conversion_keeps_old_note(tmp_path: Path, upload: Path) -> None:
    PackStore(tmp_path / "sounds", copy_convert).create("carols")
    note = tmp_path / "sounds" / "carols" / "note1.wav"
    note.write_bytes(b"old")
    with pytest.raises(InvalidSound):
        PackStore(tmp_path / "sounds", failing_convert).replace_note("carols", 1, upload)
    assert note.read_bytes() == b"old"


def test_failed_conversion_leaves_no_temp_files(tmp_path: Path, upload: Path) -> None:
    PackStore(tmp_path / "sounds", copy_convert).create("carols")
    with pytest.raises(InvalidSound):
        PackStore(tmp_path / "sounds", failing_convert).replace_note("carols", 1, upload)
    assert list((tmp_path / "sounds" / "carols").iterdir()) == []


@pytest.mark.parametrize("number", [0, 9])
def test_rejects_key_number_out_of_range(store: PackStore, upload: Path, number: int) -> None:
    store.create("carols")
    with pytest.raises(InvalidPack):
        store.replace_note("carols", number, upload)


def test_replace_note_in_missing_pack_is_rejected(store: PackStore, upload: Path) -> None:
    with pytest.raises(InvalidPack):
        store.replace_note("carols", 1, upload)


def test_export_zip_contains_all_packs(store: PackStore, upload: Path, tmp_path: Path) -> None:
    store.create("carols")
    store.replace_note("carols", 1, upload)
    destination = tmp_path / "backup.zip"
    store.export_zip(destination)
    assert zipfile.ZipFile(destination).namelist() == ["carols/note1.wav"]


def test_ffmpeg_accepts_real_audio(tmp_path: Path) -> None:
    destination = tmp_path / "out.wav"
    ffmpeg_convert(REPO_NOTE, destination)
    assert destination.read_bytes()[:4] == b"RIFF"


def test_ffmpeg_rejects_non_audio(tmp_path: Path) -> None:
    source = tmp_path / "fake.mp3"
    source.write_text("this is not audio")
    with pytest.raises(InvalidSound):
        ffmpeg_convert(source, tmp_path / "out.wav")
