"""Tests for how the piano service starts and stops."""
import os
import signal
from collections.abc import Iterator

import pytest

from christmas_piano.piano import exit_on_terminate


@pytest.fixture(autouse=True)
def restore_handler() -> Iterator[None]:
    original = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, original)


def test_terminate_signal_exits_cleanly() -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    exit_on_terminate()
    with pytest.raises(SystemExit):
        os.kill(os.getpid(), signal.SIGTERM)
        signal.pause()
