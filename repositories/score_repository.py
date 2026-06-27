"""Score metadata persistence."""

from __future__ import annotations

import paths
from json_io.json_store import JsonStore
from models.score import Score


class ScoreRepository:
    """Load and save score metadata documents."""

    def load(self, score_id: str) -> Score | None:
        try:
            path = paths.score_meta_path(score_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        return Score.from_dict(JsonStore.read_dict(path))

    def save(self, score: Score) -> None:
        JsonStore.write_dict(paths.score_meta_path(score.id), score.to_dict())

    def save_dict(self, score_id: str, meta: dict) -> None:
        JsonStore.write_dict(paths.score_meta_path(score_id), meta)

    def load_dict(self, score_id: str) -> dict | None:
        score = self.load(score_id)
        return score.to_dict() if score else None

    def list_ids(self) -> list[str]:
        root = paths.scores_dir()
        if not root.exists():
            return []
        return [
            entry.name for entry in root.iterdir()
            if entry.is_dir() and (entry / "meta.json").exists()
        ]

    def exists(self, score_id: str) -> bool:
        try:
            return paths.score_meta_path(score_id).exists()
        except ValueError:
            return False
