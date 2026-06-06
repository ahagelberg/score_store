"""Authorization policy for the score portal."""

import store

SINGER_ROLE = "singer"
CHOIR_ROLE = "choir"


def user_role(user: dict) -> str:
    return user.get("role", "")


def is_maestro(user: dict) -> bool:
    return user_role(user) == store.MAESTRO_ROLE


def is_singer(user: dict) -> bool:
    return user_role(user) == SINGER_ROLE


def is_choir(user: dict) -> bool:
    return user_role(user) == CHOIR_ROLE


def user_can_upload_to_library(user: dict, library_id: str) -> bool:
    if is_singer(user):
        return library_id == user["id"]
    if is_maestro(user):
        return library_id == store.GLOBAL_LIBRARY_ID
    return False


def user_can_manage_folders_in_library(user: dict, library_id: str) -> bool:
    if is_maestro(user):
        return True
    return is_singer(user) and library_id == user["id"]


def user_can_manage_library(user: dict, library_id: str) -> bool:
    return user_can_upload_to_library(user, library_id)


def library_panel_capabilities(user: dict, library_id: str) -> dict:
    return {
        "can_upload": user_can_upload_to_library(user, library_id),
        "can_manage_folders": user_can_manage_folders_in_library(user, library_id),
        "is_choir": is_choir(user),
    }


def user_can_edit_score(user: dict, meta: dict) -> bool:
    if is_maestro(user):
        return True
    return meta.get("owner_id") == user["id"]


def user_can_edit_score_year(user: dict) -> bool:
    return is_maestro(user)


def user_can_view_score(user: dict, meta: dict, library_id: str) -> bool:
    """Whether user may view score in the given library browsing context."""
    if is_maestro(user):
        return True
    if meta.get("owner_id") == user["id"]:
        return True
    sid = meta.get("id")
    if not sid:
        return False
    return store.library_has_score(library_id, sid)


def user_can_set_score_folder(user: dict, meta: dict, library_id: str) -> bool:
    score_id = meta.get("id")
    if not score_id or not store.library_has_score(library_id, score_id):
        return False
    return user_can_manage_folders_in_library(user, library_id)


def user_can_hard_delete_score(user: dict, meta: dict, library_id: str | None = None) -> bool:
    if is_maestro(user):
        lib_id = library_id or store.GLOBAL_LIBRARY_ID
        return lib_id == store.GLOBAL_LIBRARY_ID
    score_id = meta.get("id")
    owner_id = meta.get("owner_id")
    if not score_id or owner_id != user["id"] or owner_id == store.SYSTEM_OWNER_ID:
        return False
    if store.library_has_score(store.GLOBAL_LIBRARY_ID, score_id):
        return False
    if not store.library_has_score(user["id"], score_id):
        return False
    return not store.score_shared_beyond_owner(score_id, owner_id)


def user_can_remove_score(user: dict, meta: dict, library_id: str | None = None) -> bool:
    if is_maestro(user):
        return True
    lib_id = library_id or user["id"]
    if user_can_hard_delete_score(user, meta, lib_id):
        return True
    score_id = meta.get("id")
    if not score_id:
        return False
    return store.library_has_score(lib_id, score_id)


def user_can_assign_scores(user: dict) -> bool:
    return is_maestro(user)
