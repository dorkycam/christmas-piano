# Christmas Piano

A Raspberry Pi with physical Keys that play Notes and change the color of Govee lights. See `GLOSSARY.md` for terms and `docs/adr/` for decisions.

## Testing

Run `.venv/bin/pytest`. Tests run on any machine: `RPi.GPIO` and `pygame` are imported only inside the functions in `hardware.py` and `audio.py`, so keep them there.

Real behavior needs a Pi with Keys and lights attached. Before merging changes to timing or light control, test on the hardware.

## Rules that are easy to break

- Nothing about the lights may block or delay the Note path in `piano.py`. Lights work happens on separate threads.
- The page login and setup-network password never go in the repo, config file, logs or command lines. The repo is public.
- The position of a Key in the config sets its Note: index `i` plays `note{i + 1}.wav`. The default pin order matches the piano's wiring.
- The piano never turns lights on or off. Lights that are off or silent are skipped.

## Layout on the Pi

Config, login and sounds live in `$CHRISTMAS_PIANO_DATA` (default `/var/lib/christmas-piano`), outside the code checkout. Each folder in `sounds/` in the repo is a built-in Sound Pack, copied there at install.
