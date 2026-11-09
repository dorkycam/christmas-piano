# Christmas Piano Lights, Settings and Wifi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Govee lights follow the piano's Keys, add a password-protected settings page, and let the Pi move to new wifi from a browser.

**Architecture:** Three systemd services share a data directory. The piano service polls Keys and plays Notes on one thread, and hands presses to a separate light thread. The web service edits the config file, which the piano service picks up by watching its modification time. The wifi service watches connectivity and manages the setup network.

**Tech Stack:** Python 3.11+, pygame (audio), RPi.GPIO, Flask, ffmpeg, NetworkManager (`nmcli`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-08-govee-piano-lights-design.md`

## Global Constraints

- The page login and setup-network password never appear in the repo, docs, config file, logs or command lines.
- Nothing about the lights may block or delay the Note path.
- Local network only (ADR 0001): LAN port 4001 multicast discovery, 4002 replies, 4003 commands.
- Defaults: hold 10 seconds, fade 2 seconds, Key brightness 20, warm white Resting Look, at most 10 updates per second per light.
- `RPi.GPIO` and `pygame` are imported only inside `hardware.py` and `audio.py` functions, so tests run on a Mac.
- Data directory is `$CHRISTMAS_PIANO_DATA`, default `/var/lib/christmas-piano`, outside the code checkout. It holds `config.json`, `lights.json`, `rescan`, `login.json`, `setup-network.secret`, `session.secret` and `sounds/`.
- Project style: explicit return types and docstrings on public functions, `SCREAMING_SNAKE_CASE` constants, no type-suppression comments. Use `GLOSSARY.md` terms.

## Review Focus

- `config.json` is corrupt or half-written at boot: the piano still plays using defaults (Task 1).
- A Note file is missing or unreadable: that Key is silent and every other Key works (Task 4).
- The network is down while Keys are pressed: send errors are swallowed and Notes continue (Task 2).
- An uploaded file is not audio: the upload is rejected and the existing Note is untouched (Task 5).
- A pack name contains `../`: rejected before touching the filesystem (Task 5).

---

### Task 1: Config

**Files:** Create `christmas_piano/__init__.py`, `christmas_piano/config.py`, `requirements-dev.txt`, `tests/test_config.py`

**Interfaces:**
- Produces: `RGB = tuple[int, int, int]`; frozen dataclasses `KeyConfig(pin: int, color: RGB)`, `RestingLook(color: RGB, brightness: int)`, `PianoConfig(keys: tuple[KeyConfig, ...], key_brightness: int, hold_seconds: float, fade_seconds: float, resting_look: RestingLook, light_ids: tuple[str, ...] | None, sound_pack: str)`; `ConfigError`; `default_config() -> PianoConfig`; `parse_config(raw: dict[str, object]) -> PianoConfig`; `config_to_dict(config: PianoConfig) -> dict[str, object]`; `load_config(path: Path) -> PianoConfig`; `save_config(path: Path, config: PianoConfig) -> None`; `ConfigWatcher(path).current() -> PianoConfig`; `data_dir() -> Path`.

- [ ] **Step 1: Write failing tests**

```python
def test_defaults():
    c = default_config()
    assert [k.pin for k in c.keys] == [26, 17, 13, 22, 4, 5, 6, 27]
    assert c.keys[0].color == (255, 0, 0) and c.keys[7].color == (148, 0, 211)
    assert (c.hold_seconds, c.fade_seconds, c.key_brightness) == (10, 2, 20)
    assert c.light_ids is None and c.sound_pack == "meow"

def test_round_trip(): assert parse_config(config_to_dict(default_config())) == default_config()
def test_rejects_brightness_101(): pytest.raises(ConfigError)  # also negative timers, duplicate pins, color value 256
def test_corrupt_file_loads_defaults(tmp_path): assert load_config(file_with_garbage) == default_config()
def test_save_is_atomic(tmp_path): assert no *.tmp files remain and load_config(path) == saved
def test_watcher_sees_change(tmp_path): assert watcher.current().hold_seconds == 3 after save_config and os.utime
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_config.py -v`. Expected: FAIL on import.
- [ ] **Step 3: Implement.** Rainbow is `(255,0,0) (255,127,0) (255,255,0) (0,255,0) (0,255,255) (0,0,255) (75,0,130) (148,0,211)`. Warm white is `(255,180,107)` at brightness 20. Save through a temp file in the same directory and `os.replace`.
- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add piano config`.

### Task 2: Govee LAN client and light roster

**Files:** Create `christmas_piano/govee.py`, `christmas_piano/light_roster.py`, `tests/test_govee.py`, `tests/test_light_roster.py`

**Interfaces:**
- Produces: `Light(device_id: str, ip: str, sku: str)`; `GoveeClient(send_socket, receive_socket)` with `send_color(ip: str, color: RGB) -> None`, `send_brightness(ip: str, value: int) -> None`, `discover(seconds: float) -> list[Light]`, `is_on(ip: str, seconds: float) -> bool | None`; `open_client() -> GoveeClient`; `LightRoster(client, state_path: Path)` with `refresh() -> None` and `targets(light_ids: tuple[str, ...] | None) -> list[Light]`.

- [ ] **Step 1: Write failing tests** using a fake socket that records `sendto` and replays replies.

```python
def test_color_packet(): assert sent == ({"msg": {"cmd": "colorwc", "data": {"color": {"r": 1, "g": 2, "b": 3}, "colorTemInKelvin": 0}}}, ("1.1.1.1", 4003))
def test_send_error_is_swallowed(): socket raising OSError; client.send_color(...) returns None
def test_discover_parses_scan_reply(): assert lights == [Light("AA", "1.1.1.1", "H805A")]
def test_is_on_timeout_is_none(): assert client.is_on("1.1.1.1", 0.01) is None
def test_targets_exclude_off_and_unknown(): only lights with is_on True returned
def test_targets_filter_by_id(): targets(("AA",)) excludes "BB"
def test_refresh_writes_state(tmp_path): lights.json lists device_id, ip, sku, on
```

- [ ] **Step 2: Run tests.** Expected: FAIL on import.
- [ ] **Step 3: Implement.** Port 4002 has one owner, the roster's client. `refresh` runs on its own thread (Task 4), so discovery never blocks light sends. Unknown on/off counts as off, because lights are never turned on.
- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add Govee LAN client and roster`.

### Task 3: Light director

**Files:** Create `christmas_piano/light_director.py`, `tests/test_light_director.py`

**Interfaces:**
- Consumes: `PianoConfig`, `RGB`.
- Produces: `LightCommand(color: RGB, brightness: int)`; `LightDirector(update_interval: float = 0.1)` with `press(key_index: int, now: float) -> None` and `tick(now: float, config: PianoConfig) -> LightCommand | None`.

- [ ] **Step 1: Write failing tests** with an explicit clock.

```python
def test_first_tick_sends_resting(): assert d.tick(0, c) == LightCommand(c.resting_look.color, c.resting_look.brightness)
def test_press_sends_key_color(): assert d.tick(1, c) == LightCommand(c.keys[2].color, 20)
def test_latest_key_wins(): press(1) and press(2) before tick; tick returns keys[2]
def test_rate_cap(): second press 0.05s after a send returns None, then keys[n] at 0.1s
def test_holds_without_resending(): tick at 5s after press is None
def test_press_restarts_hold(): press at 0 and 8; tick at 11 is None
def test_fade_midpoint(): at hold + fade/2 color is halfway between key color and resting
def test_fade_ends_exactly_on_resting_once(): at hold + fade equals resting; next tick None
def test_press_during_fade_returns_to_key_color()
def test_key_removed_from_config_ignored(): press(7) with a 2-Key config; tick returns None
```

- [ ] **Step 2: Run tests.** Expected: FAIL on import.
- [ ] **Step 3: Implement** as a pure state machine with linear interpolation of color and brightness, rounding to integers. A changed Resting Look is re-sent while resting.
- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add light director`.

### Task 4: Piano service

**Files:** Create `christmas_piano/keys.py`, `christmas_piano/audio.py`, `christmas_piano/hardware.py`, `christmas_piano/light_worker.py`, `christmas_piano/piano.py`, `tests/test_keys.py`, `tests/test_audio.py`, `tests/test_light_worker.py`. Delete `bell_project.py`. Modify `AGENTS.md`.

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: `KeyWatcher(pins: Sequence[int], read_pin: Callable[[int], bool]).poll() -> list[int]` (`read_pin` returns True when pressed); `SoundBoard(load_sound: Callable[[Path], Playable])` with `load_pack(directory: Path, key_count: int) -> None` and `play(key_index: int) -> None`; `LightWorker(director, roster, client, get_config)` with non-blocking `press(key_index: int) -> None` and `start() -> None`; `piano.main() -> None`, run with `python -m christmas_piano.piano`.

- [ ] **Step 1: Write failing tests**

```python
def test_press_once_per_edge(): held for 3 polls gives [0], [], []; release and press gives [0]
def test_two_keys_same_poll(): assert poll() == [0, 1]
def test_note_n_belongs_to_key_n(): play(2) plays note3.wav
def test_missing_note_is_silent(): play(1) no exception; others play
def test_unreadable_note_is_silent(): load_sound raises; load_pack completes
def test_press_does_not_wait_on_slow_client(): client.send_color sleeps 1s; worker.press returns in under 10 ms
def test_worker_sends_brightness_and_color_to_each_target()
def test_worker_survives_client_exception(): a raising client does not stop later sends
```

- [ ] **Step 2: Run tests.** Expected: FAIL on import.
- [ ] **Step 3: Implement.** The main thread loops every 5 ms: poll, `SoundBoard.play`, `LightWorker.press`; it rebuilds pins and reloads the pack when the config changes. Use 16 mixer channels so Notes overlap. Refresh the roster every 15 seconds, and within a second when `rescan` appears, then delete it. Keys use pull-ups and read LOW when pressed.
- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Update `AGENTS.md`** with the test command and new entry points, then commit `feat: drive lights from piano keys`.

### Task 5: Sound Pack store

**Files:** Create `christmas_piano/sound_packs.py`, `tests/test_sound_packs.py`

**Interfaces:**
- Produces: `PackInfo(name: str, notes: frozenset[int])`; `InvalidSound`, `InvalidPack`; `PackStore(root: Path, convert: Callable[[Path, Path], None] = ffmpeg_convert)` with `list_packs() -> list[PackInfo]`, `create(name: str) -> None`, `delete(name: str, active: str) -> None`, `replace_note(name: str, key_number: int, upload: Path) -> None`, `export_zip(destination: Path) -> None`.

- [ ] **Step 1: Write failing tests**

```python
def test_create_and_list(tmp_path): assert store.list_packs() == [PackInfo("carols", frozenset())]
@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".hidden"]): pytest.raises(InvalidPack)
def test_cannot_delete_active(): pytest.raises(InvalidPack)
def test_replace_note_converts_to_noteN(): note3.wav exists after replace_note(name, 3, upload)
def test_failed_conversion_keeps_old_note(): convert raises InvalidSound; note bytes unchanged
def test_export_zip_contains_all_packs(): zip namelist includes "meow/note1.wav"
```

- [ ] **Step 2: Run tests.** Expected: FAIL on import.
- [ ] **Step 3: Implement.** Valid names match `^[a-z0-9][a-z0-9 _-]{0,39}$`. `ffmpeg_convert` runs `ffmpeg -y -i in -ac 1 -ar 44100 -sample_fmt s16 out.wav` with a 30-second timeout and raises `InvalidSound` on failure. Convert to a temp file, then `os.replace`.
- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add sound pack store`.

### Task 6: Login credentials

**Files:** Create `christmas_piano/credentials.py`, `christmas_piano/setup_login.py`, `tests/test_credentials.py`

**Interfaces:**
- Produces: `CredentialStore(directory: Path)` with `set_login(username: str, password: str) -> None`, `verify(username: str, password: str) -> bool`, `change_password(current: str, new: str) -> bool`, `setup_network_password() -> str`; `MIN_PASSWORD_LENGTH = 8`; `python -m christmas_piano.setup_login` reads username and password from `getpass` prompts.

- [ ] **Step 1: Write failing tests**

```python
def test_verify(): assert store.verify("u", "password1") and not store.verify("u", "wrong")
def test_password_not_in_login_file(): assert b"password1" not in login_json_bytes
def test_secret_files_are_private(): assert mode_of(login_json) == mode_of(secret) == 0o600
def test_change_requires_current(): assert not store.change_password("wrong", "newpassword")
def test_change_updates_setup_network(): assert store.setup_network_password() == "newpassword"
def test_short_password_rejected(): pytest.raises(ValueError)  # wifi needs at least 8 characters
```

- [ ] **Step 2: Run tests.** Expected: FAIL on import.
- [ ] **Step 3: Implement** with `hashlib.scrypt`, a random salt per hash, and `hmac.compare_digest`.
- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add login credentials`.

### Task 7: Wifi manager

**Files:** Create `christmas_piano/wifi.py`, `christmas_piano/wifi_service.py`, `tests/test_wifi.py`

**Interfaces:**
- Consumes: `CredentialStore.setup_network_password`.
- Produces: `SETUP_SSID = "Christmas Piano Setup"`, `SETUP_ADDRESS = "10.42.0.1"`; `WifiManager(run: Callable[[list[str]], str], get_password: Callable[[], str])` with `step(now: float) -> None`, `list_networks() -> list[str]`, `connect(ssid: str, password: str) -> bool`, `apply_setup_password() -> None`.

- [ ] **Step 1: Write failing tests** with a fake `run` recording `nmcli` argument lists.

```python
def test_no_hotspot_before_60s(); def test_hotspot_after_60s_offline(): nmcli args include SETUP_SSID
def test_connected_resets_timer()
def test_hotspot_retries_known_networks_every_300s()
def test_connect_failure_returns_false_and_restores_hotspot()
def test_networks_cached_before_hotspot_starts()
```

- [ ] **Step 2: Run tests.** Expected: FAIL on import.
- [ ] **Step 3: Implement.** Passwords reach `nmcli` through `--ask` on stdin or a NetworkManager connection file, so they never appear in process arguments. Change the `run` signature to accept optional input if needed and keep the tests in step.
- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add wifi manager`.

### Task 8: Settings page

**Files:** Create `christmas_piano/web.py`, `christmas_piano/templates/login.html`, `christmas_piano/templates/settings.html`, `christmas_piano/templates/wifi.html`, `tests/test_web.py`

**Interfaces:**
- Consumes: Tasks 1, 5, 6, 7.
- Produces: `create_app(data_path: Path, packs: PackStore, credentials: CredentialStore, wifi: WifiManager) -> Flask`; `python -m christmas_piano.web`.

- [ ] **Step 1: Write failing tests** with Flask's test client.

```python
def test_every_page_requires_login(): GET /, /wifi and /packs/backup.zip redirect to /login
def test_wrong_login_rejected(); def test_login_then_settings_loads()
def test_saving_updates_config(): POST / with hold 5; load_config(...).hold_seconds == 5
def test_invalid_form_keeps_config(): brightness 500 shows error; config unchanged
def test_upload_over_limit_rejected(): 21 MB returns 413
def test_upload_replaces_note(); def test_bad_upload_shows_error()
def test_delete_active_pack_shows_error()
def test_missing_notes_are_shown()
def test_change_password_needs_current()
def test_lights_listed_from_state_and_rescan_requested(): GET / creates the rescan file
def test_wifi_connect_calls_manager()
```

- [ ] **Step 2: Run tests.** Expected: FAIL on import.
- [ ] **Step 3: Implement.** `MAX_CONTENT_LENGTH` is 20 MB. Session cookies are `HttpOnly` and `SameSite=Strict`, with the key in `session.secret`. Accept `.wav` and `.mp3`.
- [ ] **Step 4: Run tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: add settings page`.

### Task 9: Install on the Pi

**Files:** Create `deploy/christmas-piano.service`, `deploy/christmas-piano-web.service`, `deploy/christmas-piano-wifi.service`, `deploy/50-christmas-piano.rules`, `deploy/install.sh`

- [ ] **Step 1: Write the deploy files.** Services use `Restart=always`, `RestartSec=2`, `After=sound.target` for the piano. The web service gets `AmbientCapabilities=CAP_NET_BIND_SERVICE` on port 80. `install.sh` is idempotent: installs `python3-pygame python3-rpi.gpio python3-flask ffmpeg`, creates the data directory owned by `piano`, seeds `sounds/` without overwriting, selects the headphone jack, installs units and enables them.
- [ ] **Step 2: Verify** `bash -n deploy/install.sh` and `.venv/bin/pytest`. Expected: no syntax errors, all tests PASS.
- [ ] **Step 3: Commit** `feat: add Pi install scripts`.

### Task 10: Bring-up on real hardware

No code unless a problem appears. Each step needs the owner.

- [ ] **Step 1: Back up.** Owner runs the backup command. Verify: `zstd -dc <backup> | wc -c` prints `128177930240`.
- [ ] **Step 2: Salvage.** Read the old project and Notes out of the backup, compare with the repo, and bring across missing Notes.
- [ ] **Step 3: Flash** with Raspberry Pi Imager: Pi OS Lite 64-bit, hostname `christmas-piano`, user `piano`, Mac's SSH key, current wifi. Confirm target is the 128 GB removable card.
- [ ] **Step 4: Install** with `deploy/install.sh`, then run `setup_login` with the owner's password over a private stdin. Expected: three services `active`.
- [ ] **Step 5: Detect test-button pins** while the owner presses each one, and set a 2-Key config.
- [ ] **Step 6: Check the wake question.** With the light off, send a brightness command and read status, then repeat with a color command, because the worker sends brightness first. If either wakes it, confirm the roster's off-skip prevents it, and measure a press within 15 seconds of switching off. Expected: a press with the light off leaves it off.
- [ ] **Step 7: Owner test.** Keys play through the headphone jack, lights follow, and the page saves. Then cover wifi: the setup network appears when wifi is unavailable, joining succeeds with a right password and fails with a wrong one, a known network is rejoined after a retry, and a password change updates the setup network.
