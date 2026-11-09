"""Tests for the page login and setup-network password."""
import io
import stat
from pathlib import Path

import pytest

from christmas_piano import setup_login
from christmas_piano.credentials import CredentialStore

USERNAME = "someone"
PASSWORD = "password1"


@pytest.fixture
def store(tmp_path: Path) -> CredentialStore:
    credentials = CredentialStore(tmp_path)
    credentials.set_login(USERNAME, PASSWORD)
    return credentials


def test_verify_accepts_correct_login(store: CredentialStore) -> None:
    assert store.verify(USERNAME, PASSWORD)


def test_verify_rejects_wrong_password(store: CredentialStore) -> None:
    assert not store.verify(USERNAME, "wrongpassword")


def test_verify_rejects_wrong_username(store: CredentialStore) -> None:
    assert not store.verify("nobody", PASSWORD)


def test_verify_without_login_is_false(tmp_path: Path) -> None:
    assert not CredentialStore(tmp_path).verify(USERNAME, PASSWORD)


def test_password_not_in_login_file(store: CredentialStore, tmp_path: Path) -> None:
    assert PASSWORD.encode() not in (tmp_path / "login.json").read_bytes()


def test_login_file_is_private(store: CredentialStore, tmp_path: Path) -> None:
    assert stat.S_IMODE((tmp_path / "login.json").stat().st_mode) == 0o600


def test_setup_network_secret_is_private(store: CredentialStore, tmp_path: Path) -> None:
    assert stat.S_IMODE((tmp_path / "setup-network.secret").stat().st_mode) == 0o600


def test_setup_network_uses_login_password(store: CredentialStore) -> None:
    assert store.setup_network_password() == PASSWORD


def test_change_requires_current(store: CredentialStore) -> None:
    assert not store.change_password("wrongpassword", "newpassword")
    assert store.verify(USERNAME, PASSWORD)


def test_change_updates_login(store: CredentialStore) -> None:
    assert store.change_password(PASSWORD, "newpassword")
    assert store.verify(USERNAME, "newpassword")


def test_change_updates_setup_network(store: CredentialStore) -> None:
    store.change_password(PASSWORD, "newpassword")
    assert store.setup_network_password() == "newpassword"


def test_short_password_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CredentialStore(tmp_path).set_login(USERNAME, "short")


def test_change_to_short_password_rejected(store: CredentialStore) -> None:
    with pytest.raises(ValueError):
        store.change_password(PASSWORD, "short")


def test_setup_login_reads_piped_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHRISTMAS_PIANO_DATA", str(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{USERNAME}\n{PASSWORD}\n"))
    setup_login.main()
    assert CredentialStore(tmp_path).verify(USERNAME, PASSWORD)
