"""Moves the Pi between wifi networks with NetworkManager, using a setup network when lost."""
import json
import logging
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

SETUP_SSID = "Christmas Piano Setup"
SETUP_ADDRESS = "10.42.0.1"
SETUP_CONNECTION = "christmas-piano-setup"
WIFI_INTERFACE = "wlan0"
OFFLINE_SECONDS_BEFORE_SETUP = 60
SECONDS_BETWEEN_RETRIES = 300
RETRY_WINDOW_SECONDS = 20
COMMAND_TIMEOUT_SECONDS = 45
ONLINE_CONNECTION_TYPES = {"802-11-wireless", "802-3-ethernet"}
ACTIVATED = "activated"
FIELD_SEPARATOR = re.compile(r"(?<!\\):")



class CommandRunner(Protocol):
    """Runs a command and returns its output."""

    def __call__(self, args: list[str], stdin: str | None = None, /) -> str: ...


class WifiCommandError(RuntimeError):
    """Raised when a NetworkManager command fails."""


def run_command(args: list[str], stdin: str | None = None) -> str:
    """Run a command, sending any secrets on stdin rather than in its arguments."""
    try:
        result = subprocess.run(args, input=stdin, capture_output=True, text=True, check=True, timeout=COMMAND_TIMEOUT_SECONDS)
    except (subprocess.SubprocessError, OSError) as error:
        raise WifiCommandError(f"{args[0]} {args[1] if len(args) > 1 else ''} failed") from error
    return result.stdout


def _unescape(field: str) -> str:
    return field.replace("\\:", ":").replace("\\\\", "\\")


class WifiManager:
    """Decides when to show the setup network. State comes from NetworkManager itself."""

    def __init__(self, run: CommandRunner, get_password: Callable[[], str], cache_path: Path) -> None:
        self._run = run
        self._get_password = get_password
        self._cache_path = cache_path
        self._offline_since: float | None = None
        self._hotspot_since: float | None = None
        self._retry_until: float | None = None

    def _active(self) -> list[tuple[str, str, str]]:
        """Return the name, type and state of each active connection."""
        output = self._run(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE,STATE", "connection", "show", "--active"])
        connections: list[tuple[str, str, str]] = []
        for line in output.splitlines():
            fields = FIELD_SEPARATOR.split(line)
            if len(fields) >= 4:
                connections.append((_unescape(fields[0]), fields[1], fields[3]))
        return connections

    def _hotspot_active(self) -> bool:
        return any(name == SETUP_CONNECTION for name, _, _ in self._active())

    def _set_psk(self, connection: str, password: str) -> None:
        commands = f"set 802-11-wireless-security.psk {password}\nsave persistent\nquit\n"
        self._run(["nmcli", "connection", "edit", connection], commands)
        stored = self._run(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", connection])
        if _unescape(stored.rstrip("\n")) != password:
            raise WifiCommandError("the wifi password was not saved")

    def _quietly(self, args: list[str]) -> None:
        try:
            self._run(args)
        except WifiCommandError:
            pass

    def _bring_down_setup(self) -> None:
        self._quietly(["nmcli", "connection", "down", SETUP_CONNECTION])

    def _scan(self) -> list[str]:
        output = self._run(["nmcli", "-t", "-f", "SSID", "device", "wifi", "list"])
        return sorted({_unescape(line) for line in output.splitlines() if line} - {SETUP_SSID})

    def _start_hotspot(self, now: float | None) -> None:
        self._cache_path.write_text(json.dumps(self._scan()))
        self._quietly(["nmcli", "connection", "delete", SETUP_CONNECTION])
        self._run(
            [
                "nmcli", "connection", "add", "type", "wifi", "ifname", WIFI_INTERFACE,
                "con-name", SETUP_CONNECTION, "autoconnect", "no", "ssid", SETUP_SSID,
                "mode", "ap", "ipv4.method", "shared", "ipv4.addresses", f"{SETUP_ADDRESS}/24",
                "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.proto", "rsn",
                "wifi-sec.pairwise", "ccmp", "wifi-sec.group", "ccmp",
            ]
        )
        self._set_psk(SETUP_CONNECTION, self._get_password())
        self._run(["nmcli", "connection", "up", SETUP_CONNECTION])
        self._hotspot_since = now
        self._offline_since = None

    def step(self, now: float) -> None:
        """Look at the current connection and act. Call this every few seconds."""
        active = self._active()
        hotspot_active = any(name == SETUP_CONNECTION for name, _, _ in active)
        online = any(
            name != SETUP_CONNECTION and kind in ONLINE_CONNECTION_TYPES and state == ACTIVATED
            for name, kind, state in active
        )
        if online:
            self._offline_since = None
            self._retry_until = None
            if hotspot_active:
                self._bring_down_setup()
            return
        if hotspot_active:
            self._retry_when_due(now)
            return
        if self._retry_until is not None:
            if now >= self._retry_until:
                self._retry_until = None
                self._start_hotspot(now)
            return
        if self._offline_since is None:
            self._offline_since = now
        if now - self._offline_since >= OFFLINE_SECONDS_BEFORE_SETUP:
            self._start_hotspot(now)

    def _retry_when_due(self, now: float) -> None:
        if self._hotspot_since is None:
            self._hotspot_since = now
        if now - self._hotspot_since >= SECONDS_BETWEEN_RETRIES:
            self._bring_down_setup()
            self._hotspot_since = None
            self._retry_until = now + RETRY_WINDOW_SECONDS

    def list_networks(self) -> list[str]:
        """Return nearby networks, using the list saved before the setup network started."""
        try:
            networks = self._scan()
        except WifiCommandError:
            networks = []
        if networks:
            return networks
        try:
            return json.loads(self._cache_path.read_text())
        except (OSError, ValueError):
            return []

    def connect(self, ssid: str, password: str) -> bool:
        """Join a network and remember it. Returns False and restores the setup network on failure."""
        if "\n" in password or "\r" in password:
            return False
        hotspot_was_active = False
        try:
            hotspot_was_active = self._hotspot_active()
            if hotspot_was_active:
                self._bring_down_setup()
            self._quietly(["nmcli", "connection", "delete", ssid])
            add = [
                "nmcli", "connection", "add", "type", "wifi", "ifname", WIFI_INTERFACE,
                "con-name", ssid, "autoconnect", "no", "ssid", ssid,
            ]
            if password:
                self._run([*add, "wifi-sec.key-mgmt", "wpa-psk"])
                self._set_psk(ssid, password)
            else:
                self._run(add)
            self._run(["nmcli", "connection", "modify", ssid, "connection.autoconnect", "yes"])
            self._run(["nmcli", "--wait", "30", "connection", "up", ssid])
        except WifiCommandError:
            self._quietly(["nmcli", "connection", "delete", ssid])
            if hotspot_was_active:
                self._restore_hotspot()
            return False
        return True

    def _restore_hotspot(self) -> None:
        try:
            self._start_hotspot(None)
        except (WifiCommandError, OSError) as error:
            logger.warning("Could not restore the setup network: %s", error)

    def apply_setup_password(self) -> None:
        """Update the setup network after the password changes."""
        self._set_psk(SETUP_CONNECTION, self._get_password())
