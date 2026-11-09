"""Tests for the settings page, using real stores and a fake wifi manager."""
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from christmas_piano.config import default_config, load_config, save_config
from christmas_piano.credentials import CredentialStore
from christmas_piano.sound_packs import InvalidSound, PackStore
from christmas_piano.web import create_app
from christmas_piano.wifi import WifiCommandError

USERNAME = "someone"
PASSWORD = "password1"
MULTIPART = "multipart/form-data"


def copy_convert(source: Path, destination: Path) -> None:
    if source.read_bytes() == b"not audio":
        raise InvalidSound("That file could not be read as audio.")
    shutil.copyfile(source, destination)


class FakeWifi:
    def __init__(self) -> None:
        self.connected: list[tuple[str, str]] = []
        self.password_applied = False
        self.connect_result = True

    def list_networks(self) -> list[str]:
        return ["Neighbors"]

    def connect(self, ssid: str, password: str) -> bool:
        self.connected.append((ssid, password))
        return self.connect_result

    def apply_setup_password(self) -> None:
        self.password_applied = True
        raise WifiCommandError("setup network does not exist yet")


@pytest.fixture
def wifi() -> FakeWifi:
    return FakeWifi()


@pytest.fixture
def anonymous(tmp_path: Path, wifi: FakeWifi) -> FlaskClient:
    credentials = CredentialStore(tmp_path)
    credentials.set_login(USERNAME, PASSWORD)
    packs = PackStore(tmp_path / "sounds", copy_convert)
    packs.create("meow")
    packs.create("carols")
    save_config(tmp_path / "config.json", default_config())
    return create_app(tmp_path, packs, credentials, wifi).test_client()


@pytest.fixture
def client(anonymous: FlaskClient) -> FlaskClient:
    anonymous.post("/login", data={"username": USERNAME, "password": PASSWORD})
    return anonymous


def settings_form(**changes: str) -> dict[str, str]:
    config = default_config()
    form = {
        "hold_seconds": "10",
        "fade_seconds": "2",
        "key_brightness": "20",
        "resting_color": "#ffb46b",
        "resting_brightness": "20",
        "sound_pack": "meow",
        "lights_mode": "all",
    }
    for number, key in enumerate(config.keys, start=1):
        form[f"key_pin_{number}"] = str(key.pin)
        form[f"key_color_{number}"] = "#%02x%02x%02x" % key.color
    return {**form, **changes}


@pytest.mark.parametrize("path", ["/", "/wifi", "/packs/backup.zip"])
def test_every_page_requires_login(anonymous: FlaskClient, path: str) -> None:
    response = anonymous.get(path)
    assert response.status_code == 302 and response.location.endswith("/login")


def test_changes_require_login(anonymous: FlaskClient, tmp_path: Path) -> None:
    anonymous.post("/", data=settings_form(hold_seconds="5"))
    assert load_config(tmp_path / "config.json").hold_seconds == 10


def test_wrong_login_rejected(anonymous: FlaskClient) -> None:
    anonymous.post("/login", data={"username": USERNAME, "password": "wrongpassword"})
    assert anonymous.get("/").status_code == 302


def test_login_then_settings_loads(client: FlaskClient) -> None:
    assert client.get("/").status_code == 200


def test_logout_ends_session(client: FlaskClient) -> None:
    client.post("/logout")
    assert client.get("/").status_code == 302


