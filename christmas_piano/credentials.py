"""The page login and setup-network password, stored only on the Pi."""
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

MIN_PASSWORD_LENGTH = 8
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)


def write_private(path: Path, text: str) -> None:
    """Replace a file that only its owner can read, in one step."""
    temp_path = path.with_suffix(".tmp")
    descriptor = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as temp_file:
        temp_file.write(text)
    os.replace(temp_path, path)


class CredentialStore:
    """Keeps the password hashed for the page and readable only where wifi needs it."""

    def __init__(self, directory: Path) -> None:
        self._login_path = directory / "login.json"
        self._secret_path = directory / "setup-network.secret"

    def set_login(self, username: str, password: str) -> None:
        """Save a login. The setup network shares the password."""
        if not username:
            raise ValueError("A username is required.")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.")
        salt = secrets.token_bytes(SALT_BYTES)
        record = {"username": username, "salt": salt.hex(), "hash": _hash(password, salt).hex()}
        write_private(self._login_path, json.dumps(record))
        write_private(self._secret_path, password)

    def _record(self) -> dict[str, str] | None:
        try:
            record = json.loads(self._login_path.read_text())
        except (OSError, ValueError):
            return None
        return record if isinstance(record, dict) else None

    def verify(self, username: str, password: str) -> bool:
        """Return whether a login is correct."""
        record = self._record()
        if record is None:
            return False
        matches_hash = hmac.compare_digest(_hash(password, bytes.fromhex(record["salt"])).hex(), record["hash"])
        return hmac.compare_digest(username, record["username"]) and matches_hash

    def change_password(self, current: str, new: str) -> bool:
        """Change the password if the current one is right. Returns False if it is not."""
        record = self._record()
        if record is None or not self.verify(record["username"], current):
            return False
        self.set_login(record["username"], new)
        return True

    def setup_network_password(self) -> str:
        """Return the password for the setup network."""
        return self._secret_path.read_text()
