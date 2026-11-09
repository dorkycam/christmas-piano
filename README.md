# Christmas Piano

A Raspberry Pi with physical Keys that play Notes and change the color of Govee lights on a house.

## Using it

Plug in the Pi. On the same wifi, open **http://christmas-piano.local** and log in to change colors, timing and sounds. Govee lights need LAN Control turned on in the Govee app.

## Moving to new wifi

If the Pi can't reach a wifi network it knows, it creates a network called **Christmas Piano Setup** after about a minute.

1. Join that network from your computer, using the same password as the settings page.
2. Open **http://10.42.0.1/wifi** and log in.
3. Choose the new network. The Pi joins it, and your computer can go back to that wifi.

The piano keeps playing Notes the whole time.

## Developing

```
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

Install on a Pi with `sudo deploy/install.sh` from a checkout at `/home/piano/christmas-piano`.