def test_saving_updates_config(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/", data=settings_form(hold_seconds="5"))
    assert load_config(tmp_path / "config.json").hold_seconds == 5


def test_saving_key_color(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/", data=settings_form(key_color_1="#010203"))
    assert load_config(tmp_path / "config.json").keys[0].color == (1, 2, 3)


def test_saving_key_brightness(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/", data=settings_form(key_brightness="55"))
    assert load_config(tmp_path / "config.json").key_brightness == 55


def test_saving_chosen_lights(client: FlaskClient, tmp_path: Path) -> None:
    form: dict[str, object] = {**settings_form(lights_mode="chosen"), "light_id": ["AA", "BB"]}
    client.post("/", data=form)
    assert load_config(tmp_path / "config.json").light_ids == ("AA", "BB")


def test_invalid_form_keeps_config(client: FlaskClient, tmp_path: Path) -> None:
    response = client.post("/", data=settings_form(key_brightness="500"), follow_redirects=True)
    assert b"from 0 to 100" in response.data
    assert load_config(tmp_path / "config.json").key_brightness == 20


def test_non_numeric_form_keeps_config(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/", data=settings_form(hold_seconds="soon"))
    assert load_config(tmp_path / "config.json").hold_seconds == 10


def test_unknown_sound_pack_rejected(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/", data=settings_form(sound_pack="missing"))
    assert load_config(tmp_path / "config.json").sound_pack == "meow"


def test_create_pack(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/packs", data={"name": "jazz"})
    assert (tmp_path / "sounds" / "jazz").is_dir()


def test_upload_replaces_note(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/packs/carols/notes/2", data={"file": (io.BytesIO(b"tune"), "tune.mp3")}, content_type=MULTIPART)
    assert (tmp_path / "sounds" / "carols" / "note2.wav").read_bytes() == b"tune"


def test_bad_upload_shows_error(client: FlaskClient) -> None:
    response = client.post(
        "/packs/carols/notes/2",
        data={"file": (io.BytesIO(b"not audio"), "tune.mp3")},
        content_type=MULTIPART,
        follow_redirects=True,
    )
    assert b"could not be read as audio" in response.data


def test_wrong_file_type_rejected(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/packs/carols/notes/2", data={"file": (io.BytesIO(b"tune"), "tune.exe")}, content_type=MULTIPART)
    assert not (tmp_path / "sounds" / "carols" / "note2.wav").exists()


def test_upload_over_limit_rejected(client: FlaskClient) -> None:
    big = io.BytesIO(b"x" * (21 * 1024 * 1024))
    response = client.post("/packs/carols/notes/2", data={"file": (big, "big.wav")}, content_type=MULTIPART)
    assert response.status_code == 413


def test_delete_pack(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/packs/carols/delete")
    assert not (tmp_path / "sounds" / "carols").exists()


def test_delete_active_pack_shows_error(client: FlaskClient, tmp_path: Path) -> None:
    response = client.post("/packs/meow/delete", follow_redirects=True)
    assert b"cannot be deleted" in response.data
    assert (tmp_path / "sounds" / "meow").is_dir()


def test_missing_notes_are_shown(client: FlaskClient) -> None:
    assert b"No Note yet for Keys 1, 2, 3, 4, 5, 6, 7, 8" in client.get("/").data


def test_backup_download_contains_packs(client: FlaskClient, tmp_path: Path) -> None:
    (tmp_path / "sounds" / "meow" / "note1.wav").write_bytes(b"x")
    response = client.get("/packs/backup.zip")
    assert zipfile.ZipFile(io.BytesIO(response.data)).namelist() == ["meow/note1.wav"]


def test_change_password_needs_current(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/password", data={"current": "wrongpassword", "new": "newpassword"})
    assert CredentialStore(tmp_path).verify(USERNAME, PASSWORD)


def test_change_password_updates_login(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/password", data={"current": PASSWORD, "new": "newpassword"})
    assert CredentialStore(tmp_path).verify(USERNAME, "newpassword")


def test_change_password_updates_setup_network(client: FlaskClient, wifi: FakeWifi) -> None:
    client.post("/password", data={"current": PASSWORD, "new": "newpassword"})
    assert wifi.password_applied


def test_short_new_password_shows_error(client: FlaskClient) -> None:
    response = client.post("/password", data={"current": PASSWORD, "new": "short"}, follow_redirects=True)
    assert b"at least 8" in response.data


def test_lights_listed_from_state(client: FlaskClient, tmp_path: Path) -> None:
    state = [{"device_id": "AA:BB", "ip": "1.1.1.1", "sku": "H805A", "on": True}]
    (tmp_path / "lights.json").write_text(json.dumps(state))
    assert b"AA:BB" in client.get("/").data


def test_opening_settings_requests_light_search(client: FlaskClient, tmp_path: Path) -> None:
    client.get("/")
    assert (tmp_path / "rescan").exists()


def test_corrupt_lights_state_still_loads(client: FlaskClient, tmp_path: Path) -> None:
    (tmp_path / "lights.json").write_text("not json")
    assert client.get("/").status_code == 200


def test_wifi_page_lists_networks(client: FlaskClient) -> None:
    assert b"Neighbors" in client.get("/wifi").data


def test_wifi_connect_calls_manager(client: FlaskClient, wifi: FakeWifi) -> None:
    client.post("/wifi", data={"ssid": "Home", "password": "homepassword"})
    assert wifi.connected == [("Home", "homepassword")]


def test_wifi_failure_shows_error(client: FlaskClient, wifi: FakeWifi) -> None:
    wifi.connect_result = False
    response = client.post("/wifi", data={"ssid": "Home", "password": "x"}, follow_redirects=True)
    assert b"Could not join Home" in response.data
