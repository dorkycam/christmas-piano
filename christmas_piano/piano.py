"""The piano service: reads Keys, plays Notes and hands presses to the lights."""
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from christmas_piano import hardware
from christmas_piano.audio import SoundBoard, open_pygame_loader, pack_stamp
from christmas_piano.config import ConfigWatcher, PianoConfig, data_dir
from christmas_piano.govee import open_client
from christmas_piano.keys import KeyWatcher
from christmas_piano.light_director import LightDirector
from christmas_piano.light_roster import LightRoster, consume_rescan_request
from christmas_piano.light_worker import LightWorker

logger = logging.getLogger(__name__)

POLL_SECONDS = 0.005
CONFIG_CHECK_SECONDS = 1.0
ROSTER_REFRESH_SECONDS = 15
ROSTER_WAIT_SECONDS = 1.0


def _keep_roster_fresh(roster: LightRoster, rescan_path: Path) -> None:
    while True:
        try:
            roster.refresh()
        except OSError as error:
            logger.warning("Could not refresh the lights: %s", error)
        waited = 0.0
        while waited < ROSTER_REFRESH_SECONDS and not consume_rescan_request(rescan_path):
            time.sleep(ROSTER_WAIT_SECONDS)
            waited += ROSTER_WAIT_SECONDS


def start_lights(get_config: Callable[[], PianoConfig], root: Path) -> LightWorker | None:
    """Start the light threads. If that fails the piano carries on with Notes only."""
    try:
        client = open_client()
    except OSError as error:
        logger.error("Lights are unavailable: %s", error)
        return None
    roster = LightRoster(client, root / "lights.json")
    threading.Thread(
        target=_keep_roster_fresh, args=(roster, root / "rescan"), name="light-roster", daemon=True
    ).start()
    worker = LightWorker(LightDirector(), roster, client, get_config)
    worker.start()
    return worker


def main() -> None:
    """Run the piano until the service is stopped."""
    logging.basicConfig(level=logging.INFO)
    root = data_dir()
    watcher = ConfigWatcher(root / "config.json")
    config = watcher.current()
    board = SoundBoard(open_pygame_loader())
    worker = start_lights(lambda: config, root)

    pins: tuple[int, ...] | None = None
    key_watcher = KeyWatcher([], hardware.is_pressed)
    loaded_pack: tuple[str, int, int | None] | None = None
    next_config_check = 0.0
    try:
        while True:
            now = time.monotonic()
            if now >= next_config_check:
                next_config_check = now + CONFIG_CHECK_SECONDS
                config = watcher.current()
                wanted_pins = tuple(key.pin for key in config.keys)
                if wanted_pins != pins:
                    hardware.setup_pins(wanted_pins)
                    key_watcher = KeyWatcher(wanted_pins, hardware.is_pressed)
                    pins = wanted_pins
                pack_path = root / "sounds" / config.sound_pack
                wanted_pack = (config.sound_pack, len(config.keys), pack_stamp(pack_path))
                if wanted_pack != loaded_pack:
                    board.load_pack(pack_path, len(config.keys))
                    loaded_pack = wanted_pack
            for key_index in key_watcher.poll():
                board.play(key_index)
                if worker is not None:
                    worker.press(key_index)
            time.sleep(POLL_SECONDS)
    finally:
        hardware.release_pins()


if __name__ == "__main__":
    main()
