"""Tests for moving between wifi networks, with a fake in place of nmcli."""
from pathlib import Path

import pytest

from christmas_piano.wifi import SETUP_CONNECTION, SETUP_SSID, WifiCommandError, WifiManager

PASSWORD = "setup-password"
HOME_ACTIVE = "home:802-11-wireless:wlan0:activated\n"
HOME_ACTIVATING = "home:802-11-wireless:wlan0:activating\n"
SETUP_ACTIVE = f"{SETUP_CONNECTION}:802-11-wireless:wlan0:activated\n"


class FakeNmcli:
    """Answers nmcli commands and records every call."""

    def __init__(self) -> None:
        self.active = ""
        self.scan = "Neighbors\nHome\\: Wifi\n"
        self.calls: list[tuple[list[str], str | None]] = []
        self.fail_up_of: str | None = None
        self.setup_broken = False
        self.scan_broken = False
        self.all_broken = False
        self.lose_psk = False
        self.saved_psk = ""

    def __call__(self, args: list[str], stdin: str | None = None) -> str:
        self.calls.append((args, stdin))
        if self.all_broken or (self.scan_broken and args[-2:] == ["wifi", "list"]):
            raise WifiCommandError("nmcli failed")
        if self.setup_broken and "up" in args and SETUP_CONNECTION in args:
            raise WifiCommandError("could not start")
        if "edit" in args and stdin and not self.lose_psk:
            self.saved_psk = stdin.split("\n")[0].split(" ", 2)[2]
        if "-s" in args:
            return f"{self.saved_psk}\n"
        if "--active" in args:
            return self.active
        if args[-3:-1] == ["device", "wifi"] or args[-2:] == ["wifi", "list"]:
            return self.scan
        if "up" in args:
            name = args[args.index("up") + 1]
            if name == self.fail_up_of:
                raise WifiCommandError("could not connect")
            if name == SETUP_CONNECTION:
                self.active = SETUP_ACTIVE
        if "down" in args:
            self.active = ""
        return ""

    def ran(self, *words: str) -> bool:
        return any(all(word in args for word in words) for args, _ in self.calls)

    def clear(self) -> None:
        self.calls = []


@pytest.fixture
def nmcli() -> FakeNmcli:
    return FakeNmcli()


@pytest.fixture
def manager(nmcli: FakeNmcli, tmp_path: Path) -> WifiManager:
    return WifiManager(nmcli, lambda: PASSWORD, tmp_path / "networks.json")


def offline_until_hotspot(manager: WifiManager) -> None:
    manager.step(0)
    manager.step(60)


def test_no_hotspot_before_60s(manager: WifiManager, nmcli: FakeNmcli) -> None:
    manager.step(0)
    manager.step(59)
    assert nmcli.active == ""


