"""Tests for tracking which lights exist and which are on."""
import json
from pathlib import Path

from christmas_piano.govee import Light
from christmas_piano.light_roster import LightRoster, consume_rescan_request

LIGHT_A = Light("AA", "1.1.1.1", "H805A")
LIGHT_B = Light("BB", "1.1.1.2", "H805A")


class FakeClient:
    """Answers discovery and on/off questions from fixed data."""

    def __init__(self, lights: list[Light], states: dict[str, bool | None]) -> None:
        self.lights = lights
        self.states = states

    def discover(self, seconds: float) -> list[Light]:
        return self.lights

    def is_on(self, ip: str, seconds: float) -> bool | None:
        return self.states[ip]


def refreshed(states: dict[str, bool | None], path: Path, lights: list[Light] | None = None) -> LightRoster:
    roster = LightRoster(FakeClient([LIGHT_A, LIGHT_B] if lights is None else lights, states), path)
    roster.refresh()
    return roster


def test_targets_include_lights_that_are_on(tmp_path: Path) -> None:
    roster = refreshed({"1.1.1.1": True, "1.1.1.2": True}, tmp_path / "lights.json")
    assert roster.targets(None) == [LIGHT_A, LIGHT_B]


def test_targets_exclude_off_lights(tmp_path: Path) -> None:
    roster = refreshed({"1.1.1.1": False, "1.1.1.2": True}, tmp_path / "lights.json")
    assert roster.targets(None) == [LIGHT_B]


def test_targets_exclude_unknown_state(tmp_path: Path) -> None:
    roster = refreshed({"1.1.1.1": None, "1.1.1.2": True}, tmp_path / "lights.json")
    assert roster.targets(None) == [LIGHT_B]


def test_targets_filter_by_id(tmp_path: Path) -> None:
    roster = refreshed({"1.1.1.1": True, "1.1.1.2": True}, tmp_path / "lights.json")
    assert roster.targets(("AA",)) == [LIGHT_A]


def test_targets_empty_before_refresh(tmp_path: Path) -> None:
    roster = LightRoster(FakeClient([LIGHT_A], {"1.1.1.1": True}), tmp_path / "lights.json")
    assert roster.targets(None) == []


def test_refresh_writes_state(tmp_path: Path) -> None:
    path = tmp_path / "lights.json"
    refreshed({"1.1.1.1": True, "1.1.1.2": False}, path)
    assert json.loads(path.read_text()) == [
        {"device_id": "AA", "ip": "1.1.1.1", "sku": "H805A", "on": True},
        {"device_id": "BB", "ip": "1.1.1.2", "sku": "H805A", "on": False},
    ]


def test_rescan_request_is_consumed(tmp_path: Path) -> None:
    path = tmp_path / "rescan"
    path.touch()
    assert consume_rescan_request(path) is True
    assert not path.exists()


def test_no_rescan_request(tmp_path: Path) -> None:
    assert consume_rescan_request(tmp_path / "rescan") is False


def test_light_gone_from_network_is_removed(tmp_path: Path) -> None:
    client = FakeClient([LIGHT_A], {"1.1.1.1": True})
    roster = LightRoster(client, tmp_path / "lights.json")
    roster.refresh()
    client.lights = []
    roster.refresh()
    assert roster.targets(None) == []
