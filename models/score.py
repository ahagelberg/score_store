"""Score and score-file models."""

from __future__ import annotations

from typing import Any

import constants as c
from models.base import JsonModel


class ScoreFile(JsonModel):
    """A main or auxiliary file attached to a score."""

    def __init__(
        self,
        file_id: str,
        role: str,
        name: str,
        media: str,
        stored_name: str = "",
        url: str = "",
    ):
        self._id = file_id
        self._role = role
        self._name = name
        self._media = media
        self._stored_name = stored_name
        self._url = url

    @property
    def id(self) -> str:
        return self._id

    @property
    def role(self) -> str:
        return self._role

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def media(self) -> str:
        return self._media

    @property
    def stored_name(self) -> str:
        return self._stored_name

    @stored_name.setter
    def stored_name(self, value: str) -> None:
        self._stored_name = value

    @property
    def url(self) -> str:
        return self._url

    @url.setter
    def url(self, value: str) -> None:
        self._url = value

    def is_main(self) -> bool:
        return self.role == "main"

    def is_youtube(self) -> bool:
        return self.media == "youtube"

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "role": self.role,
            "name": self.name,
            "media": self.media,
        }
        if self.stored_name:
            data["stored_name"] = self.stored_name
        if self.url:
            data["url"] = self.url
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScoreFile:
        return cls(
            data["id"],
            data.get("role", "aux"),
            data.get("name", ""),
            data.get("media", "file"),
            data.get("stored_name", ""),
            data.get("url", ""),
        )


class Score(JsonModel):
    """Score metadata and attached files."""

    def __init__(
        self,
        score_id: str,
        title: str,
        owner_id: str,
        files: list[ScoreFile] | None = None,
        composer: str = "",
        arranger: str = "",
        description: str = "",
        tags: list[str] | None = None,
        year: str = "",
        main_content_hash: str = "",
        created_at: str = "",
    ):
        self._id = score_id
        self._title = title
        self._owner_id = owner_id
        self._files = list(files or [])
        self._composer = composer
        self._arranger = arranger
        self._description = description
        self._tags = list(tags or [])
        self._year = year
        self._main_content_hash = main_content_hash
        self._created_at = created_at

    @property
    def id(self) -> str:
        return self._id

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        self._title = value

    @property
    def owner_id(self) -> str:
        return self._owner_id

    @owner_id.setter
    def owner_id(self, value: str) -> None:
        self._owner_id = value

    @property
    def files(self) -> list[ScoreFile]:
        return self._files

    @property
    def composer(self) -> str:
        return self._composer

    @composer.setter
    def composer(self, value: str) -> None:
        self._composer = value

    @property
    def arranger(self) -> str:
        return self._arranger

    @arranger.setter
    def arranger(self, value: str) -> None:
        self._arranger = value

    @property
    def description(self) -> str:
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        self._description = value

    @property
    def tags(self) -> list[str]:
        return self._tags

    @tags.setter
    def tags(self, value: list[str]) -> None:
        self._tags = list(value)

    @property
    def year(self) -> str:
        return self._year

    @year.setter
    def year(self, value: str) -> None:
        self._year = value

    @property
    def main_content_hash(self) -> str:
        return self._main_content_hash

    @main_content_hash.setter
    def main_content_hash(self, value: str) -> None:
        self._main_content_hash = value

    @property
    def created_at(self) -> str:
        return self._created_at

    @created_at.setter
    def created_at(self, value: str) -> None:
        self._created_at = value

    def main_file(self) -> ScoreFile | None:
        for entry in self.files:
            if entry.is_main():
                return entry
        return None

    def file_by_id(self, file_id: str) -> ScoreFile | None:
        for entry in self.files:
            if entry.id == file_id:
                return entry
        return None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "title": self.title,
            "composer": self.composer,
            "arranger": self.arranger,
            "description": self.description,
            "tags": self.tags,
            "year": self.year,
            "owner_id": self.owner_id,
            "files": [entry.to_dict() for entry in self.files],
        }
        if self.main_content_hash:
            data[c.MAIN_CONTENT_HASH_META_KEY] = self.main_content_hash
        if self.created_at:
            data["created_at"] = self.created_at
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Score:
        files = [ScoreFile.from_dict(entry) for entry in data.get("files", [])]
        return cls(
            data.get("id", ""),
            data.get("title", ""),
            data.get("owner_id", ""),
            files,
            data.get("composer", ""),
            data.get("arranger", ""),
            data.get("description", ""),
            list(data.get("tags", [])),
            data.get("year", ""),
            data.get(c.MAIN_CONTENT_HASH_META_KEY, ""),
            data.get("created_at", ""),
        )
