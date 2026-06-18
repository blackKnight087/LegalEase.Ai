"""Field-level encryption at rest (Fernet). Optional — set DATA_ENCRYPTION_KEY in production."""
from __future__ import annotations

import os
from typing import Optional

_PREFIX = "enc:v1:"


def encryption_enabled() -> bool:
    return bool((os.getenv("DATA_ENCRYPTION_KEY") or "").strip())


def _fernet():
    key = (os.getenv("DATA_ENCRYPTION_KEY") or "").strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet

        return Fernet(key.encode("utf-8") if not key.startswith("gAAAA") else key)
    except Exception:
        return None


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string for DB storage. Passthrough if encryption disabled."""
    if not plaintext:
        return plaintext
    f = _fernet()
    if f is None:
        return plaintext
    token = f.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_field(value: str) -> str:
    """Decrypt a stored value. Returns input unchanged if not encrypted."""
    if not value or not value.startswith(_PREFIX):
        return value
    f = _fernet()
    if f is None:
        raise RuntimeError("DATA_ENCRYPTION_KEY required to decrypt protected fields")
    token = value[len(_PREFIX) :]
    return f.decrypt(token.encode("ascii")).decode("utf-8")


def generate_encryption_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode("ascii")
