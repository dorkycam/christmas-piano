"""The password-protected settings page, served by the Pi."""
import io
import json
import logging
import re
import secrets
import tempfile
from pathlib import Path
from typing import Protocol

from flask import Flask, Response, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.wrappers import Response as BaseResponse

from christmas_piano.config import ConfigError, PianoConfig, config_to_dict, data_dir, load_config, parse_config, save_config
from christmas_piano.credentials import CredentialStore, write_private
from christmas_piano.sound_packs import InvalidPack, InvalidSound, PackStore
from christmas_piano.wifi import SETUP_ADDRESS, WifiCommandError, WifiManager, run_command

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".wav", ".mp3"}
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
PUBLIC_ENDPOINTS = {"login", "static"}
WEB_PORT = 80


class WifiControls(Protocol):
    """The wifi actions the page offers."""

    def list_networks(self) -> list[str]: ...

    def connect(self, ssid: str, password: str) -> bool: ...

    def apply_setup_password(self) -> None: ...


def _session_key(path: Path) -> str:
    """Return the key that signs login cookies, creating it the first time."""
    try:
        return path.read_text()
    except OSError:
        key = secrets.token_hex(32)
        write_private(path, key)
        return key


def _hex_to_rgb(value: str) -> list[int]:
    if not HEX_COLOR.fullmatch(value):
        raise ConfigError("Colors must look like #ff0000.")
    return [int(value[start : start + 2], 16) for start in (1, 3, 5)]


def _number(form: ImmutableMultiDict[str, str], field: str, kind: type[int] | type[float]) -> int | float:
    try:
        return kind(form.get(field, ""))
    except ValueError as error:
        raise ConfigError(f"{field.replace('_', ' ')} must be a number.") from error


def _config_from_form(form: ImmutableMultiDict[str, str], current: PianoConfig) -> PianoConfig:
    """Build a new config from the settings form, raising ConfigError if it is invalid."""
    raw: dict[str, object] = {
        **config_to_dict(current),
        "keys": [
            {
                "pin": _number(form, f"key_pin_{number}", int),
                "color": _hex_to_rgb(form.get(f"key_color_{number}", "")),
            }
            for number in range(1, len(current.keys) + 1)
        ],
        "key_brightness": _number(form, "key_brightness", int),
        "hold_seconds": _number(form, "hold_seconds", float),
        "fade_seconds": _number(form, "fade_seconds", float),
        "resting_look": {
            "color": _hex_to_rgb(form.get("resting_color", "")),
            "brightness": _number(form, "resting_brightness", int),
        },
        "light_ids": None if form.get("lights_mode") == "all" else form.getlist("light_id"),
        "sound_pack": form.get("sound_pack", ""),
    }
    return parse_config(raw)


