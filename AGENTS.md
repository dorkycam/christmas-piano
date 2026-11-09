# Christmas Piano

A Raspberry Pi script that plays one of eight notes when its physical button is pressed.

## Hardware

- `bell_project.py` needs a Raspberry Pi: `RPi.GPIO` only works there. On any other machine, check changes with `python3 -m py_compile bell_project.py` and leave real playback to a test on the Pi.
- The position in `button_pins` sets the note: index `i` plays note `i + 1`. The order matches the wiring, so keep it as is unless the buttons are being rewired.

## Sounds

- At runtime the script loads `/home/winnetka/notes/note1.wav` through `note8.wav`, which are paths on the Pi. It does not read `sounds/` in this repo.
- Each folder in `sounds/` is a sound pack with exactly `note1.wav` through `note8.wav`. To use a pack, put its files in the Pi's notes directory.
