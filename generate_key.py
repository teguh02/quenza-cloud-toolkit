"""CLI utility to generate a Fernet encryption key for ENCRYPTION_KEY.

Usage:
    python generate_key.py

The resulting key should be placed in `.env` as ENCRYPTION_KEY. It is used
to encrypt sensitive destination config (e.g. Google Drive refresh tokens).
"""

import sys


def main() -> int:
    """Generate and print a Fernet key."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print(
            "ERROR: 'cryptography' belum terpasang. Jalankan: "
            "pip install cryptography",
            file=sys.stderr,
        )
        return 1

    key = Fernet.generate_key().decode("utf-8")
    print("\nAdd the following line to your .env file:\n")
    print(f"ENCRYPTION_KEY={key}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