def _rgb_to_hex(color: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % color


def _read_lights(path: Path) -> list[dict[str, object]]:
    try:
        lights = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    return lights if isinstance(lights, list) else []


def create_app(data_path: Path, packs: PackStore, credentials: CredentialStore, wifi: WifiControls) -> Flask:
    """Build the settings page around the stores it manages."""
    app = Flask(__name__)
    app.secret_key = _session_key(data_path / "session.secret")
    app.config.update(MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")
    config_path = data_path / "config.json"

    @app.before_request
    def require_login() -> BaseResponse | None:
        if request.endpoint not in PUBLIC_ENDPOINTS and not session.get("logged_in"):
            return redirect(url_for("login"))
        return None

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(_: RequestEntityTooLarge) -> tuple[str, int]:
        return render_template("message.html", message="That file is larger than 20 MB."), 413

    @app.route("/login", methods=["GET", "POST"])
    def login() -> BaseResponse | str:
        if request.method == "POST":
            if credentials.verify(request.form.get("username", ""), request.form.get("password", "")):
                session.clear()
                session["logged_in"] = True
                return redirect(url_for("settings"))
            flash("That username or password is not right.")
        return render_template("login.html")

    @app.post("/logout")
    def logout() -> BaseResponse:
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def settings() -> str:
        config = load_config(config_path)
        try:
            (data_path / "rescan").touch()
        except OSError as error:
            logger.warning("Could not request a light search: %s", error)
        all_packs = packs.list_packs()
        lights = _read_lights(data_path / "lights.json")
        found_ids = {light.get("device_id") for light in lights}
        active = next((pack for pack in all_packs if pack.name == config.sound_pack), None)
        have_notes = active.notes if active else frozenset()
        return render_template(
            "settings.html",
            config=config,
            packs=all_packs,
            lights=lights,
            absent_lights=[light_id for light_id in config.light_ids or () if light_id not in found_ids],
            missing_notes=[number for number in range(1, len(config.keys) + 1) if number not in have_notes],
            to_hex=_rgb_to_hex,
        )

    @app.post("/")
    def save_settings() -> BaseResponse:
        try:
            config = _config_from_form(request.form, load_config(config_path))
            if config.sound_pack not in {pack.name for pack in packs.list_packs()}:
                raise ConfigError("That Sound Pack does not exist.")
            save_config(config_path, config)
            flash("Saved.")
        except ConfigError as error:
            flash(str(error))
        return redirect(url_for("settings"))

    @app.post("/packs")
    def create_pack() -> BaseResponse:
        try:
            packs.create(request.form.get("name", ""))
        except InvalidPack as error:
            flash(str(error))
        return redirect(url_for("settings"))

    @app.post("/packs/<name>/notes/<int:number>")
    def upload_note(name: str, number: int) -> BaseResponse:
        upload = request.files.get("file")
        suffix = Path(upload.filename or "").suffix.lower() if upload else ""
        if upload is None or suffix not in ALLOWED_UPLOAD_SUFFIXES:
            flash("Please choose a WAV or MP3 file.")
            return redirect(url_for("settings"))
        try:
            with tempfile.TemporaryDirectory() as directory:
                saved = Path(directory) / f"upload{suffix}"
                upload.save(saved)
                packs.replace_note(name, number, saved)
            flash(f"Updated Key {number} in {name}.")
        except (InvalidPack, InvalidSound) as error:
            flash(str(error))
        return redirect(url_for("settings"))

    @app.post("/packs/<name>/delete")
    def delete_pack(name: str) -> BaseResponse:
        try:
            packs.delete(name, load_config(config_path).sound_pack)
        except InvalidPack as error:
            flash(str(error))
        return redirect(url_for("settings"))

    @app.get("/packs/backup.zip")
    def backup_packs() -> Response:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "sounds.zip"
            packs.export_zip(destination)
            contents = io.BytesIO(destination.read_bytes())
        return send_file(contents, mimetype="application/zip", as_attachment=True, download_name="christmas-piano-sounds.zip")

    @app.post("/password")
    def change_password() -> BaseResponse:
        try:
            if credentials.change_password(request.form.get("current", ""), request.form.get("new", "")):
                flash("Password changed.")
                try:
                    wifi.apply_setup_password()
                except (WifiCommandError, OSError) as error:
                    logger.info("Setup network will use the new password when it next starts: %s", error)
            else:
                flash("The current password is not right.")
        except ValueError as error:
            flash(str(error))
        return redirect(url_for("settings"))

    @app.route("/wifi", methods=["GET", "POST"])
    def wifi_page() -> BaseResponse | str:
        if request.method == "POST":
            ssid = request.form.get("ssid", "")
            if wifi.connect(ssid, request.form.get("password", "")):
                flash(f"Joined {ssid}.")
            else:
                flash(f"Could not join {ssid}. Check the password and try again.")
            return redirect(url_for("wifi_page"))
        return render_template("wifi.html", networks=wifi.list_networks(), setup_address=SETUP_ADDRESS)

    return app


def main() -> None:
    """Serve the page until the service is stopped."""
    from waitress import serve

    logging.basicConfig(level=logging.INFO)
    root = data_dir()
    credentials = CredentialStore(root)
    wifi = WifiManager(run_command, credentials.setup_network_password, root / "networks.json")
    serve(create_app(root, PackStore(root / "sounds"), credentials, wifi), host="0.0.0.0", port=WEB_PORT)


if __name__ == "__main__":
    main()
