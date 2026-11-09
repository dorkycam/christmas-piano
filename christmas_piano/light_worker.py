"""Sends light changes on its own thread, so the Notes never wait for the network."""
import logging
import threading
import time
from collections.abc import Callable
from typing import Protocol

from christmas_piano.config import RGB, PianoConfig
from christmas_piano.govee import Light
from christmas_piano.light_director import LightDirector

logger = logging.getLogger(__name__)

STEP_SECONDS = 0.02


class TargetSource(Protocol):
    """Answers which lights should change."""

    def targets(self, light_ids: tuple[str, ...] | None) -> list[Light]: ...


class LightSender(Protocol):
    """Sends looks to a light."""

    def send_color(self, ip: str, color: RGB) -> None: ...

    def send_brightness(self, ip: str, value: int) -> None: ...


class LightWorker:
    """Connects Key presses to the lights."""

    def __init__(
        self,
        director: LightDirector,
        roster: TargetSource,
        client: LightSender,
        get_config: Callable[[], PianoConfig],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._director = director
        self._roster = roster
        self._client = client
        self._get_config = get_config
        self._clock = clock
        self._lock = threading.Lock()

    def press(self, key_index: int) -> None:
        """Record a Key press and return immediately."""
        with self._lock:
            self._director.press(key_index, self._clock())

    def step(self) -> None:
        """Send the next look if one is due. With no lights to change, it stays pending."""
        try:
            config = self._get_config()
            targets = self._roster.targets(config.light_ids)
            if not targets:
                return
            with self._lock:
                command = self._director.tick(self._clock(), config)
            if command is None:
                return
            for light in targets:
                self._client.send_brightness(light.ip, command.brightness)
                self._client.send_color(light.ip, command.color)
        except Exception:
            logger.exception("Could not update the lights")

    def _run(self) -> None:
        while True:
            self.step()
            time.sleep(STEP_SECONDS)

    def start(self) -> None:
        """Begin sending on a background thread."""
        threading.Thread(target=self._run, name="light-worker", daemon=True).start()
