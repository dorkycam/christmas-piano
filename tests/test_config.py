"""Tests for the piano config."""
import dataclasses
import os
from pathlib import Path

import pytest

from christmas_piano.config import (
    ConfigError,
    ConfigWatcher,
    config_to_dict,
    data_dir,
    default_config,
    load_config,
    parse_config,
    save_config,
)


def test_default_pins_match_piano_wiring() -> None:
    assert [key.pin for key in default_config().keys] == [26, 17, 13, 22, 4, 5, 6, 27]


def test_default_colors_are_a_rainbow_from_red_to_violet() -> None:
    keys = default_config().keys
    assert keys[0].color == (255, 0, 0)
    assert keys[7].color == (148, 0, 211)


def test_default_timing_and_brightness() -> None:
    config = default_config()
    assert (config.hold_seconds, config.fade_seconds, config.key_brightness) == (10, 2, 20)


def test_default_resting_look_is_dim_warm_white() -> None:
    resting = default_config().resting_look
    assert (resting.color, resting.brightness) == ((255, 180, 107), 20)


def test_defaults_use_every_light_and_meow() -> None:
    config = default_config()
    assert config.light_ids is None
    assert config.sound_pack == "meow"


def test_round_trip() -> None:
    assert parse_config(config_to_dict(default_config())) == default_config()


def test_round_trip_keeps_chosen_lights() -> None:
    config = dataclasses.replace(default_config(), light_ids=("AA", "BB"))
    assert parse_config(config_to_dict(config)).light_ids == ("AA", "BB")


@pytest.mark.parametrize(
    "change",
    [
        {"key_brightness": 101},
        {"key_brightness": -1},
        {"hold_seconds": -1},
        {"fade_seconds": -0.5},
        {"hold_seconds": float("nan")},
        {"fade_seconds": float("inf")},
        {"sound_pack": ""},
        {"key_brightness": "bright"},
    ],
)
def test_rejects_invalid_values(change: dict[str, object]) -> None:
    raw = {**config_to_dict(default_config()), **change}
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_rejects_duplicate_pins() -> None:
    raw = config_to_dict(default_config())
    raw["keys"] = [{"pin": 4, "color": [1, 2, 3]}, {"pin": 4, "color": [1, 2, 3]}]
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_rejects_out_of_range_color() -> None:
    raw = config_to_dict(default_config())
    raw["keys"] = [{"pin": 4, "color": [256, 0, 0]}]
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_rejects_missing_field() -> None:
    raw = config_to_dict(default_config())
    del raw["hold_seconds"]
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_missing_file_loads_defaults(tmp_path: Path) -> None:
    assert load_config(tmp_path / "config.json") == default_config()


def test_corrupt_file_loads_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"hold_seconds": ')
    assert load_config(path) == default_config()


def test_invalid_file_loads_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"hold_seconds": 3}')
    assert load_config(path) == default_config()


def test_save_then_load(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = dataclasses.replace(default_config(), hold_seconds=4)
    save_config(path, config)
    assert load_config(path) == config


def test_save_leaves_no_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    save_config(path, default_config())
    assert [item.name for item in tmp_path.iterdir()] == ["config.json"]


def test_watcher_sees_change(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    save_config(path, default_config())
    watcher = ConfigWatcher(path)
    assert watcher.current().hold_seconds == 10
    save_config(path, dataclasses.replace(default_config(), hold_seconds=3))
    os.utime(path, (1, 1))
    assert watcher.current().hold_seconds == 3


def test_watcher_handles_deleted_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    save_config(path, dataclasses.replace(default_config(), hold_seconds=3))
    watcher = ConfigWatcher(path)
    watcher.current()
    path.unlink()
    assert watcher.current() == default_config()


def test_data_dir_uses_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHRISTMAS_PIANO_DATA", str(tmp_path))
    assert data_dir() == tmp_path


def test_data_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHRISTMAS_PIANO_DATA", raising=False)
    assert data_dir() == Path("/var/lib/christmas-piano")
