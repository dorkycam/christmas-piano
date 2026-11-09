"""Tests for deciding what the lights should show at each moment."""
import dataclasses

from christmas_piano.config import KeyConfig, PianoConfig, RestingLook
from christmas_piano.light_director import LightCommand, LightDirector

RED = (255, 0, 0)
BLUE = (0, 0, 255)
RESTING = (0, 100, 0)
CONFIG = PianoConfig(
    keys=(KeyConfig(1, RED), KeyConfig(2, BLUE)),
    key_brightness=20,
    hold_seconds=10,
    fade_seconds=2,
    resting_look=RestingLook(RESTING, 40),
    light_ids=None,
    sound_pack="meow",
)
RED_COMMAND = LightCommand(RED, 20)
BLUE_COMMAND = LightCommand(BLUE, 20)
RESTING_COMMAND = LightCommand(RESTING, 40)


def started() -> LightDirector:
    """Return a director that showed the Resting Look before the test's first moment."""
    director = LightDirector()
    director.tick(-1, CONFIG)
    return director


def pressed(key: int, at: float) -> LightDirector:
    """Return a director showing a Key's color from the given time."""
    director = started()
    director.press(key, at)
    director.tick(at, CONFIG)
    return director


def test_first_tick_sends_resting() -> None:
    assert LightDirector().tick(0, CONFIG) == RESTING_COMMAND


def test_resting_is_only_sent_once() -> None:
    assert started().tick(5, CONFIG) is None


def test_press_sends_key_color() -> None:
    director = started()
    director.press(0, 1)
    assert director.tick(1, CONFIG) == RED_COMMAND


def test_latest_key_wins() -> None:
    director = started()
    director.press(0, 1)
    director.press(1, 1.2)
    assert director.tick(1.2, CONFIG) == BLUE_COMMAND


def test_rate_cap_delays_second_change() -> None:
    director = pressed(0, 1)
    director.press(1, 1.05)
    assert director.tick(1.05, CONFIG) is None


def test_capped_change_sends_when_allowed() -> None:
    director = pressed(0, 1)
    director.press(1, 1.05)
    director.tick(1.05, CONFIG)
    assert director.tick(1.11, CONFIG) == LightCommand(RED, 20, (RED, BLUE))


def test_holds_without_resending() -> None:
    assert pressed(0, 1).tick(6, CONFIG) is None


def test_press_restarts_hold() -> None:
    director = pressed(0, 0)
    director.press(0, 8)
    director.tick(8, CONFIG)
    assert director.tick(11, CONFIG) is None


def test_fade_midpoint_is_halfway() -> None:
    director = pressed(0, 0)
    assert director.tick(11, CONFIG) == LightCommand((128, 50, 0), 30)


def test_fade_respects_rate_cap() -> None:
    director = pressed(0, 0)
    director.tick(11, CONFIG)
    assert director.tick(11.05, CONFIG) is None


def test_fade_ends_exactly_on_resting() -> None:
    assert pressed(0, 0).tick(12, CONFIG) == RESTING_COMMAND


def test_fade_end_is_sent_once() -> None:
    director = pressed(0, 0)
    director.tick(12, CONFIG)
    assert director.tick(13, CONFIG) is None


def test_press_during_fade_returns_to_key_color() -> None:
    director = pressed(0, 0)
    director.tick(11, CONFIG)
    director.press(1, 11.5)
    assert director.tick(11.5, CONFIG) == BLUE_COMMAND


def test_zero_fade_jumps_to_resting() -> None:
    config = dataclasses.replace(CONFIG, fade_seconds=0)
    director = LightDirector()
    director.tick(-1, config)
    director.press(0, 0)
    director.tick(0, config)
    assert director.tick(10, config) == RESTING_COMMAND


def test_changed_resting_look_is_resent() -> None:
    director = started()
    config = dataclasses.replace(CONFIG, resting_look=RestingLook(BLUE, 10))
    assert director.tick(5, config) == LightCommand(BLUE, 10)


GREEN = (0, 255, 0)
THREE_KEYS = dataclasses.replace(CONFIG, keys=(KeyConfig(1, RED), KeyConfig(2, BLUE), KeyConfig(3, GREEN)))


def test_keys_pressed_together_make_bands() -> None:
    director = started()
    director.press(0, 1)
    director.press(1, 1.05)
    assert director.tick(1.05, CONFIG) == LightCommand(RED, 20, (RED, BLUE))


def test_three_keys_make_three_bands() -> None:
    director = started()
    for key in range(3):
        director.press(key, 1)
    assert director.tick(1, THREE_KEYS).bands == (RED, BLUE, GREEN)


def test_bands_follow_key_order_not_press_order() -> None:
    director = started()
    director.press(1, 1)
    director.press(0, 1.05)
    assert director.tick(1.05, CONFIG).bands == (RED, BLUE)


def test_single_key_has_no_bands() -> None:
    director = started()
    director.press(0, 1)
    assert director.tick(1, CONFIG).bands == ()


def test_same_key_twice_has_no_bands() -> None:
    director = started()
    director.press(0, 1)
    director.press(0, 1.05)
    assert director.tick(1.05, CONFIG) == RED_COMMAND


def test_presses_apart_do_not_make_bands() -> None:
    director = started()
    director.press(0, 1)
    director.press(1, 1.5)
    assert director.tick(1.5, CONFIG) == BLUE_COMMAND


def test_fast_run_does_not_pile_into_bands() -> None:
    director = started()
    director.press(0, 1)
    director.press(1, 1.1)
    director.press(2, 1.2)
    assert director.tick(1.2, THREE_KEYS) == LightCommand(GREEN, 20)


def test_removed_key_is_left_out_of_bands() -> None:
    director = started()
    director.press(0, 1)
    director.press(7, 1.05)
    assert director.tick(1.05, CONFIG) == RED_COMMAND


def test_bands_hold_until_timer_ends() -> None:
    director = started()
    director.press(0, 0)
    director.press(1, 0.05)
    director.tick(0.05, CONFIG)
    assert director.tick(9, CONFIG) is None


def test_bands_fade_toward_resting() -> None:
    director = started()
    director.press(0, 0)
    director.press(1, 0)
    director.tick(0, CONFIG)
    assert director.tick(11, CONFIG).bands == ((128, 50, 0), (0, 50, 128))


def test_bands_end_on_solid_resting() -> None:
    director = started()
    director.press(0, 0)
    director.press(1, 0)
    director.tick(0, CONFIG)
    assert director.tick(12, CONFIG) == RESTING_COMMAND


def test_key_removed_from_config_is_ignored() -> None:
    director = started()
    director.press(7, 1)
    assert director.tick(1, CONFIG) is None
