"""Library and folder models."""

from __future__ import annotations

from typing import Any

import constants as c
from models.base import JsonModel


class Folder(JsonModel):
    """Folder node within a library."""

    def __init__(self, folder_id: str, name: str, parent_id: str = c.ROOT_FOLDER_ID):
        self._id = folder_id
        self._name = name
        self._parent_id = parent_id

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def parent_id(self) -> str:
        return self._parent_id

    @parent_id.setter
    def parent_id(self, value: str) -> None:
        self._parent_id = value

    def is_root(self) -> bool:
        return self.id == c.ROOT_FOLDER_ID

    def to_dict(self) -> dict[str, Any]:
        data = {"id": self.id, "name": self.name}
        if not self.is_root():
            data[c.FOLDER_PARENT_KEY] = self.parent_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Folder:
        return cls(
            data["id"],
            data.get("name", ""),
            data.get(c.FOLDER_PARENT_KEY, c.ROOT_FOLDER_ID),
        )


class Library(JsonModel):
    """Score library with folder tree and membership."""

    def __init__(
        self,
        library_id: str,
        folders: list[Folder] | None = None,
        score_folders: dict[str, str] | None = None,
        score_order: list[str] | None = None,
        display_name: str = "",
        owner_id: str = "",
    ):
        self._library_id = library_id
        self._folders = list(folders or [])
        self._score_folders = dict(score_folders or {})
        self._score_order = list(score_order or [])
        self._display_name = display_name
        self._owner_id = owner_id

    @property
    def library_id(self) -> str:
        return self._library_id

    @library_id.setter
    def library_id(self, value: str) -> None:
        self._library_id = value

    @property
    def folders(self) -> list[Folder]:
        return self._folders

    @folders.setter
    def folders(self, value: list[Folder]) -> None:
        self._folders = list(value)

    @property
    def score_folders(self) -> dict[str, str]:
        return self._score_folders

    @property
    def score_order(self) -> list[str]:
        return self._score_order

    @score_order.setter
    def score_order(self, value: list[str]) -> None:
        self._score_order = list(value)

    @property
    def display_name(self) -> str:
        return self._display_name

    @display_name.setter
    def display_name(self, value: str) -> None:
        self._display_name = value

    @property
    def owner_id(self) -> str:
        return self._owner_id

    @owner_id.setter
    def owner_id(self, value: str) -> None:
        self._owner_id = value

    def folder_by_id(self, folder_id: str) -> Folder | None:
        for folder in self.folders:
            if folder.id == folder_id:
                return folder
        return None

    def has_score(self, score_id: str) -> bool:
        return score_id in self.score_order

    def to_dict(self) -> dict[str, Any]:
        data = {
            "library_id": self.library_id,
            "folders": [folder.to_dict() for folder in self.folders],
            "score_folders": self.score_folders,
            "score_order": self.score_order,
        }
        if self.display_name:
            data["display_name"] = self.display_name
        if self.owner_id:
            data["owner_id"] = self.owner_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Library:
        folders = [Folder.from_dict(entry) for entry in data.get("folders", [])]
        return cls(
            data.get("library_id", ""),
            folders,
            dict(data.get("score_folders", {})),
            list(data.get("score_order", [])),
            data.get("display_name", ""),
            data.get("owner_id", ""),
        )
