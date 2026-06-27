"""Public persistence API — domain models with JSON serialization."""

from pathlib import Path

from constants import *
from scope import (
    activate_maestro_data,
    current_maestro_data,
    maestro_data_scope,
    require_maestro_data,
)
import paths
from paths import (
    DATA_DIR,
    USERS_PATH,
    default_data_dir,
    default_setup_data_dir_display,
    ensure_maestro_data_dirs,
    libraries_dir,
    library_path,
    maestro_config_path,
    maestro_data_dir,
    maestro_theme_path,
    maestro_users_path,
    reconfigure_data_dir,
    reload_data_dir_from_instance,
    resolve_data_dir,
    save_instance_config,
    score_dir,
    score_files_dir,
    score_meta_path,
    scores_dir,
    stored_file_path,
    user_notes_dir,
    user_notes_path,
    validate_score_id,
    validate_stored_name,
)
from models.library import Folder, Library
from models.maestro_config import MaestroConfig
from models.score import Score, ScoreFile
from models.user import AdminUser, ChoirUser, MaestroUser, SingerUser, User, user_from_dict
from models.user_notes import UserNotes
from repositories.library_repository import LibraryRepository
from repositories.notes_repository import NotesRepository
from repositories.score_repository import ScoreRepository
from repositories.user_repository import UserRepository
from services import password as password_service

_user_repo = UserRepository()
_score_repo = ScoreRepository()
_library_repo = LibraryRepository(_user_repo)
_notes_repo = NotesRepository()

from persistence import engine as _persistence
from persistence.engine import *  # noqa: E402,F403


def _score_payload(score: Score | dict) -> dict:
    return score.to_dict() if isinstance(score, Score) else score


def score_subtitle_line(score: Score | dict) -> str:
    return _persistence.score_subtitle_line(_score_payload(score))


def get_main_file(score: Score | dict) -> dict | None:
    if isinstance(score, Score):
        main = score.main_file()
        return main.to_dict() if main else None
    return _persistence.get_main_file(score)


def file_display_name(score: Score | dict, file_id: str) -> str:
    return _persistence.file_display_name(_score_payload(score), file_id)


def file_download_name(file_entry: dict) -> str:
    return _persistence.file_download_name(file_entry)


def aux_file_type_label(file_entry: ScoreFile | dict) -> str:
    payload = file_entry.to_dict() if isinstance(file_entry, ScoreFile) else file_entry
    return _persistence.aux_file_type_label(payload)


def library_folder_ids(library: Library | dict) -> set[str]:
    if isinstance(library, Library):
        return {folder.id for folder in library.folders}
    return _persistence.library_folder_ids(library)


def build_folder_tree(library: Library | dict) -> dict:
    payload = library.to_dict() if isinstance(library, Library) else library
    return _persistence.build_folder_tree(payload)


def create_score_from_upload(
    library_id: str,
    folder_id: str,
    upload,
    metadata: dict,
    owner_id: str,
) -> dict:
    meta = _persistence.create_score_from_upload(
        library_id, folder_id, upload, metadata, owner_id
    )
    return Score.from_dict(meta).to_dict()


def update_score_metadata(
    score_id: str,
    metadata: dict,
    *,
    allow_year: bool = False,
) -> dict:
    meta = _persistence.update_score_metadata(score_id, metadata, allow_year=allow_year)
    return Score.from_dict(meta).to_dict()


def split_file_to_new_score(
    src_id: str,
    file_id: str,
    library_id: str,
    folder_id: str,
    metadata: dict,
    owner_id: str,
) -> dict:
    meta = _persistence.split_file_to_new_score(
        src_id, file_id, library_id, folder_id, metadata, owner_id
    )
    return Score.from_dict(meta).to_dict()


def load_main_users() -> list[User]:
    return _user_repo.load_main()


def save_main_users(users: list[User]) -> None:
    _user_repo.save_main(users)


def load_maestro_sub_users(maestro_username: str) -> list[User]:
    return _user_repo.load_sub_accounts(maestro_username)


def save_maestro_sub_users(maestro_username: str, users: list[User]) -> None:
    _user_repo.save_sub_accounts(maestro_username, users)


def load_users() -> list[User]:
    return _user_repo.load_all()


def save_users(users: list[User]) -> None:
    _user_repo.save_all(users)


def get_user_from_main(username: str) -> User | None:
    return _user_repo.get_from_main(username)


def get_user(username: str) -> User | None:
    return _user_repo.get_by_username(username)


def get_user_by_username(username: str) -> User | None:
    return _user_repo.get_by_username(username)


def upsert_user(user: User) -> None:
    _user_repo.upsert(user)


def remove_user_record(username: str) -> bool:
    return _user_repo.remove(username)


def get_maestro_accounts() -> list[MaestroUser]:
    return _user_repo.maestro_accounts()


def get_users_for_maestro(maestro_username: str) -> list[User]:
    return _user_repo.sub_accounts_for_maestro(maestro_username)


def maestro_folder_username(user: User) -> str:
    return _user_repo.maestro_folder_username(user)


def maestro_account_id(user: User) -> str:
    return _user_repo.maestro_account_username(user)


def score_owner_id(user: User) -> str:
    return user.score_owner_id()


def set_user_password(user: User, password: str, secret: str) -> None:
    password_service.set_password(user, password, secret)


def finalize_user_role(user: User, secret: str) -> None:
    password_service.finalize_role(user, secret)


def password_for_display(user: User) -> str:
    return password_service.password_for_display(user)


def verify_user_password(user: User, password: str, secret: str) -> bool:
    return password_service.verify_password(user, password, secret)


