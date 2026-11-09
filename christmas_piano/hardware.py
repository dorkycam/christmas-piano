"""The Raspberry Pi's GPIO pins. Keys use internal pull-ups and read LOW when pressed."""
from collections.abc import Sequence


def setup_pins(pins: Sequence[int]) -> None:
    """Prepare the pins for reading, releasing any previous setup."""
    import RPi.GPIO as GPIO

    GPIO.setwarnings(False)
    GPIO.cleanup()
    GPIO.setmode(GPIO.BCM)
    for pin in pins:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def is_pressed(pin: int) -> bool:
    """Return whether the Key on this pin is pressed."""
    import RPi.GPIO as GPIO

    return GPIO.input(pin) == GPIO.LOW


def release_pins() -> None:
    """Return the pins to a safe state."""
    import RPi.GPIO as GPIO

    GPIO.cleanup()
