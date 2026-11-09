# Christmas Piano: Govee Lights, Settings Page and Portable Wifi

## Intent

Christmas Piano is a Raspberry Pi with physical Keys that play Notes. It has been used happily for a couple of years. The owner now has Govee lights on the house and wants them to change color as people play, wants to adjust everything from a browser on the same network, and wants to move the Pi to a new location without needing a screen or a terminal.

Vocabulary is defined in `GLOSSARY.md`. Decisions with lasting trade-offs are in `docs/adr/`.

## Goals, in build order

1. Pressing a Key changes the color of the lights.
2. A password-protected settings page on the Pi controls colors, timing, lights and Sound Packs.
3. The Pi can be moved to a new wifi network using only a Mac and a browser.

## Non-goals for now

- Patterns across pixels, such as stripes or sweeps. This is wanted later, so keep light control separate enough to extend. See "Experiments" below.
- Assigning particular Keys to particular lights.
- Different colors for each location.
- Controlling lights through a Govee account or cloud service (ADR 0001).
- Automatic software updates.

## Anti-goals

These would make the project a failure even if the features worked:

- A Note is delayed or lost because the lights are slow, unplugged or missing.
- The page login or setup-network password appears in the repo, the docs or the config file. The repo is public.
- The piano needs anything more than power to start playing.

## Key press behavior

- Pressing a Key plays its Note and sets every selected light to that Key's color.
- The color holds for a configurable time, default 10 seconds after the last press. Each press restarts the time.
- The lights then fade to the Resting Look over a configurable time, default 2 seconds.
- The Resting Look is one color and one brightness, default warm white.
- Key colors share one configurable brightness, separate from the Resting Look, default 20%.
- During fast playing the latest Key wins, and in-between colors are dropped.
- Light updates, including fade steps, are capped at about 10 per second. Recheck this on the real piano.
- The piano never turns lights on or off, so the Govee app and its schedules stay in charge. A press while the lights are off leaves them off. Whether the color command wakes an off light has not been tested; the builder must test this and prevent it if it does, for example by checking on/off state.
- Sound comes first. Nothing about the lights may block or delay the Note path.

## Lights

- Local network control only, using Govee's LAN protocol. LAN Control must be on in the Govee app.
- The test light is one model H805A, which answers discovery and accepted color, brightness-state and color-temperature checks.
- Measured from a Mac over wifi: status replies took 24-44 ms. Bursts of 5, 10 and 20 changes per second always ended on the right color. Immediately after a 10-per-second fade the light reported the second-to-last step, so changes appear to apply at least 0.1 seconds late.
- The light selection setting is either "every light found" (default) or a list of ticked lights, remembered by device ID so a changed network address does not matter.
- Moving to a new location uses the lights found there and keeps the same colors.
- Builder's call, recorded here: "never turn lights on" outranks "react to presses". If a color command wakes an off light, skip updates to lights known to be off, tracking on/off from a status check every 2 seconds rather than one per press. Tested on the H805A: commands sent to an off light turn it on, so a press within 2 seconds of switching off can still wake it. The update cap is per light.
- Builder's call, recorded here: discovery repeats periodically and whenever the settings page lists lights.

## Config

- One config file on the Pi is the single source of truth. The settings page reads and updates it, and changes take effect without a restart.
- It holds: each Key's wiring pin and color, Key brightness, hold time, fade time, Resting Look, light selection, and active Sound Pack.
- Each Key has one entry, so the same code handles 2 test buttons or all 8 Keys. Only listed pins are used.
- Default wiring, in Key order, is BCM pins 26, 17, 13, 22, 4, 5, 6, 27. This order matches the piano's wiring and sets which Note each Key plays.
- Default colors are a rainbow from red to violet in Key order.
- It lives outside the code checkout, so software updates cannot overwrite it.

## Settings page

- Served by the Pi at `http://christmas-piano.local`, in plain Python with no app or install on the Mac.
- Requires a login. The username and password are entered once during setup on the Pi. The password is stored only as a hash, on the Pi. Plain HTTP is an accepted trade-off for a page used only on the local network.
- Controls everything in the config, plus Sound Pack management.
- Offers a password change that requires the current password and updates the setup network's password at the same time. A forgotten password is reset by re-running setup over SSH.

## Sound Packs

- `meow` and `random` come from the repo. `meow` is active at first.
- The page can create a pack, replace any single Note, delete any pack except the active one, and switch the active pack.
- Uploads accept WAV and MP3 up to about 20 MB each, converted on the Pi to the format the piano plays.
- A pack with no Note for a Key leaves that Key silent, and the page shows that.
- Uploaded sounds stay on the Pi, outside the code checkout and out of the repo. The page offers a download-all backup, since a reflash erases uploads.

## Moving to new wifi

- If the Pi cannot reach any known wifi for about a minute, it creates a password-protected network called "Christmas Piano Setup".
- The owner joins it from a Mac and picks the new wifi on a page.
- The setup network uses the same password as the page login. Wifi needs the real password, so it is stored readable on the Pi, outside the repo and the config file.
- The Pi keeps checking for known networks and rejoins on its own if one returns.
- Notes keep playing throughout. Lights cannot react until the Pi shares a network with them.
- Builder's call, recorded here: assume only the Pi's built-in wifi. Checking for known networks may briefly interrupt the setup network. The setup page is reached at a fixed address shown in the setup instructions, since `.local` names may not work on that network.

## Running on the Pi

- Starts automatically on power-on and restarts within a few seconds after a crash.
- Sound plays through the Pi's headphone jack. The exact Pi model is not known yet and can be read once the new system is installed.
- Software updates happen only on request, by pulling the latest code from GitHub. Config, login and uploaded sounds are unaffected.

## Installing

- The current SD card is backed up to a compressed image on the Mac, and the backup is verified as complete before the card is erased.
- The backup is also the record of the old install. Compare its project copy and Notes with the repo, and bring across any Notes that are missing.
- The same card is reflashed with Raspberry Pi OS Lite, hostname `christmas-piano`, user `piano`, with the Mac's existing SSH key and current wifi preconfigured.
- Setup is then run once over SSH, which also sets the page login.
- Pins for the 2 test buttons are detected after install by watching GPIO while the owner presses each one.

## Current state of the code

`bell_project.py` is one script that polls 8 pins and plays fixed Pi paths under `/home/winnetka/notes`. In the repo copy, a bare `yield` at line 49 makes `main()` a generator, so running it does nothing. The copy that ran on the Pi for years has not been compared. Replace this with the new structure.

Behavior to preserve: Keys use internal pull-ups and read LOW when pressed, a Note plays once per press edge, and Notes can overlap. The repo's sounds are WAV files named `note1.wav` to `note8.wav`, with `noteN` belonging to Key N. The `random` pack is 16-bit mono 44.1 kHz.

## Experiments

An undocumented `ptReal` LAN command was sent to paint red and white segment bands, assuming 16 segments. It worked on the H805A: the owner saw alternating groups of red and white lights, not individual LEDs. Each band was two segments wide. The real segment count and LEDs per segment are unknown, and read requests for segment data got no reply. It was a throwaway test, and the command is undocumented, so a future patterns feature should re-verify it.

## Left to the builder

These were the builder's call rather than the owner's decisions:

- Python libraries for GPIO, audio, the web server and password hashing.
- Process and module structure, as long as the Note path stays independent of the lights.
- Config file format and locations on the Pi.
- Visual design of the page.
- Default port handling needed to serve the page without a port number.
- How wifi switching and the setup network are implemented, including whether checking for known networks briefly interrupts the setup network.
- Whether to rename `bell_project.py`.
