"""Keeps track of which lights are on the network and which are switched on."""
import json
import os
from pathlib import Path
from typing import Protocol

from christmas_piano.govee import Light

DISCOVERY_SECONDS = 1.0
STATUS_SECONDS = 0.5


class LightFinder(Protocol):
    """The client calls the roster needs."""

    def discover(self, seconds: float) -> list[Light]: ...

    def is_on(self, ip: str, seconds: float) -> bool | None: ...


class LightRoster:
    """A snapshot of the lights. Lights that are off or silent are never sent colors."""

    def __init__(self, client: LightFinder, state_path: Path) -> None:
        self._client = client
        self._state_path = state_path
        self._lights: list[tuple[Light, bool | None]] = []

    def refresh(self) -> None:
        """Look for lights again and record the result for the settings page. This takes seconds."""
        found = self._client.discover(DISCOVERY_SECONDS)
        self._lights = [(light, self._client.is_on(light.ip, STATUS_SECONDS)) for light in found]
        self._write_state()

    def _write_state(self) -> None:
        state = [
            {"device_id": light.device_id, "ip": light.ip, "sku": light.sku, "on": on}
            for light, on in self._lights
        ]
        temp_path = self._state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(state))
        os.replace(temp_path, self._state_path)

    def targets(self, light_ids: tuple[str, ...] | None) -> list[Light]:
        """Return the selected lights that are currently on."""
        return [
            light
            for light, on in self._lights
            if on is True and (light_ids is None or light.device_id in light_ids)
        ]
