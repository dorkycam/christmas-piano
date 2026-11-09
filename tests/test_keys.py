"""Tests for turning pin readings into Key presses."""
from christmas_piano.keys import KeyWatcher


def test_press_is_reported_once_while_held() -> None:
    pressed = {26: True}
    watcher = KeyWatcher([26], pressed.__getitem__)
    assert [watcher.poll(), watcher.poll(), watcher.poll()] == [[0], [], []]


def test_press_again_after_release() -> None:
    pressed = {26: True}
    watcher = KeyWatcher([26], pressed.__getitem__)
    watcher.poll()
    pressed[26] = False
    watcher.poll()
    pressed[26] = True
    assert watcher.poll() == [0]


def test_two_keys_in_one_poll() -> None:
    watcher = KeyWatcher([26, 17], {26: True, 17: True}.__getitem__)
    assert watcher.poll() == [0, 1]


def test_index_follows_configured_order() -> None:
    watcher = KeyWatcher([26, 17], {26: False, 17: True}.__getitem__)
    assert watcher.poll() == [1]
