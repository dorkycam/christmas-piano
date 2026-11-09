"""Tests for sending light changes without ever holding up the Notes."""
import threading
import time
from collections.abc import Sequence

from christmas_piano.config import default_config
from christmas_piano.govee import Light
from christmas_piano.light_director import LightDirector
from christmas_piano.light_worker import LightWorker

LIGHT_A = Light("AA", "1.1.1.1", "H805A")
LIGHT_B = Light("BB", "1.1.1.2", "H805A")
START_TIME = 1000.0


class FakeRoster:
    def __init__(self, lights: list[Light]) -> None:
        self.lights = lights

    def targets(self, light_ids: tuple[str, ...] | None) -> list[Light]:
        return self.lights


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def send_color(self, ip: str, color: tuple[int, int, int]) -> None:
        self.calls.append(("color", ip, color))

    def send_brightness(self, ip: str, value: int) -> None:
        self.calls.append(("brightness", ip, value))

    def send_bands(self, ip: str, colors: Sequence[tuple[int, int, int]]) -> None:
        self.calls.append(("bands", ip, tuple(colors)))


class RaisingClient(FakeClient):
    def send_color(self, ip: str, color: tuple[int, int, int]) -> None:
        raise RuntimeError("unexpected")


class BlockingClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.sending = threading.Event()
        self.release = threading.Event()

    def send_color(self, ip: str, color: tuple[int, int, int]) -> None:
        self.sending.set()
        self.release.wait(2)


now = [START_TIME]


def worker_for(client: FakeClient, lights: list[Light]) -> LightWorker:
    now[0] = START_TIME
    return LightWorker(LightDirector(), FakeRoster(lights), client, default_config, clock=lambda: now[0])


def test_worker_sends_brightness_and_color_to_each_target() -> None:
    client = FakeClient()
    worker_for(client, [LIGHT_A, LIGHT_B]).step()
    resting = default_config().resting_look
    assert client.calls == [
        ("brightness", "1.1.1.1", resting.brightness),
        ("color", "1.1.1.1", resting.color),
        ("brightness", "1.1.1.2", resting.brightness),
        ("color", "1.1.1.2", resting.color),
    ]


def test_keys_together_send_bands_instead_of_one_color() -> None:
    client = FakeClient()
    worker = worker_for(client, [LIGHT_A])
    worker.step()
    client.calls.clear()
    now[0] += 1
    worker.press(0)
    worker.press(1)
    worker.step()
    colors = tuple(key.color for key in default_config().keys[:2])
    assert client.calls == [("brightness", "1.1.1.1", 20), ("bands", "1.1.1.1", colors)]


def test_worker_sends_nothing_without_targets() -> None:
    client = FakeClient()
    worker_for(client, []).step()
    assert client.calls == []


def test_light_found_after_startup_gets_the_resting_look() -> None:
    client = FakeClient()
    roster = FakeRoster([])
    worker = LightWorker(LightDirector(), roster, client, default_config, clock=lambda: START_TIME)
    worker.step()
    roster.lights = [LIGHT_A]
    worker.step()
    assert ("color", "1.1.1.1", default_config().resting_look.color) in client.calls


def test_worker_survives_client_exception() -> None:
    client = RaisingClient()
    worker = worker_for(client, [LIGHT_A])
    worker.step()
    worker.step()


def test_press_does_not_wait_on_slow_client() -> None:
    client = BlockingClient()
    worker = LightWorker(LightDirector(), FakeRoster([LIGHT_A]), client, default_config)
    worker.start()
    assert client.sending.wait(2)
    started = time.perf_counter()
    worker.press(0)
    elapsed = time.perf_counter() - started
    client.release.set()
    assert elapsed < 0.01
