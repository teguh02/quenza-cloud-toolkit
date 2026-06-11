"""Symmetric encryption for sensitive secrets (Fernet).

Used to encrypt destination secrets such as Google Drive refresh tokens
before they are stored in the database. The key comes from settings
(ENCRYPTION_KEY). Functions degrade gracefully:

  * If no key is configured, `encrypt`/`decrypt` raise CryptoNotConfigured
    so callers can surface a clear setup message.
  * `is_configured()` lets the UI disable features that need encryption.

Encrypted values are tagged with an "enc:v1:" prefix so we can detect
whether a stored value is encrypted (helps migration / mixed data).
"""

from __future__ import annotations

from functools import lru_cache

from app.config import settings

_PREFIX = "enc:v1:"


class CryptoNotConfigured(RuntimeError):
    """Raised when encryption is requested but ENCRYPTION_KEY is unset/invalid."""


@lru_cache(maxsize=1)
def _fernet():
    """Return a cached Fernet instance, or raise CryptoNotConfigured."""
    key = (settings.encryption_key or "").strip()
    if not key:
        raise CryptoNotConfigured(
            "ENCRYPTION_KEY belum diatur. Jalankan: python generate_key.py"
        )
    try:
        from cryptography.fernet import Fernet

        return Fernet(key.encode("utf-8"))
    except ImportError as exc:  # pragma: no cover
        raise CryptoNotConfigured(
            "Library 'cryptography' belum terpasang (pip install cryptography)."
        ) from exc
    except (ValueError, TypeError) as exc:
        raise CryptoNotConfigured(
            "ENCRYPTION_KEY tidak valid (harus Fernet key urlsafe base64)."
        ) from exc


def is_configured() -> bool:
    """Return True if encryption is usable."""
    try:
        _fernet()
        return True
    except CryptoNotConfigured:
        return False


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return a prefixed token.

    Raises:
        CryptoNotConfigured: if encryption is not configured.
    """
    if plaintext is None:
        plaintext = ""
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return _PREFIX + token


def is_encrypted(value: str) -> bool:
    """Return True if a stored value looks encrypted."""
    return isinstance(value, str) and value.startswith(_PREFIX)


def decrypt(value: str) -> str:
    """Decrypt a prefixed token back to plaintext.

    If the value is not encrypted (no prefix), it is returned unchanged so
    legacy/plaintext values keep working.

    Raises:
        CryptoNotConfigured: if the value is encrypted but no key is set.
    """
    if not is_encrypted(value):
        return value or ""
    token = value[len(_PREFIX):]
    try:
        from cryptography.fernet import InvalidToken

        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except CryptoNotConfigured:
        raise
    except Exception as exc:  # InvalidToken or others
        raise CryptoNotConfigured(
            "Gagal mendekripsi nilai (ENCRYPTION_KEY berbeda atau data rusak)."
        ) from exc
