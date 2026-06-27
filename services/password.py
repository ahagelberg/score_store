"""Password encryption and verification."""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

import constants as c
from models.user import User


def storage_secret() -> str:
    return os.environ.get("SECRET_KEY", "dev-change-me-in-production")


def _fernet(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def is_encrypted_password(stored: str) -> bool:
    return stored.startswith(c.PASSWORD_ENCRYPT_PREFIX)


def encrypt_stored_password(plain: str, secret: str) -> str:
    token = _fernet(secret).encrypt(plain.encode("utf-8")).decode("ascii")
    return c.PASSWORD_ENCRYPT_PREFIX + token


def decrypt_stored_password(stored: str, secret: str) -> str:
    if not is_encrypted_password(stored):
        raise ValueError("Password is not encrypted")
    token = stored[len(c.PASSWORD_ENCRYPT_PREFIX):].encode("ascii")
    return _fernet(secret).decrypt(token).decode("utf-8")


def set_password(user: User, password: str, secret: str) -> None:
    if user.uses_encrypted_password():
        user.password = encrypt_stored_password(password, secret)
    else:
        user.password = password


def finalize_role(user: User, secret: str) -> None:
    stored = user.password
    if not stored:
        return
    if user.uses_encrypted_password():
        if not is_encrypted_password(stored):
            user.password = encrypt_stored_password(stored, secret)
    elif is_encrypted_password(stored):
        user.password = ""


def password_for_display(user: User) -> str:
    if user.uses_encrypted_password():
        return ""
    stored = user.password or ""
    if is_encrypted_password(stored):
        return ""
    return stored


def verify_password(user: User, password: str, secret: str) -> bool:
    stored = user.password
    if not stored:
        return False
    if is_encrypted_password(stored):
        try:
            return decrypt_stored_password(stored, secret) == password
        except InvalidToken:
            return False
    return stored == password
