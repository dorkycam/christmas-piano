"""Sets the page login once on the Pi: `python -m christmas_piano.setup_login`."""
import getpass
import sys

from christmas_piano.config import data_dir
from christmas_piano.credentials import CredentialStore


def main() -> None:
    """Ask for a login, or read two lines when input is piped, and store it."""
    if sys.stdin.isatty():
        username = input("Username: ")
        password = getpass.getpass("Password: ")
    else:
        username = sys.stdin.readline().rstrip("\n")
        password = sys.stdin.readline().rstrip("\n")
    CredentialStore(data_dir()).set_login(username, password)
    print("Login saved.")


if __name__ == "__main__":
    main()
