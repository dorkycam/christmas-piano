"""Tests for the Govee LAN client, using fake sockets in place of the network."""
import base64
import functools
import json
import operator
import socket

from christmas_piano.govee import GoveeClient, Light, band_masks, segment_packet


class FakeSocket:
    """Records what is sent and replays queued replies."""

    def __init__(self, replies: list[dict[str, object]] | None = None, send_error: bool = False) -> None:
        self.sent: list[tuple[dict[str, object], tuple[str, int]]] = []
        self.replies = list(replies or [])
        self.send_error = send_error

    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        if self.send_error:
            raise OSError("network is unreachable")
        self.sent.append((json.loads(data), address))
        return len(data)

    def settimeout(self, seconds: float) -> None:
        pass

    def recvfrom(self, size: int) -> tuple[bytes, tuple[str, int]]:
        if not self.replies:
            raise socket.timeout
        return json.dumps(self.replies.pop(0)).encode(), ("1.1.1.1", 4002)


def scan_reply(device: str, ip: str) -> dict[str, object]:
    return {"msg": {"cmd": "scan", "data": {"ip": ip, "device": device, "sku": "H805A"}}}


def status_reply(on: int) -> dict[str, object]:
    return {"msg": {"cmd": "devStatus", "data": {"onOff": on, "brightness": 20}}}


def client_with(replies: list[dict[str, object]] | None = None) -> tuple[GoveeClient, FakeSocket]:
    sender = FakeSocket()
    return GoveeClient(sender, FakeSocket(replies)), sender


def test_color_packet() -> None:
    client, sender = client_with()
    client.send_color("1.1.1.1", (1, 2, 3))
    expected = {"msg": {"cmd": "colorwc", "data": {"color": {"r": 1, "g": 2, "b": 3}, "colorTemInKelvin": 0}}}
    assert sender.sent == [(expected, ("1.1.1.1", 4003))]


def test_brightness_packet() -> None:
    client, sender = client_with()
    client.send_brightness("1.1.1.1", 20)
    assert sender.sent == [({"msg": {"cmd": "brightness", "data": {"value": 20}}}, ("1.1.1.1", 4003))]


def test_segment_packet_format() -> None:
    packet = base64.b64decode(segment_packet((1, 2, 3), 0x3333))
    assert packet[:7] == bytes([0x33, 0x05, 0x15, 0x01, 1, 2, 3])
    assert packet[12:14] == bytes([0x33, 0x33])
    assert len(packet) == 20


def test_segment_packet_checksum() -> None:
    packet = base64.b64decode(segment_packet((1, 2, 3), 0x3333))
    assert functools.reduce(operator.xor, packet[:-1]) == packet[-1]


def test_two_bands_match_candy_cane_layout() -> None:
    assert band_masks(2) == [0x3333, 0xCCCC]


def test_bands_cover_every_segment_once() -> None:
    masks = band_masks(3)
    assert functools.reduce(operator.or_, masks) == 0xFFFF
    assert sum(bin(mask).count("1") for mask in masks) == 16


def test_bands_go_out_in_one_datagram() -> None:
    client, sender = client_with()
    client.send_bands("1.1.1.1", [(1, 2, 3), (4, 5, 6)])
    expected = [segment_packet((1, 2, 3), 0x3333), segment_packet((4, 5, 6), 0xCCCC)]
    assert sender.sent == [({"msg": {"cmd": "ptReal", "data": {"command": expected}}}, ("1.1.1.1", 4003))]


def test_band_send_error_is_swallowed() -> None:
    GoveeClient(FakeSocket(send_error=True), FakeSocket()).send_bands("1.1.1.1", [(1, 2, 3)])


def test_send_error_is_swallowed() -> None:
    client = GoveeClient(FakeSocket(send_error=True), FakeSocket())
    client.send_color("1.1.1.1", (1, 2, 3))
    client.send_brightness("1.1.1.1", 20)


def test_discover_sends_scan_to_multicast() -> None:
    client, sender = client_with()
    client.discover(0.01)
    assert sender.sent == [({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}, ("239.255.255.250", 4001))]


def test_discover_parses_scan_reply() -> None:
    client, _ = client_with([scan_reply("AA", "1.1.1.1")])
    assert client.discover(0.01) == [Light("AA", "1.1.1.1", "H805A")]


def test_discover_removes_duplicates() -> None:
    client, _ = client_with([scan_reply("AA", "1.1.1.1"), scan_reply("AA", "1.1.1.1")])
    assert client.discover(0.01) == [Light("AA", "1.1.1.1", "H805A")]


def test_discover_ignores_malformed_replies() -> None:
    client, _ = client_with([{"msg": {"cmd": "scan", "data": {}}}, scan_reply("AA", "1.1.1.1")])
    assert client.discover(0.01) == [Light("AA", "1.1.1.1", "H805A")]


def test_discover_ignores_reply_claiming_another_address() -> None:
    client, _ = client_with([scan_reply("AA", "8.8.8.8")])
    assert client.discover(0.01) == []


def test_discover_survives_send_error() -> None:
    client = GoveeClient(FakeSocket(send_error=True), FakeSocket())
    assert client.discover(0.01) == []


def test_is_on_true() -> None:
    client, _ = client_with([status_reply(1)])
    assert client.is_on("1.1.1.1", 0.01) is True


def test_is_on_false() -> None:
    client, _ = client_with([status_reply(0)])
    assert client.is_on("1.1.1.1", 0.01) is False


def test_is_on_timeout_is_none() -> None:
    client, _ = client_with()
    assert client.is_on("1.1.1.1", 0.01) is None
