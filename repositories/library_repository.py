"""Library persistence."""

from __future__ import annotations

import constants as c
import paths
from json_io.json_store import JsonStore
from models.library import Folder, Library


class LibraryRepository:
    """Load and save library documents."""

    def __init__(self, user_repo):
        self._users = user_repo

    def _is_user_library(self, library_id: str) -> bool:
        if library_id == c.GLOBAL_LIBRARY_ID:
            return False
        user = self._users.get_by_username(library_id)
        return user is not None and user.is_sub_account()

    def default(self, library_id: str) -> Library:
        folders = [Folder(c.ROOT_FOLDER_ID, c.ROOT_FOLDER_DISPLAY_NAME)]
        display_name = ""
        owner_id = ""
        if library_id == c.GLOBAL_LIBRARY_ID:
            display_name = c.GLOBAL_LIBRARY_DISPLAY_NAME
        elif self._is_user_library(library_id):
            owner_id = library_id
            user = self._users.get_by_username(library_id)
            display_name = user.display_name if user else library_id
        return Library(library_id, folders, {}, [], display_name, owner_id)

    def load(self, library_id: str) -> Library:
        library = Library.from_dict(
            JsonStore.read_dict(paths.library_path(library_id))
        )
        if not library.library_id:
            library.library_id = library_id
        self.normalize_folders(library)
        return library

    def save(self, library: Library) -> None:
        self.sync_metadata(library)
        payload = library.to_dict()
        payload.pop("file_aliases", None)
        JsonStore.write_dict(paths.library_path(library.library_id), payload)

    def ensure(self, library_id: str) -> Library:
        path = paths.library_path(library_id)
        if path.exists():
            return self.load(library_id)
        library = self.default(library_id)
        self.save(library)
        return library

    def sync_metadata(self, library: Library) -> bool:
        changed = False
        if library.library_id == c.GLOBAL_LIBRARY_ID:
            if library.display_name != c.GLOBAL_LIBRARY_DISPLAY_NAME:
                library.display_name = c.GLOBAL_LIBRARY_DISPLAY_NAME
                changed = True
        elif self._is_user_library(library.library_id):
            if library.owner_id != library.library_id:
                library.owner_id = library.library_id
                changed = True
            user = self._users.get_by_username(library.library_id)
            expected = user.display_name if user else library.library_id
            if library.display_name != expected:
                library.display_name = expected
                changed = True
        return changed

    def normalize_folders(self, library: Library) -> bool:
        changed = False
        if not library.folders:
            library.folders = [Folder(c.ROOT_FOLDER_ID, c.ROOT_FOLDER_DISPLAY_NAME)]
            return True
        folder_ids = {folder.id for folder in library.folders}
        if c.ROOT_FOLDER_ID not in folder_ids:
            library.folders.insert(0, Folder(c.ROOT_FOLDER_ID, c.ROOT_FOLDER_DISPLAY_NAME))
            folder_ids.add(c.ROOT_FOLDER_ID)
            changed = True
        for folder in library.folders:
            if folder.is_root():
                continue
            if folder.parent_id not in folder_ids or folder.parent_id == folder.id:
                folder.parent_id = c.ROOT_FOLDER_ID
                changed = True
        return changed

    def has_score(self, library_id: str, score_id: str) -> bool:
        return self.load(library_id).has_score(score_id)
