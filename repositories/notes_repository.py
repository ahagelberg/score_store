"""User notes persistence."""

import paths
from json_io.json_store import JsonStore
from models.user_notes import UserNotes


class NotesRepository:
    """Load and save per-user annotation files."""

    def load(self, user_id: str) -> UserNotes:
        return UserNotes.from_dict(JsonStore.read_dict(paths.user_notes_path(user_id)))

    def save(self, user_id: str, notes: UserNotes) -> None:
        JsonStore.write_dict(paths.user_notes_path(user_id), notes.to_dict())

    def score_notes(self, user_id: str, score_id: str) -> dict:
        return self.load(user_id).score_entry(score_id)

    def set_score_notes(self, user_id: str, score_id: str, score_notes: dict) -> None:
        notes = self.load(user_id)
        notes.set_score_entry(score_id, score_notes)
        self.save(user_id, notes)