def test_hotspot_after_60s_offline(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    assert nmcli.active == SETUP_ACTIVE


def test_hotspot_uses_setup_name(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    assert nmcli.ran(SETUP_SSID)


def test_connected_resets_timer(manager: WifiManager, nmcli: FakeNmcli) -> None:
    manager.step(0)
    nmcli.active = HOME_ACTIVE
    manager.step(30)
    nmcli.active = ""
    manager.step(31)
    manager.step(90)
    assert nmcli.active == ""


def test_hotspot_retries_known_networks_every_300s(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    manager.step(359)
    assert nmcli.active == SETUP_ACTIVE
    manager.step(360)
    assert nmcli.active == ""


def test_hotspot_stays_down_if_known_network_returns(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    manager.step(360)
    nmcli.active = HOME_ACTIVE
    manager.step(370)
    manager.step(500)
    assert nmcli.active == HOME_ACTIVE


def test_hotspot_returns_if_retry_finds_nothing(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    manager.step(360)
    manager.step(370)
    assert nmcli.active == ""
    manager.step(380)
    assert nmcli.active == SETUP_ACTIVE


def test_connect_success_returns_true(manager: WifiManager, nmcli: FakeNmcli) -> None:
    assert manager.connect("Home", "homepassword") is True
    assert nmcli.ran("up", "Home")


def test_connect_failure_returns_false(manager: WifiManager, nmcli: FakeNmcli) -> None:
    nmcli.fail_up_of = "Home"
    assert manager.connect("Home", "homepassword") is False


def test_connect_failure_restores_hotspot(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    nmcli.fail_up_of = "Home"
    manager.connect("Home", "homepassword")
    assert nmcli.active == SETUP_ACTIVE


def test_connect_failure_removes_bad_profile(manager: WifiManager, nmcli: FakeNmcli) -> None:
    nmcli.fail_up_of = "Home"
    manager.connect("Home", "homepassword")
    commands = [args for args, _ in nmcli.calls]
    failed_at = next(index for index, args in enumerate(commands) if "up" in args and "Home" in args)
    assert any("delete" in args and "Home" in args for args in commands[failed_at:])


def test_password_with_newline_is_rejected(manager: WifiManager, nmcli: FakeNmcli) -> None:
    assert manager.connect("Home", "pass\nquit") is False
    assert nmcli.calls == [] or not any(stdin for _, stdin in nmcli.calls)


def test_passwords_never_appear_in_arguments(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    manager.connect("Home", "homepassword")
    arguments = " ".join(word for args, _ in nmcli.calls for word in args)
    assert PASSWORD not in arguments and "homepassword" not in arguments


def test_passwords_are_sent_on_stdin(manager: WifiManager, nmcli: FakeNmcli) -> None:
    manager.connect("Home", "homepassword")
    assert any(stdin and "homepassword" in stdin for _, stdin in nmcli.calls)


def test_open_network_sends_no_password(manager: WifiManager, nmcli: FakeNmcli) -> None:
    manager.connect("Cafe", "")
    assert not any(stdin for _, stdin in nmcli.calls)


def test_list_networks_handles_escaped_names(manager: WifiManager) -> None:
    assert manager.list_networks() == ["Home: Wifi", "Neighbors"]


def test_networks_cached_before_hotspot_starts(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    nmcli.scan = ""
    assert manager.list_networks() == ["Home: Wifi", "Neighbors"]


def test_activating_connection_is_not_online(manager: WifiManager, nmcli: FakeNmcli) -> None:
    nmcli.active = HOME_ACTIVATING
    manager.step(0)
    manager.step(60)
    assert nmcli.active == SETUP_ACTIVE


def test_autoconnect_is_turned_on_after_password_is_set(manager: WifiManager, nmcli: FakeNmcli) -> None:
    manager.connect("Home", "homepassword")
    commands = [args for args, _ in nmcli.calls]
    added = next(index for index, args in enumerate(commands) if "add" in args)
    edited = next(index for index, args in enumerate(commands) if "edit" in args)
    enabled = next(index for index, args in enumerate(commands) if "modify" in args)
    assert "no" in commands[added] and added < edited < enabled
    assert commands[enabled][-2:] == ["connection.autoconnect", "yes"]


def test_connect_fails_when_password_was_not_saved(manager: WifiManager, nmcli: FakeNmcli) -> None:
    nmcli.lose_psk = True
    assert manager.connect("Home", "homepassword") is False


def test_setup_password_not_saved_raises(manager: WifiManager, nmcli: FakeNmcli) -> None:
    nmcli.lose_psk = True
    with pytest.raises(WifiCommandError):
        manager.apply_setup_password()


def test_hotspot_uses_wpa2_aes(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    assert nmcli.ran("wifi-sec.proto", "rsn", "wifi-sec.pairwise", "ccmp", "wifi-sec.group")


def test_own_setup_network_hidden_from_list(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    nmcli.scan = f"{SETUP_SSID}\n"
    assert manager.list_networks() == ["Home: Wifi", "Neighbors"]


def test_list_uses_saved_networks_when_scan_fails(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    nmcli.scan_broken = True
    assert manager.list_networks() == ["Home: Wifi", "Neighbors"]


def test_list_is_empty_when_nothing_works(manager: WifiManager, nmcli: FakeNmcli) -> None:
    nmcli.all_broken = True
    assert manager.list_networks() == []


def test_connect_is_false_when_nmcli_is_broken(manager: WifiManager, nmcli: FakeNmcli) -> None:
    nmcli.all_broken = True
    assert manager.connect("Home", "homepassword") is False


def test_connect_is_false_when_hotspot_cannot_return(manager: WifiManager, nmcli: FakeNmcli) -> None:
    offline_until_hotspot(manager)
    nmcli.fail_up_of = "Home"
    nmcli.setup_broken = True
    assert manager.connect("Home", "homepassword") is False


def test_apply_setup_password_sends_on_stdin(manager: WifiManager, nmcli: FakeNmcli) -> None:
    manager.apply_setup_password()
    assert any(stdin and PASSWORD in stdin for _, stdin in nmcli.calls)
