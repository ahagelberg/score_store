"""Base type for JSON-serializable domain objects."""

from abc import ABC, abstractmethod
from typing import Any


class JsonModel(ABC):
    """Domain object that round-trips to JSON at the persistence boundary only."""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]):
        raise NotImplementedError
