"""CLI utility to generate a bcrypt hash for the Master Password.

Usage:
    python generate_hash.py
    python generate_hash.py "my-secret-password"

The resulting hash should be placed in `.env` as MASTER_PASSWORD_HASH.
"""

import getpass
import sys

import bcrypt


def generate_hash(password: str) -> str:
    """Return a bcrypt hash for the given plaintext password."""
    if not password:
        raise ValueError("Password must not be empty.")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def main() -> int:
    """Entry point: read a password and print its bcrypt hash."""
    try:
        if len(sys.argv) > 1:
            password = sys.argv[1]
        else:
            password = getpass.getpass("Enter Master Password: ")
            confirm = getpass.getpass("Confirm Master Password: ")
            if password != confirm:
                print("ERROR: Passwords do not match.", file=sys.stderr)
                return 1

        hashed = generate_hash(password)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130

    print("\nAdd the following line to your .env file:\n")
    print(f"MASTER_PASSWORD_HASH={hashed}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
