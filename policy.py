"""Authorization policy for the score portal."""

from __future__ import annotations

import store
from models.score import Score
from models.user import User


def user_can_edit_maestro_config(user: User, maestro_username: str) -> bool:
    if user.is_admin():
        return True
    if user.is_maestro():
        return user.username == maestro_username.strip().lower()
    return False


def user_can_upload_to_library(user: User, library_id: str) -> bool:
    if user.is_admin():
        return False
    if user.is_singer():
        return library_id == user.id
    if user.is_maestro():
        return library_id == store.GLOBAL_LIBRARY_ID
    return False


def user_can_manage_folders_in_library(user: User, library_id: str) -> bool:
    if user.is_admin():
        return False
    if user.is_maestro():
        return True
    return user.is_singer() and library_id == user.id


def library_panel_capabilities(user: User, library_id: str) -> dict:
    return {
        "can_upload": user_can_upload_to_library(user, library_id),
        "can_manage_folders": user_can_manage_folders_in_library(user, library_id),
        "is_choir": user.is_choir(),
        "read_only": user.is_admin(),
    }


def user_can_edit_score(user: User, score: Score) -> bool:
    if user.is_admin():
        return False
    if user.is_maestro():
        return True
    return score.owner_id == user.id


def user_can_edit_score_year(user: User) -> bool:
    return user.is_maestro()


def user_can_view_score(user: User, score: Score, library_id: str) -> bool:
    if user.is_admin():
        return store.current_maestro_data() is not None
    if user.is_maestro():
        return True
    if score.owner_id == user.id:
        return True
    if not score.id:
        return False
    return store.library_has_score(library_id, score.id)


def user_can_set_score_folder(user: User, score: Score, library_id: str) -> bool:
    if user.is_admin():
        return False
    if not score.id or not store.library_has_score(library_id, score.id):
        return False
    return user_can_manage_folders_in_library(user, library_id)


def user_can_hard_delete_score(user: User, score: Score, library_id: str | None = None) -> bool:
    if user.is_admin():
        return False
    if user.is_maestro():
        lib_id = library_id or store.GLOBAL_LIBRARY_ID
        return lib_id == store.GLOBAL_LIBRARY_ID
    if not score.id or score.owner_id != user.id or score.owner_id == store.SYSTEM_OWNER_ID:
        return False
    if store.library_has_score(store.GLOBAL_LIBRARY_ID, score.id):
        return False
    if not store.library_has_score(user.id, score.id):
        return False
    return not store.score_shared_beyond_owner(score.id, score.owner_id)


def user_can_remove_score(user: User, score: Score, library_id: str | None = None) -> bool:
    if user.is_admin():
        return False
    if user.is_maestro():
        return True
    lib_id = library_id or user.id
    if user_can_hard_delete_score(user, score, lib_id):
        return True
    if not score.id:
        return False
    return store.library_has_score(lib_id, score.id)


def user_can_assign_scores(user: User) -> bool:
    return user.is_maestro()


def user_owns_sub_account(actor: User, target: User) -> bool:
    if not actor.is_maestro():
        return False
    return target.maestro_username == actor.id


def admin_can_view_maestro(actor: User, maestro_username: str) -> bool:
    if not actor.is_admin():
        return False
    owner = store.get_user_by_username(maestro_username)
    return bool(owner and owner.is_maestro())


def admin_can_preview_user(admin: User, target: User) -> bool:
    if not admin.is_admin():
        return False
    return target.is_maestro()
