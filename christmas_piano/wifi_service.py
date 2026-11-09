"""The wifi service: watches the connection and offers the setup network when lost."""
import logging
import time

from christmas_piano.config import data_dir
from christmas_piano.credentials import CredentialStore
from christmas_piano.wifi import WifiCommandError, WifiManager, run_command

logger = logging.getLogger(__name__)

STEP_SECONDS = 5


def main() -> None:
    """Run until the service is stopped."""
    logging.basicConfig(level=logging.INFO)
    root = data_dir()
    manager = WifiManager(run_command, CredentialStore(root).setup_network_password, root / "networks.json")
    while True:
        try:
            manager.step(time.monotonic())
        except (WifiCommandError, OSError) as error:
            logger.warning("Wifi check failed: %s", error)
        time.sleep(STEP_SECONDS)


if __name__ == "__main__":
    main()
