"""User account models with role-specific subclasses."""

from __future__ import annotations

from typing import Any

import constants as c
from models.base import JsonModel


def _username_from_data(data: dict[str, Any]) -> str:
    return (data.get("username") or "").strip().lower()


class User(JsonModel):
    """Base user account; username is the canonical identity."""

    def __init__(
        self,
        display_name: str,
        username: str,
        role: str,
        password: str = "",
        maestro_username: str = "",
    ):
        self._display_name = display_name
        self._username = username.strip().lower()
        self._role = role
        self._password = password
        self._maestro_username = maestro_username.strip().lower() if maestro_username else ""

    @property
    def id(self) -> str:
        return self._username

    @property
    def display_name(self) -> str:
        return self._display_name

    @display_name.setter
    def display_name(self, value: str) -> None:
        self._display_name = value

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        self._username = value.strip().lower()

    @property
    def role(self) -> str:
        return self._role

    @role.setter
    def role(self, value: str) -> None:
        self._role = value

    @property
    def password(self) -> str:
        return self._password

    @password.setter
    def password(self, value: str) -> None:
        self._password = value

    @property
    def maestro_username(self) -> str:
        return self._maestro_username

    @maestro_username.setter
    def maestro_username(self, value: str) -> None:
        self._maestro_username = value.strip().lower() if value else ""

    def to_dict(self) -> dict[str, Any]:
        data = {
            "display_name": self.display_name,
            "username": self.username,
            "role": self.role,
        }
        if self.password:
            data["password"] = self.password
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, maestro_username: str = "") -> User:
        return user_from_dict(data, maestro_username=maestro_username)

    def score_owner_id(self) -> str:
        if self.role == c.MAESTRO_ROLE:
            return c.SYSTEM_OWNER_ID
        return self.id

    def uses_encrypted_password(self) -> bool:
        return self.role in c.ROLES_WITH_ENCRYPTED_PASSWORD

    def is_main_account(self) -> bool:
        return self.role in (c.ADMIN_ROLE, c.MAESTRO_ROLE)

    def is_sub_account(self) -> bool:
        return self.role in c.SUB_ACCOUNT_ROLES

    def is_admin(self) -> bool:
        return self.role == c.ADMIN_ROLE

    def is_maestro(self) -> bool:
        return self.role == c.MAESTRO_ROLE

    def is_singer(self) -> bool:
        return self.role == c.SINGER_ROLE

    def is_choir(self) -> bool:
        return self.role == c.CHOIR_ROLE


class AdminUser(User):
    """Platform administrator."""

    def __init__(self, display_name: str, username: str, password: str = ""):
        super().__init__(display_name, username, c.ADMIN_ROLE, password)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AdminUser:
        return cls(
            data.get("display_name", ""),
            _username_from_data(data),
            data.get("password", ""),
        )


class MaestroUser(User):
    """Maestro account owning a data folder."""

    def __init__(self, display_name: str, username: str, password: str = ""):
        super().__init__(display_name, username, c.MAESTRO_ROLE, password)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MaestroUser:
        return cls(
            data.get("display_name", ""),
            _username_from_data(data),
            data.get("password", ""),
        )


class SubAccountUser(User):
    """Singer or choir account under a maestro."""

    def __init__(
        self,
        display_name: str,
        username: str,
        role: str,
        maestro_username: str,
        password: str = "",
    ):
        super().__init__(display_name, username, role, password, maestro_username)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, maestro_username: str = "") -> SubAccountUser:
        role = data.get("role", c.SINGER_ROLE)
        if role == c.CHOIR_ROLE:
            return ChoirUser.from_dict(data, maestro_username=maestro_username)
        return SingerUser.from_dict(data, maestro_username=maestro_username)


class SingerUser(SubAccountUser):
    """Individual singer account."""

    def __init__(
        self,
        display_name: str,
        username: str,
        maestro_username: str,
        password: str = "",
    ):
        super().__init__(display_name, username, c.SINGER_ROLE, maestro_username, password)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, maestro_username: str = "") -> SingerUser:
        return cls(
            data.get("display_name", ""),
            _username_from_data(data),
            maestro_username,
            data.get("password", ""),
        )


class ChoirUser(SubAccountUser):
    """Choir account."""

    def __init__(
        self,
        display_name: str,
        username: str,
        maestro_username: str,
        password: str = "",
    ):
        super().__init__(display_name, username, c.CHOIR_ROLE, maestro_username, password)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, maestro_username: str = "") -> ChoirUser:
        return cls(
            data.get("display_name", ""),
            _username_from_data(data),
            maestro_username,
            data.get("password", ""),
        )


def user_from_dict(data: dict[str, Any], *, maestro_username: str = "") -> User:
    role = data.get("role", "")
    if role == c.ADMIN_ROLE:
        return AdminUser.from_dict(data)
    if role == c.MAESTRO_ROLE:
        return MaestroUser.from_dict(data)
    if role == c.CHOIR_ROLE:
        return ChoirUser.from_dict(data, maestro_username=maestro_username)
    if role == c.SINGER_ROLE:
        return SingerUser.from_dict(data, maestro_username=maestro_username)
    return User(
        data.get("display_name", ""),
        _username_from_data(data),
        role,
        data.get("password", ""),
        maestro_username,
    )