def create_sub_account(
    display_name: str,
    username: str,
    password: str,
    role: str,
    maestro_username: str,
    secret: str,
) -> User:
    return _user_repo.create_sub_account(
        display_name,
        username,
        password,
        role,
        maestro_username,
        secret,
        ensure_library=ensure_library,
    )


def delete_maestro_account(maestro_username: str) -> None:
    _user_repo.delete_maestro(maestro_username, delete_user_fn=delete_user)


def load_score_meta(score_id: str) -> Score | None:
    return _score_repo.load(score_id)


def save_score_meta(score_id: str, score: Score) -> None:
    _score_repo.save(score)


def list_all_score_ids() -> list[str]:
    return _score_repo.list_ids()


def default_library(library_id: str) -> Library:
    return _library_repo.default(library_id)


def load_library(library_id: str) -> Library:
    return _library_repo.load(library_id)


def save_library(library: Library) -> None:
    _library_repo.save(library)


def ensure_library(library_id: str) -> Library:
    return _library_repo.ensure(library_id)


def sync_library_metadata(library: Library) -> bool:
    return _library_repo.sync_metadata(library)


def normalize_library_folders(library: Library) -> bool:
    return _library_repo.normalize_folders(library)


def library_has_score(library_id: str, score_id: str) -> bool:
    return _library_repo.has_score(library_id, score_id)


def default_user_notes() -> UserNotes:
    return UserNotes()


def load_user_notes(username: str) -> UserNotes:
    return _notes_repo.load(username)


def save_user_notes(username: str, notes: UserNotes) -> None:
    _notes_repo.save(username, notes)


def get_score_notes(username: str, score_id: str) -> dict:
    return _notes_repo.score_notes(username, score_id)


def set_score_notes(username: str, score_id: str, score_notes: dict) -> None:
    _notes_repo.set_score_notes(username, score_id, score_notes)


def default_maestro_config(display_name: str) -> dict:
    return MaestroConfig(display_name).to_dict()


def save_maestro_config(maestro_username: str, config: dict) -> None:
    cfg = MaestroConfig.from_dict(config)
    if not cfg.site_title:
        user = get_user_by_username(maestro_username)
        cfg.site_title = user.display_name if user else maestro_username
    ensure_maestro_data_dirs(maestro_username)
    from json_io.json_store import JsonStore
    JsonStore.write_dict(maestro_config_path(maestro_username), cfg.to_dict())


def maestro_header_show_title(cfg: dict, has_logotype: bool) -> bool:
    return MaestroConfig.from_dict(cfg).header_show_title(has_logotype)


def scores_for_library_sorted(library_id: str, query: str, tag: str | None) -> list[Score]:
    return [
        Score.from_dict(entry)
        for entry in _persistence.scores_for_library_sorted(library_id, query, tag)
    ]


def rename_username(old_username: str, new_username: str) -> str:
    old = old_username.strip().lower()
    new = new_username.strip().lower()
    if not new:
        raise ValueError("Username is required")
    if old == new:
        return new
    if _user_repo.get_by_username(new):
        raise ValueError("Username taken")
    user = _user_repo.get_by_username(old)
    if not user:
        raise ValueError("User not found")
    lib_path = library_path(old)
    if lib_path.exists():
        library = _library_repo.load(old)
        library.library_id = new
        library.owner_id = new
        _library_repo.save(library)
        if lib_path.stem != new and lib_path.exists():
            lib_path.unlink()
    old_notes = user_notes_path(old)
    new_notes = user_notes_path(new)
    if old_notes.exists():
        new_notes.parent.mkdir(parents=True, exist_ok=True)
        old_notes.rename(new_notes)
    for sid in list_all_score_ids():
        score = _score_repo.load(sid)
        if not score:
            continue
        if score.owner_id == old:
            score.owner_id = new
            _score_repo.save(score)
    user.username = new
    return new


def complete_setup(username: str, password: str, data_dir: Path, secret: str) -> User:
    if len(password) < SETUP_PASSWORD_MIN_LEN:
        raise ValueError(f"Password must be at least {SETUP_PASSWORD_MIN_LEN} characters")
    uname = username.strip().lower()
    if not uname:
        raise ValueError("Username is required")
    resolved = resolve_data_dir(str(data_dir))
    save_instance_config(resolved)
    reconfigure_data_dir(resolved)
    user = AdminUser("Admin", uname)
    set_user_password(user, password, secret)
    save_main_users([user])
    return user


def bootstrap_admin(secret: str) -> User | None:
    username = os.environ.get("BOOTSTRAP_ADMIN_USER", "").strip().lower()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username or not password:
        return None
    if has_admin():
        return None
    user = AdminUser("Admin", username)
    set_user_password(user, password, secret)
    upsert_user(user)
    return user


def create_maestro_account(display_name: str, username: str, password: str, secret: str) -> MaestroUser:
    uname = username.strip().lower()
    if not uname:
        raise ValueError("Username is required")
    if get_user_by_username(uname):
        raise ValueError("Username taken")
    if maestro_data_dir(uname).exists():
        raise ValueError("Maestro folder exists")
    user = MaestroUser(display_name.strip() or uname, uname)
    set_user_password(user, password, secret)
    upsert_user(user)
    ensure_maestro_data_dirs(uname)
    save_maestro_config(uname, default_maestro_config(user.display_name))
    write_default_maestro_theme(uname)
    prev = current_maestro_data()
    try:
        activate_maestro_data(uname)
        ensure_library(GLOBAL_LIBRARY_ID)
    finally:
        activate_maestro_data(prev)
    return user

