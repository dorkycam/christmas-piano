"""Talks to Govee lights with their local network protocol (see docs/adr/0001)."""
import json
import logging
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from christmas_piano.config import RGB

logger = logging.getLogger(__name__)

MULTICAST_ADDRESS = "239.255.255.250"
SCAN_PORT = 4001
REPLY_PORT = 4002
COMMAND_PORT = 4003
MAX_PACKET_BYTES = 4096


class DatagramSocket(Protocol):
    """The parts of a UDP socket the client uses."""

    def sendto(self, data: bytes, address: tuple[str, int], /) -> int: ...

    def settimeout(self, seconds: float, /) -> None: ...

    def recvfrom(self, size: int, /) -> tuple[bytes, tuple[str, int]]: ...


@dataclass(frozen=True)
class Light:
    """A Govee light found on the network."""

    device_id: str
    ip: str
    sku: str


class GoveeClient:
    """Sends commands to lights. Network errors are logged and never raised."""

    def __init__(self, send_socket: DatagramSocket, receive_socket: DatagramSocket) -> None:
        self._send_socket = send_socket
        self._receive_socket = receive_socket

    def _send(self, command: str, data: dict[str, object], address: tuple[str, int]) -> None:
        payload = json.dumps({"msg": {"cmd": command, "data": data}}).encode()
        try:
            self._send_socket.sendto(payload, address)
        except OSError as error:
            logger.debug("Could not send %s to %s: %s", command, address, error)

    def send_color(self, ip: str, color: RGB) -> None:
        """Set a light's color."""
        red, green, blue = color
        data = {"color": {"r": red, "g": green, "b": blue}, "colorTemInKelvin": 0}
        self._send("colorwc", data, (ip, COMMAND_PORT))

    def send_brightness(self, ip: str, value: int) -> None:
        """Set a light's brightness from 0 to 100."""
        self._send("brightness", {"value": value}, (ip, COMMAND_PORT))

    def _replies(self, seconds: float) -> Iterator[tuple[dict[str, object], str]]:
        """Yield decoded replies until the time runs out."""
        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                self._receive_socket.settimeout(remaining)
                payload, (source, _) = self._receive_socket.recvfrom(MAX_PACKET_BYTES)
            except OSError:  # includes socket.timeout
                break
            try:
                message = json.loads(payload)["msg"]
            except (ValueError, KeyError, TypeError):
                continue
            if isinstance(message, dict):
                yield message, source

    def discover(self, seconds: float) -> list[Light]:
        """Ask the network which lights exist. Only lights with LAN Control turned on answer."""
        self._send("scan", {"account_topic": "reserve"}, (MULTICAST_ADDRESS, SCAN_PORT))
        lights: dict[str, Light] = {}
        for message, _ in self._replies(seconds):
            data = message.get("data")
            if message.get("cmd") != "scan" or not isinstance(data, dict):
                continue
            device_id, ip, sku = data.get("device"), data.get("ip"), data.get("sku")
            if isinstance(device_id, str) and isinstance(ip, str) and isinstance(sku, str):
                lights[device_id] = Light(device_id, ip, sku)
        return list(lights.values())

    def is_on(self, ip: str, seconds: float) -> bool | None:
        """Return whether a light is on, or None if it did not answer in time."""
        self._send("devStatus", {}, (ip, COMMAND_PORT))
        for message, source in self._replies(seconds):
            data = message.get("data")
            if source == ip and message.get("cmd") == "devStatus" and isinstance(data, dict):
                return data.get("onOff") == 1
        return None


def open_client() -> GoveeClient:
    """Create a client on real sockets. Only one client per machine can listen for replies."""
    receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receive_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    receive_socket.bind(("", REPLY_PORT))
    return GoveeClient(socket.socket(socket.AF_INET, socket.SOCK_DGRAM), receive_socket)
