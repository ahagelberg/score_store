"""Per-user score annotation notes model."""

from __future__ import annotations

from typing import Any

from models.base import JsonModel


class UserNotes(JsonModel):
    """Nested annotation data keyed by score and file."""

    def __init__(self, scores: dict[str, dict] | None = None):
        self.scores = dict(scores or {})

    def score_entry(self, score_id: str) -> dict:
        entry = self.scores.get(score_id)
        if not isinstance(entry, dict):
            return {"files": {}}
        entry.setdefault("files", {})
        return entry

    def set_score_entry(self, score_id: str, score_notes: dict) -> None:
        files = score_notes.get("files") if isinstance(score_notes, dict) else None
        if not isinstance(files, dict) or not files:
            self.scores.pop(score_id, None)
            return
        self.scores[score_id] = {"files": files}

    def to_dict(self) -> dict[str, Any]:
        return {"scores": self.scores}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserNotes:
        scores = data.get("scores", {})
        return cls(dict(scores) if isinstance(scores, dict) else {})
