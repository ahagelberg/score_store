"""Score and library operations (implementation layer)."""

import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import constants as c
import paths
from json_io.json_store import JsonStore
from scope import (
    activate_maestro_data,
    current_maestro_data,
    maestro_data_scope,
    require_maestro_data,
)

APP_ROOT = c.APP_ROOT
INSTANCE_DIR = c.INSTANCE_DIR
INSTANCE_CONFIG_PATH = c.INSTANCE_CONFIG_PATH
DEFAULT_DATA_DIR_NAME = c.DEFAULT_DATA_DIR_NAME
DEFAULT_ADMIN_USERNAME = c.DEFAULT_ADMIN_USERNAME
MAESTRO_USERS_FILENAME = c.MAESTRO_USERS_FILENAME
SETUP_PASSWORD_MIN_LEN = c.SETUP_PASSWORD_MIN_LEN
MAESTRO_CONFIG_FILENAME = c.MAESTRO_CONFIG_FILENAME
DEFAULT_SHOW_SITE_TITLE = c.DEFAULT_SHOW_SITE_TITLE
MAESTRO_THEME_FILENAME = c.MAESTRO_THEME_FILENAME
MAESTRO_ASSETS_DIRNAME = c.MAESTRO_ASSETS_DIRNAME
LOGOTYPE_STORED_BASENAME = c.LOGOTYPE_STORED_BASENAME
LOGOTYPE_EXTENSIONS = c.LOGOTYPE_EXTENSIONS
MAIN_EXTENSIONS = c.MAIN_EXTENSIONS
AUX_EXTENSIONS = c.AUX_EXTENSIONS
YOUTUBE_DOMAINS = c.YOUTUBE_DOMAINS
YOUTUBE_OEMBED_URL = c.YOUTUBE_OEMBED_URL
YOUTUBE_OEMBED_TIMEOUT_SEC = c.YOUTUBE_OEMBED_TIMEOUT_SEC
YOUTUBE_DEFAULT_NAME = c.YOUTUBE_DEFAULT_NAME
ROOT_FOLDER_ID = c.ROOT_FOLDER_ID
ROOT_FOLDER_DISPLAY_NAME = c.ROOT_FOLDER_DISPLAY_NAME
GLOBAL_LIBRARY_DISPLAY_NAME = c.GLOBAL_LIBRARY_DISPLAY_NAME
LIBRARY_VIEW_LIST = c.LIBRARY_VIEW_LIST
LIBRARY_VIEW_FOLDER = c.LIBRARY_VIEW_FOLDER
DEFAULT_LIBRARY_VIEW = c.DEFAULT_LIBRARY_VIEW
FILE_NAME_MAX_LEN = c.FILE_NAME_MAX_LEN
TAG_MAX_LEN = c.TAG_MAX_LEN
GLOBAL_LIBRARY_ID = c.GLOBAL_LIBRARY_ID
SYSTEM_OWNER_ID = c.SYSTEM_OWNER_ID
ADMIN_ROLE = c.ADMIN_ROLE
MAESTRO_ROLE = c.MAESTRO_ROLE
PASSWORD_ENCRYPT_PREFIX = c.PASSWORD_ENCRYPT_PREFIX
ROLES_WITH_ENCRYPTED_PASSWORD = c.ROLES_WITH_ENCRYPTED_PASSWORD
SUB_ACCOUNT_ROLES = c.SUB_ACCOUNT_ROLES
DEFAULT_MAESTRO_THEME_CSS = c.DEFAULT_MAESTRO_THEME_CSS
SCORE_ID_PREFIX = c.SCORE_ID_PREFIX
FILE_ID_PREFIX = c.FILE_ID_PREFIX
SCORE_RANDOM_ID_BYTES = c.SCORE_RANDOM_ID_BYTES
FILE_RANDOM_ID_BYTES = c.FILE_RANDOM_ID_BYTES
STORED_NAME_RANDOM_BYTES = c.STORED_NAME_RANDOM_BYTES
STARTUP_LOCK_FILENAME = c.STARTUP_LOCK_FILENAME
DISK_USAGE_CACHE_TTL_SEC = c.DISK_USAGE_CACHE_TTL_SEC
MAIN_CONTENT_HASH_META_KEY = c.MAIN_CONTENT_HASH_META_KEY
FILE_HASH_READ_BYTES = c.FILE_HASH_READ_BYTES
BYTES_PER_SIZE_UNIT = c.BYTES_PER_SIZE_UNIT
SIZE_UNIT_LABELS = c.SIZE_UNIT_LABELS
SCORE_YEAR_PATTERN = c.SCORE_YEAR_PATTERN
SCORE_YEAR_MIN = c.SCORE_YEAR_MIN
SCORE_YEAR_MAX = c.SCORE_YEAR_MAX
UNSAFE_PATH_CHAR_PATTERN = c.UNSAFE_PATH_CHAR_PATTERN
WHITESPACE_PATTERN = c.WHITESPACE_PATTERN
MULTI_SEP_PATTERN = c.MULTI_SEP_PATTERN
FOLDER_PARENT_KEY = c.FOLDER_PARENT_KEY
USER_NOTES_DIRNAME = c.USER_NOTES_DIRNAME

DATA_DIR = paths.DATA_DIR
USERS_PATH = paths.USERS_PATH

_startup_guard = threading.Lock()
_startup_done = False
_disk_usage_cache: dict[str, tuple[float, dict]] = {}
_disk_usage_cache_lock = threading.Lock()


def _read_json(path: Path, default):
    return JsonStore.read(path, default)


def _write_json(path: Path, data) -> None:
    JsonStore.write(path, data)


def maestro_data_dir(maestro_username: str) -> Path:
    return paths.maestro_data_dir(maestro_username)


def scores_dir() -> Path:
    return paths.scores_dir()


def libraries_dir() -> Path:
    return paths.libraries_dir()


def user_notes_dir() -> Path:
    return paths.user_notes_dir()


def user_notes_path(user_id: str) -> Path:
    return paths.user_notes_path(user_id)


def reconfigure_data_dir(data_dir: Path) -> Path:
    return paths.reconfigure_data_dir(data_dir)


def reload_data_dir_from_instance() -> Path:
    result = paths.reload_data_dir_from_instance()
    global DATA_DIR, USERS_PATH
    DATA_DIR = paths.DATA_DIR
    USERS_PATH = paths.USERS_PATH
    return result


def save_instance_config(data_dir: Path) -> None:
    paths.save_instance_config(data_dir)


def resolve_data_dir(path_str: str) -> Path:
    return paths.resolve_data_dir(path_str)


def default_setup_data_dir_display() -> str:
    return paths.default_setup_data_dir_display()


def default_data_dir() -> Path:
    return paths.default_data_dir()


def ensure_maestro_data_dirs(maestro_username: str) -> None:
    paths.ensure_maestro_data_dirs(maestro_username)


def maestro_users_path(maestro_username: str) -> Path:
    return paths.maestro_users_path(maestro_username)


def maestro_config_path(maestro_username: str) -> Path:
    return paths.maestro_config_path(maestro_username)


def maestro_theme_path(maestro_username: str) -> Path:
    return paths.maestro_theme_path(maestro_username)


def library_path(library_id: str) -> Path:
    return paths.library_path(library_id)


from persistence.score_paths import (  # noqa: E402
    score_dir,
    score_files_dir,
    score_meta_path,
    stored_file_path,
    validate_score_id,
    validate_stored_name,
)
from models.library import Library
from models.score import Score
from models.user import User, user_from_dict
from repositories.library_repository import LibraryRepository
from repositories.score_repository import ScoreRepository
from repositories.user_repository import UserRepository
from services import password as password_service

_user_repo = UserRepository()
_score_repo = ScoreRepository()
_library_repo = LibraryRepository(_user_repo)


def has_admin() -> bool:
    return any(user.is_admin() for user in _user_repo.load_main())


def env_bootstrap_configured() -> bool:
    return bool(os.environ.get("BOOTSTRAP_ADMIN_USER") and os.environ.get("BOOTSTRAP_ADMIN_PASSWORD"))


def needs_setup() -> bool:
    if has_admin():
        return False
    if env_bootstrap_configured():
        return False
    return True


def format_byte_size(num_bytes: int) -> str:
    size = float(max(num_bytes, 0))
    unit_index = 0
    last_index = len(SIZE_UNIT_LABELS) - 1
    while size >= BYTES_PER_SIZE_UNIT and unit_index < last_index:
        size /= BYTES_PER_SIZE_UNIT
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {SIZE_UNIT_LABELS[unit_index]}"
    return f"{size:.1f} {SIZE_UNIT_LABELS[unit_index]}"


def maestro_folder_size_bytes(maestro_username: str) -> int:
    base = maestro_data_dir(maestro_username)
    if not base.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(base):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def disk_usage_stats() -> dict:
    maestro_username = require_maestro_data()
    now = time.monotonic()
    with _disk_usage_cache_lock:
        cached = _disk_usage_cache.get(maestro_username)
        if cached and now - cached[0] < DISK_USAGE_CACHE_TTL_SEC:
            return cached[1]
    base = maestro_data_dir(maestro_username)
    base.mkdir(parents=True, exist_ok=True)
    used_bytes = maestro_folder_size_bytes(maestro_username)
    _total, _fs_used, free_bytes = shutil.disk_usage(DATA_DIR)
    stats = {
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "used_label": format_byte_size(used_bytes),
        "free_label": format_byte_size(free_bytes),
    }
    with _disk_usage_cache_lock:
        _disk_usage_cache[maestro_username] = (now, stats)
    return stats


def _score_exists(score_id: str) -> bool:
    try:
        return score_meta_path(score_id).exists()
    except ValueError:
        return False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _basename_only(filename: str) -> str:
    return Path(filename).name.replace("\\", "/").split("/")[-1]


def split_filename(filename: str) -> tuple[str, str]:
    name = _basename_only(filename)
    if not name or name in (".", ".."):
        return "file", ""
    dot = name.rfind(".")
    if dot > 0:
        return name[:dot], name[dot + 1 :].lower()
    return name, ""


def sanitize_stored_stem(text: str, max_len: int = FILE_NAME_MAX_LEN) -> str:
    text = _basename_only(text)
    text = UNSAFE_PATH_CHAR_PATTERN.sub("-", text)
    text = WHITESPACE_PATTERN.sub("-", text)
    text = MULTI_SEP_PATTERN.sub("-", text)
    text = text.strip(" .-")
    if len(text) > max_len:
        text = text[:max_len].rstrip(" .-")
    return text or "file"


def _slug(text: str, max_len: int = FILE_NAME_MAX_LEN) -> str:
    return sanitize_stored_stem(text.strip(), max_len)


def _unique_with_suffix(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def unique_id(label: str, taken: set[str], prefix: str = "") -> str:
    return _unique_with_suffix(f"{prefix}{_slug(label)}", taken)


def _random_hex_token(nbytes: int) -> str:
    return secrets.token_hex(nbytes)


def _random_hex_id(prefix: str, nbytes: int, taken: set[str]) -> str:
    while True:
        candidate = f"{prefix}{_random_hex_token(nbytes)}"
        if candidate not in taken:
            return candidate


def _existing_score_dir_names() -> set[str]:
    if not scores_dir().exists():
        return set()
    return {p.name for p in scores_dir().iterdir() if p.is_dir()}


def new_score_id(taken: set[str] | None = None) -> str:
    ids = taken if taken is not None else _existing_score_dir_names()
    return _random_hex_id(SCORE_ID_PREFIX, SCORE_RANDOM_ID_BYTES, ids)


def new_file_id(taken: set[str]) -> str:
    return _random_hex_id(FILE_ID_PREFIX, FILE_RANDOM_ID_BYTES, taken)


def new_stored_filename(ext: str, files_dir: Path) -> str:
    ext = (ext or "").strip().lower()
    taken = {p.name for p in files_dir.iterdir() if p.is_file()} if files_dir.exists() else set()
    while True:
        token = _random_hex_token(STORED_NAME_RANDOM_BYTES)
        name = f"{token}.{ext}" if ext else token
        if name not in taken:
            return name


def _run_startup_once(secret: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = DATA_DIR / STARTUP_LOCK_FILENAME
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            reload_data_dir_from_instance()
            bootstrap_admin(secret)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def ensure_data_ready(secret: str) -> bool:
    """One-shot startup and env bootstrap; safe under multi-worker WSGI."""
    global _startup_done
    with _startup_guard:
        if _startup_done:
            return needs_setup()
        _run_startup_once(secret)
        _startup_done = True
        return needs_setup()


def _digest_stream(read_fn) -> str:
    h = hashlib.sha256()
    while True:
        chunk = read_fn(FILE_HASH_READ_BYTES)
        if not chunk:
            break
        h.update(chunk)
    return h.hexdigest()


def _digest_file(path: Path) -> str:
    with open(path, "rb") as f:
        return _digest_stream(f.read)


def _digest_upload(upload_file) -> str:
    digest = _digest_stream(upload_file.read)
    upload_file.seek(0)
    return digest


def _main_file_content_hash(meta: dict) -> str | None:
    stored_hash = meta.get(MAIN_CONTENT_HASH_META_KEY)
    if stored_hash:
        return stored_hash
    main = get_main_file(meta)
    if not main or not main.get("stored_name"):
        return None
    try:
        path = stored_file_path(meta["id"], main["stored_name"])
    except ValueError:
        return None
    if not path.exists():
        return None
    return _digest_file(path)


def find_score_by_main_content_hash(digest: str) -> dict | None:
    for sid in list_all_score_ids():
        meta = load_score_meta(sid)
        if not meta:
            continue
        existing = _main_file_content_hash(meta)
        if existing != digest:
            continue
        if not meta.get(MAIN_CONTENT_HASH_META_KEY):
            meta[MAIN_CONTENT_HASH_META_KEY] = digest
            save_score_meta(sid, meta)
        return meta
    return None


def folder_by_id(lib: dict, folder_id: str) -> dict | None:
    for folder in lib.get("folders", []):
        if folder["id"] == folder_id:
            return folder
    return None


def folder_parent_id(folder: dict) -> str:
    return folder.get(FOLDER_PARENT_KEY, ROOT_FOLDER_ID)


def sibling_folder_ids(lib: dict, parent_id: str) -> set[str]:
    return {
        folder["id"] for folder in lib.get("folders", [])
        if folder["id"] != ROOT_FOLDER_ID and folder_parent_id(folder) == parent_id
    }


def folder_id_from_name(name: str, sibling_ids: set[str]) -> str:
    return unique_id(name, sibling_ids)


def normalize_library_folders(lib: dict) -> bool:
    folders = lib.get("folders", [])
    changed = False
    if not folders:
        lib["folders"] = [{"id": ROOT_FOLDER_ID, "name": ROOT_FOLDER_DISPLAY_NAME}]
        return True
    folder_ids = {folder["id"] for folder in folders}
    if ROOT_FOLDER_ID not in folder_ids:
        folders.insert(0, {"id": ROOT_FOLDER_ID, "name": ROOT_FOLDER_DISPLAY_NAME})
        folder_ids.add(ROOT_FOLDER_ID)
        changed = True
    for folder in folders:
        if folder["id"] == ROOT_FOLDER_ID:
            if folder.pop(FOLDER_PARENT_KEY, None) is not None:
                changed = True
            continue
        parent_id = folder.get(FOLDER_PARENT_KEY, ROOT_FOLDER_ID)
        if FOLDER_PARENT_KEY not in folder:
            folder[FOLDER_PARENT_KEY] = ROOT_FOLDER_ID
            changed = True
        elif parent_id not in folder_ids or parent_id == folder["id"]:
            folder[FOLDER_PARENT_KEY] = ROOT_FOLDER_ID
            changed = True
    return changed


def build_folder_tree(lib: dict) -> dict:
    normalize_library_folders(lib)
    nodes = {folder["id"]: {**folder, "children": []} for folder in lib.get("folders", [])}
    for folder in lib.get("folders", []):
        if folder["id"] == ROOT_FOLDER_ID:
            continue
        parent = nodes.get(folder_parent_id(folder))
        if parent is not None:
            parent["children"].append(nodes[folder["id"]])
    root = nodes[ROOT_FOLDER_ID]

    def sort_children(node: dict) -> None:
        node["children"].sort(key=lambda child: (child.get("name") or "").lower())
        for child in node["children"]:
            sort_children(child)

    sort_children(root)
    return root


def create_folder(library_id: str, name: str, parent_id: str = ROOT_FOLDER_ID) -> dict:
    lib = load_library(library_id)
    parent_id = parent_id or ROOT_FOLDER_ID
    if not folder_by_id(lib, parent_id):
        raise ValueError("Unknown parent folder")
    folder = {
        "id": folder_id_from_name(name, sibling_folder_ids(lib, parent_id)),
        "name": name,
        FOLDER_PARENT_KEY: parent_id,
    }
    lib["folders"].append(folder)
    save_library(library_id, lib)
    return folder


def delete_folder(library_id: str, folder_id: str) -> None:
    lib = load_library(library_id)
    if folder_id == ROOT_FOLDER_ID:
        raise ValueError("Cannot delete root folder")
    folder = folder_by_id(lib, folder_id)
    if not folder:
        raise ValueError("Unknown folder")
    parent_id = folder_parent_id(folder)
    for child in lib.get("folders", []):
        if child["id"] != ROOT_FOLDER_ID and folder_parent_id(child) == folder_id:
            child[FOLDER_PARENT_KEY] = parent_id
    for score_id, assigned_id in list(lib.get("score_folders", {}).items()):
        if assigned_id == folder_id:
            lib["score_folders"][score_id] = parent_id
    lib["folders"] = [entry for entry in lib["folders"] if entry["id"] != folder_id]
    save_library(library_id, lib)


def library_folder_ids(lib: dict) -> set[str]:
    return {folder["id"] for folder in lib.get("folders", [])}


def load_main_users() -> list[dict]:
    return [user.to_dict() for user in _user_repo.load_main()]


def save_main_users(users: list) -> None:
    _user_repo.save_main([user_from_dict(entry) for entry in users])


def load_maestro_sub_users(maestro_username: str) -> list[dict]:
    return [user.to_dict() for user in _user_repo.load_sub_accounts(maestro_username)]


def save_maestro_sub_users(maestro_username: str, users: list) -> None:
    uname = maestro_username.strip().lower()
    _user_repo.save_sub_accounts(
        uname,
        [user_from_dict(entry, maestro_username=uname) for entry in users],
    )


def _user_model(user) -> User:
    return user_from_dict(user) if isinstance(user, dict) else user


def score_owner_id(user) -> str:
    return _user_model(user).score_owner_id()


def is_maestro_role(role: str) -> bool:
    return role == MAESTRO_ROLE


def is_admin_role(role: str) -> bool:
    return role == ADMIN_ROLE


def role_uses_encrypted_password(role: str) -> bool:
    return role in ROLES_WITH_ENCRYPTED_PASSWORD


def password_storage_secret() -> str:
    return password_service.storage_secret()


def is_encrypted_password(stored: str) -> bool:
    return password_service.is_encrypted_password(stored)


def encrypt_stored_password(plain: str, secret: str) -> str:
    return password_service.encrypt_stored_password(plain, secret)


def decrypt_stored_password(stored: str, secret: str) -> str:
    return password_service.decrypt_stored_password(stored, secret)


def set_user_password(user, password: str, secret: str) -> None:
    model = _user_model(user)
    password_service.set_password(model, password, secret)
    if isinstance(user, dict):
        user["password"] = model.password


def finalize_user_role(user, secret: str) -> None:
    model = _user_model(user)
    password_service.finalize_role(model, secret)
    if isinstance(user, dict):
        user["password"] = model.password


def password_for_display(user) -> str:
    return password_service.password_for_display(_user_model(user))


def verify_user_password(user, password: str, secret: str) -> bool:
    return password_service.verify_password(_user_model(user), password, secret)


def load_users() -> list[dict]:
    return [user.to_dict() for user in _user_repo.load_all()]


def save_users(users: list) -> None:
    _user_repo.save_all([user_from_dict(entry) for entry in users])


def get_user_from_main(user_id: str):
    return _user_repo.get_from_main(user_id)


def get_user(user_id: str):
    return _user_repo.get_by_id(user_id)


def get_user_by_username(username: str):
    return _user_repo.get_by_username(username)


def upsert_user(user) -> None:
    _user_repo.upsert(_user_model(user))


def remove_user_record(user_id: str) -> bool:
    return _user_repo.remove(user_id)


def get_maestro_accounts() -> list:
    return _user_repo.maestro_accounts()


def get_users_for_maestro(maestro_user_id: str) -> list:
    return _user_repo.sub_accounts_for_maestro(maestro_user_id)


def maestro_folder_username(user) -> str:
    return _user_repo.maestro_folder_username(_user_model(user))


def maestro_account_id(user) -> str:
    return _user_repo.maestro_account_id(_user_model(user))


def default_maestro_config(display_name: str) -> dict:
    from models.maestro_config import MaestroConfig
    return MaestroConfig(display_name).to_dict()


def maestro_header_show_title(cfg: dict, has_logotype: bool) -> bool:
    from models.maestro_config import MaestroConfig
    return MaestroConfig.from_dict(cfg).header_show_title(has_logotype)


def form_show_site_title_checked(form_value: str | None) -> bool:
    return form_value == "1"


def load_maestro_config(maestro_username: str) -> dict:
    from models.maestro_config import MaestroConfig
    uname = maestro_username.strip().lower()
    path = maestro_config_path(uname)
    if not path.exists():
        user = get_user_by_username(uname)
        name = user.display_name if user else uname
        return MaestroConfig(name).to_dict()
    cfg = MaestroConfig.from_dict(_read_json(path, MaestroConfig(uname).to_dict()))
    if not cfg.site_title:
        user = get_user_by_username(uname)
        cfg.site_title = user.display_name if user else uname
    return cfg.to_dict()


def save_maestro_config(maestro_username: str, config: dict) -> None:
    uname = maestro_username.strip().lower()
    ensure_maestro_data_dirs(uname)
    payload = {
        "site_title": (config.get("site_title") or "").strip(),
        "logotype": (config.get("logotype") or "").strip(),
        "show_site_title": bool(config.get("show_site_title", DEFAULT_SHOW_SITE_TITLE)),
        "enable_printing": bool(config.get("enable_printing", c.DEFAULT_ENABLE_PRINTING)),
        "enable_download": bool(config.get("enable_download", c.DEFAULT_ENABLE_DOWNLOAD)),
    }
    if not payload["site_title"]:
        user = get_user_by_username(uname)
        payload["site_title"] = user.display_name if user else uname
    _write_json(maestro_config_path(uname), payload)


def maestro_has_theme(maestro_username: str) -> bool:
    return maestro_theme_path(maestro_username).is_file()


def write_default_maestro_theme(maestro_username: str) -> None:
    uname = maestro_username.strip().lower()
    ensure_maestro_data_dirs(uname)
    dest = maestro_theme_path(uname)
    template = APP_ROOT / "templates" / "maestro_theme_template.css"
    if template.is_file():
        shutil.copy(template, dest)
    else:
        dest.write_text(DEFAULT_MAESTRO_THEME_CSS, encoding="utf-8")


def maestro_logotype_path(maestro_username: str) -> Path | None:
    cfg = load_maestro_config(maestro_username)
    rel = cfg.get("logotype", "")
    if not rel:
        return None
    base = maestro_data_dir(maestro_username) / MAESTRO_ASSETS_DIRNAME
    path = (maestro_data_dir(maestro_username) / rel).resolve()
    _assert_path_under_base(path, base.resolve())
    if not path.is_file():
        return None
    ext = extension_of(path.name)
    if ext not in LOGOTYPE_EXTENSIONS:
        return None
    return path


def maestro_stats(maestro_username: str) -> dict:
    uname = maestro_username.strip().lower()
    maestro_user = get_user_by_username(uname)
    if not maestro_user or not maestro_user.is_maestro():
        raise ValueError("Unknown maestro")
    prev = current_maestro_data()
    try:
        activate_maestro_data(uname)
        score_count = len(list_all_score_ids())
        disk_bytes = maestro_folder_size_bytes(uname)
        sub_accounts = get_users_for_maestro(maestro_user.username)
        singer_count = sum(1 for u in sub_accounts if u.is_singer())
        choir_count = sum(1 for u in sub_accounts if u.is_choir())
        return {
            "score_count": score_count,
            "disk_bytes": disk_bytes,
            "disk_label": format_byte_size(disk_bytes),
            "singer_count": singer_count,
            "choir_count": choir_count,
            "sub_account_count": len(sub_accounts),
        }
    finally:
        activate_maestro_data(prev)


def rename_maestro_folder(old_username: str, new_username: str) -> None:
    old = old_username.strip().lower()
    new = new_username.strip().lower()
    if old == new:
        return
    src = maestro_data_dir(old)
    dst = maestro_data_dir(new)
    if not src.exists():
        raise ValueError("Maestro folder not found")
    if dst.exists():
        raise ValueError("Target maestro folder exists")
    src.rename(dst)


def bootstrap_admin(secret: str) -> User | None:
    from models.user import AdminUser
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


def is_user_library_id(library_id: str) -> bool:
    if library_id == GLOBAL_LIBRARY_ID:
        return False
    user = get_user_by_username(library_id)
    return bool(user and user.is_sub_account())


def default_library(library_id: str) -> dict:
    lib = {
        "library_id": library_id,
        "folders": [{"id": ROOT_FOLDER_ID, "name": ROOT_FOLDER_DISPLAY_NAME}],
        "score_folders": {},
        "score_order": [],
    }
    if library_id == GLOBAL_LIBRARY_ID:
        lib["display_name"] = GLOBAL_LIBRARY_DISPLAY_NAME
    elif is_user_library_id(library_id):
        lib["owner_id"] = library_id
        user = get_user_by_username(library_id)
        lib["display_name"] = user.display_name if user else library_id
    return lib


def sync_library_metadata(library_id: str, lib: dict) -> bool:
    changed = False
    if lib.get("library_id") != library_id:
        lib["library_id"] = library_id
        changed = True
    if library_id == GLOBAL_LIBRARY_ID:
        if lib.get("display_name") != GLOBAL_LIBRARY_DISPLAY_NAME:
            lib["display_name"] = GLOBAL_LIBRARY_DISPLAY_NAME
            changed = True
    elif is_user_library_id(library_id):
        if lib.get("owner_id") != library_id:
            lib["owner_id"] = library_id
            changed = True
        user = get_user_by_username(library_id)
        expected_name = user.display_name if user else library_id
        if lib.get("display_name") != expected_name:
            lib["display_name"] = expected_name
            changed = True
    return changed


def load_library(library_id: str) -> dict:
    lib = _read_json(library_path(library_id), default_library(library_id))
    normalize_library_folders(lib)
    for key in ("score_folders", "score_order"):
        lib.setdefault(key, {} if key != "score_order" else [])
    return lib


def ensure_library(library_id: str) -> dict:
    path = library_path(library_id)
    if path.exists():
        return load_library(library_id)
    lib = default_library(library_id)
    save_library(library_id, lib)
    return lib


def _prune_library_stale_scores(lib: dict) -> bool:
    order = lib.get("score_order", [])
    valid_order = [sid for sid in order if _score_exists(sid)]
    changed = len(valid_order) != len(order)
    if changed:
        lib["score_order"] = valid_order
    score_folders = lib.get("score_folders", {})
    for sid in list(score_folders):
        if sid not in valid_order:
            score_folders.pop(sid)
            changed = True
    return changed


def score_library_ids(score_id: str) -> list[str]:
    ids = []
    for lib_file in libraries_dir().glob("*.json"):
        library_id = lib_file.stem
        if library_has_score(library_id, score_id):
            ids.append(library_id)
    return ids


def score_shared_beyond_owner(score_id: str, owner_id: str) -> bool:
    for library_id in score_library_ids(score_id):
        if library_id == GLOBAL_LIBRARY_ID or library_id != owner_id:
            return True
    return False


def save_library(library_id: str, lib: dict) -> None:
    sync_library_metadata(library_id, lib)
    lib.pop("file_aliases", None)
    _write_json(library_path(library_id), lib)


def default_user_notes() -> dict:
    return {"scores": {}}


def load_user_notes(user_id: str) -> dict:
    notes = _read_json(user_notes_path(user_id), default_user_notes())
    notes.setdefault("scores", {})
    return notes


def save_user_notes(user_id: str, notes: dict) -> None:
    notes.setdefault("scores", {})
    _write_json(user_notes_path(user_id), notes)


def get_score_notes(user_id: str, score_id: str) -> dict:
    notes = load_user_notes(user_id)
    entry = notes["scores"].get(score_id)
    if not isinstance(entry, dict):
        return {"files": {}}
    entry.setdefault("files", {})
    return entry


def set_score_notes(user_id: str, score_id: str, score_notes: dict) -> None:
    notes = load_user_notes(user_id)
    files = score_notes.get("files") if isinstance(score_notes, dict) else None
    if not isinstance(files, dict) or not files:
        notes["scores"].pop(score_id, None)
    else:
        notes["scores"][score_id] = {"files": files}
    save_user_notes(user_id, notes)


def _assert_path_under_base(path: Path, base: Path) -> None:
    resolved = path.resolve()
    base_resolved = base.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise ValueError("Path escapes base directory")


def _reject_path_segments(value: str, label: str) -> str:
    text = value.strip()
    if not text or text in (".", ".."):
        raise ValueError(f"Invalid {label}")
    if text != _basename_only(text):
        raise ValueError(f"Invalid {label}")
    return text


def validate_score_id(score_id: str) -> str:
    score_id = _reject_path_segments(score_id, "score id")
    _assert_path_under_base(scores_dir() / score_id, scores_dir())
    return score_id


def validate_stored_name(stored_name: str) -> str:
    return _reject_path_segments(stored_name, "stored file name")


def score_dir(score_id: str) -> Path:
    score_id = validate_score_id(score_id)
    return scores_dir() / score_id


def score_files_dir(score_id: str) -> Path:
    return score_dir(score_id) / "files"


def score_meta_path(score_id: str) -> Path:
    return score_dir(score_id) / "meta.json"


def load_score_meta(score_id: str) -> dict | None:
    try:
        path = score_meta_path(score_id)
    except ValueError:
        return None
    if not path.exists():
        return None
    return _read_json(path, {})


def save_score_meta(score_id: str, meta: dict) -> None:
    _write_json(score_meta_path(score_id), meta)


def list_all_score_ids() -> list[str]:
    if not scores_dir().exists():
        return []
    return [p.name for p in scores_dir().iterdir() if p.is_dir() and (p / "meta.json").exists()]


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def media_from_extension(ext: str) -> str:
    if ext in ("png", "jpeg", "jpg"):
        return "image"
    if ext in ("mp3", "wav", "m4a", "ogg"):
        return "audio"
    if ext in ("mp4", "mkv", "webm"):
        return "video"
    if ext in ("mscz", "mscx", "xml", "musicxml"):
        return "musescore"
    if ext == "pdf":
        return "pdf"
    return "file"


def aux_file_type_label(file_entry: dict) -> str:
    if file_entry.get("media") == "youtube":
        return "YouTube"
    ext = extension_of(file_entry.get("stored_name") or "")
    if ext in ("mscz", "mscx"):
        return "MuseScore"
    if ext in ("musicxml", "xml"):
        return "MusicXML"
    if ext:
        return ext.upper()
    media_labels = {
        "pdf": "PDF",
        "image": "Image",
        "audio": "Audio",
        "video": "Video",
        "musescore": "MuseScore",
    }
    return media_labels.get(file_entry.get("media", ""), "File")


def basename_display_name(filename: str) -> str:
    name = Path(filename).stem
    if len(name) > FILE_NAME_MAX_LEN:
        return name[:FILE_NAME_MAX_LEN]
    return name or "File"


def normalize_tags(tags) -> list[str]:
    if not tags:
        return []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = [tags]
    seen = set()
    out = []
    for t in tags:
        s = str(t).strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s[:TAG_MAX_LEN])
    return out


def normalize_year(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not SCORE_YEAR_PATTERN.match(raw):
        raise ValueError("Year must be a four-digit number")
    year_num = int(raw)
    if year_num < SCORE_YEAR_MIN or year_num > SCORE_YEAR_MAX:
        raise ValueError(f"Year must be between {SCORE_YEAR_MIN} and {SCORE_YEAR_MAX}")
    return raw


def score_subtitle_line(meta: dict) -> str:
    composer = (meta.get("composer") or "").strip()
    arranger = (meta.get("arranger") or "").strip()
    year = (meta.get("year") or "").strip()
    credit_parts = []
    if composer:
        credit_parts.append(composer)
    if arranger:
        credit_parts.append(f"arr. {arranger}")
    line = " · ".join(credit_parts)
    if year:
        if line:
            return f"{line} ({year})"
        return f"({year})"
    return line


def normalize_metadata(data: dict) -> dict:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("Title is required")
    return {
        "title": title,
        "composer": (data.get("composer") or "").strip(),
        "arranger": (data.get("arranger") or "").strip(),
        "description": (data.get("description") or "").strip(),
        "tags": normalize_tags(data.get("tags", [])),
    }


def validate_youtube_url(url: str) -> bool:
    if not url:
        return False
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return host in YOUTUBE_DOMAINS


def youtube_embed_url(url: str) -> str | None:
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    video_id = None
    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]
    elif "youtube.com" in host:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith("/embed/"):
            video_id = parsed.path.split("/")[2]
    if video_id and re.match(r"^[\w-]{11}$", video_id):
        return f"https://www.youtube.com/embed/{video_id}"
    return None


def fetch_youtube_title(url: str) -> str | None:
    from urllib.parse import urlencode
    from urllib.request import urlopen
    if not validate_youtube_url(url):
        return None
    query = urlencode({"url": url.strip(), "format": "json"})
    try:
        with urlopen(f"{YOUTUBE_OEMBED_URL}?{query}", timeout=YOUTUBE_OEMBED_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode())
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    title = (data.get("title") or "").strip()
    if not title:
        return None
    return title[:FILE_NAME_MAX_LEN]


def validate_score_files(files: list[dict], require_main: bool = True) -> None:
    mains = [f for f in files if f.get("role") == "main"]
    if require_main:
        if len(mains) != 1:
            raise ValueError("Score must have exactly one main file")
        if mains[0].get("media") != "pdf":
            raise ValueError("Main file must be PDF")
    elif len(mains) > 1:
        raise ValueError("Score must have at most one main file")
    for f in files:
        name = (f.get("name") or "").strip()
        if not name:
            raise ValueError("Each file needs a display name")
        if len(name) > FILE_NAME_MAX_LEN:
            raise ValueError(f"Display name too long: {name[:20]}…")


def file_display_name(score_meta: dict, file_id: str) -> str:
    for f in score_meta.get("files", []):
        if f["id"] == file_id:
            return f.get("name", "File")
    return "File"


def get_main_file(meta: dict) -> dict | None:
    for f in meta.get("files", []):
        if f.get("role") == "main":
            return f
    return None


def file_download_name(file_entry: dict) -> str:
    stored = file_entry.get("stored_name") or ""
    ext = extension_of(stored)
    name = file_entry.get("name") or "file"
    if ext and not name.lower().endswith(f".{ext.lower()}"):
        return f"{name}.{ext}"
    return name


def get_file_by_id(meta: dict, file_id: str) -> dict | None:
    for f in meta.get("files", []):
        if f["id"] == file_id:
            return f
    return None


def stored_file_path(score_id: str, stored_name: str) -> Path:
    name = validate_stored_name(stored_name)
    files_dir = score_files_dir(score_id)
    path = files_dir / name
    _assert_path_under_base(path, files_dir)
    return path


def assign_score_to_folder(library_id: str, score_id: str, folder_id: str) -> None:
    lib = load_library(library_id)
    lib["score_folders"][score_id] = folder_id
    if score_id not in lib["score_order"]:
        lib["score_order"].insert(0, score_id)
    save_library(library_id, lib)
    if library_id == GLOBAL_LIBRARY_ID:
        transfer_score_to_system(score_id)


def set_score_folder(library_id: str, score_id: str, folder_id: str) -> None:
    lib = load_library(library_id)
    if score_id not in lib.get("score_order", []):
        raise ValueError("Score not in library")
    lib["score_folders"][score_id] = folder_id
    save_library(library_id, lib)


def _remove_score_refs_from_library(lib: dict, score_id: str) -> bool:
    changed = False
    if score_id in lib.get("score_folders", {}):
        lib["score_folders"].pop(score_id, None)
        changed = True
    order = lib.get("score_order", [])
    if score_id in order:
        lib["score_order"] = [sid for sid in order if sid != score_id]
        changed = True
    return changed


def remove_score_from_library(library_id: str, score_id: str) -> None:
    lib = load_library(library_id)
    if _remove_score_refs_from_library(lib, score_id):
        save_library(library_id, lib)


def library_has_score(library_id: str, score_id: str) -> bool:
    lib = load_library(library_id)
    return score_id in lib.get("score_order", [])


def user_library_score_ids(user_id: str) -> list[str]:
    return load_library(user_id).get("score_order", [])


def _write_uploaded_file(score_id: str, upload_file) -> tuple[str, str]:
    dest_dir = score_files_dir(score_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = extension_of(upload_file.filename or "file")
    stored_name = new_stored_filename(ext, dest_dir)
    dest = dest_dir / stored_name
    upload_file.save(dest)
    return stored_name, ext


def create_score_from_upload(
    library_id: str,
    folder_id: str,
    upload_file,
    metadata: dict,
    owner_id: str,
) -> dict:
    meta_fields = normalize_metadata(metadata)
    ext = extension_of(upload_file.filename or "")
    if ext not in MAIN_EXTENSIONS:
        raise ValueError("Main file must be PDF")
    content_hash = _digest_upload(upload_file)
    existing = find_score_by_main_content_hash(content_hash)
    if existing:
        fid = folder_id if folder_id else ROOT_FOLDER_ID
        assign_score_to_folder(library_id, existing["id"], fid)
        return existing
    score_id = new_score_id()
    upload_name = upload_file.filename or "score.pdf"
    sdir = score_dir(score_id)
    sdir.mkdir(parents=True, exist_ok=True)
    stored_name, _ = _write_uploaded_file(score_id, upload_file)
    file_id = new_file_id(set())
    files = [{
        "id": file_id,
        "role": "main",
        "stored_name": stored_name,
        "name": basename_display_name(upload_name),
        "media": "pdf",
    }]
    validate_score_files(files)
    meta = {
        "id": score_id,
        **meta_fields,
        "year": "",
        "owner_id": owner_id,
        MAIN_CONTENT_HASH_META_KEY: content_hash,
        "files": files,
        "created_at": utc_now_iso(),
    }
    save_score_meta(score_id, meta)
    fid = folder_id if folder_id else ROOT_FOLDER_ID
    assign_score_to_folder(library_id, score_id, fid)
    return meta


def update_score_metadata(score_id: str, metadata: dict, *, allow_year: bool = False) -> dict:
    meta = load_score_meta(score_id)
    if not meta:
        raise ValueError("Score not found")
    fields = normalize_metadata(metadata)
    if allow_year:
        fields["year"] = normalize_year(metadata.get("year"))
    meta.update(fields)
    meta.pop("type", None)
    validate_score_files(meta.get("files", []))
    save_score_meta(score_id, meta)
    return meta


def add_aux_file(score_id: str, upload_file) -> dict:
    meta = load_score_meta(score_id)
    if not meta:
        raise ValueError("Score not found")
    ext = extension_of(upload_file.filename or "")
    if ext not in AUX_EXTENSIONS:
        raise ValueError(f"File type not allowed: {ext}")
    stored_name, ext = _write_uploaded_file(score_id, upload_file)
    existing_ids = {f["id"] for f in meta.get("files", [])}
    upload_name = upload_file.filename or "file"
    entry = {
        "id": new_file_id(existing_ids),
        "role": "aux",
        "stored_name": stored_name,
        "name": basename_display_name(upload_name),
        "media": media_from_extension(ext),
    }
    meta.setdefault("files", []).append(entry)
    validate_score_files(meta["files"])
    save_score_meta(score_id, meta)
    return entry


def add_youtube_aux(score_id: str, url: str, name: str) -> dict:
    if not validate_youtube_url(url):
        raise ValueError("Invalid YouTube URL")
    meta = load_score_meta(score_id)
    if not meta:
        raise ValueError("Score not found")
    display = (name or "").strip()
    if not display:
        display = fetch_youtube_title(url) or YOUTUBE_DEFAULT_NAME
    display = display[:FILE_NAME_MAX_LEN] or YOUTUBE_DEFAULT_NAME
    existing_ids = {f["id"] for f in meta.get("files", [])}
    entry = {
        "id": new_file_id(existing_ids),
        "role": "aux",
        "name": display,
        "media": "youtube",
        "url": url.strip(),
    }
    meta.setdefault("files", []).append(entry)
    validate_score_files(meta["files"])
    save_score_meta(score_id, meta)
    return entry


def remove_aux_file(score_id: str, file_id: str) -> None:
    meta = load_score_meta(score_id)
    if not meta:
        raise ValueError("Score not found")
    target = get_file_by_id(meta, file_id)
    if not target:
        raise ValueError("File not found")
    if target.get("role") == "main":
        raise ValueError("Cannot remove main file this way")
    meta["files"] = [f for f in meta["files"] if f["id"] != file_id]
    if target.get("stored_name"):
        path = stored_file_path(score_id, target["stored_name"])
        if path.exists():
            path.unlink()
    validate_score_files(meta["files"])
    save_score_meta(score_id, meta)


def update_file_name(score_id: str, file_id: str, name: str) -> dict:
    meta = load_score_meta(score_id)
    if not meta:
        raise ValueError("Score not found")
    target = get_file_by_id(meta, file_id)
    if not target:
        raise ValueError("File not found")
    clean = name.strip()[:FILE_NAME_MAX_LEN]
    if not clean:
        raise ValueError("Name required")
    target["name"] = clean
    save_score_meta(score_id, meta)
    return target


def _move_blob(src_score_id: str, stored_name: str, dst_score_id: str) -> None:
    src = stored_file_path(src_score_id, stored_name)
    if not src.exists():
        raise ValueError("File missing on disk")
    dst_dir = score_files_dir(dst_score_id)
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst_dir / stored_name))


def _apply_main_out_rules(meta: dict) -> None:
    if get_main_file(meta):
        validate_score_files(meta.get("files", []))
        save_score_meta(meta["id"], meta)
        return
    pdf_aux = [f for f in meta.get("files", []) if f.get("role") == "aux" and f.get("media") == "pdf"]
    if pdf_aux:
        pdf_aux[0]["role"] = "main"
        validate_score_files(meta.get("files", []))
    else:
        validate_score_files(meta.get("files", []), require_main=False)
    save_score_meta(meta["id"], meta)


def move_file_between_scores(src_score_id: str, file_id: str, dst_score_id: str) -> None:
    src = load_score_meta(src_score_id)
    dst = load_score_meta(dst_score_id)
    if not src or not dst:
        raise ValueError("Score not found")
    target = get_file_by_id(src, file_id)
    if not target:
        raise ValueError("File not found")
    if target.get("media") == "youtube":
        entry = dict(target)
        src["files"] = [f for f in src["files"] if f["id"] != file_id]
        if target.get("role") == "main":
            _apply_main_out_rules(src)
        else:
            save_score_meta(src_score_id, src)
        entry["role"] = "aux"
        dst.setdefault("files", []).append(entry)
        validate_score_files(dst["files"])
        save_score_meta(dst_score_id, dst)
        return
    stored = target["stored_name"]
    was_main = target.get("role") == "main"
    src["files"] = [f for f in src["files"] if f["id"] != file_id]
    _move_blob(src_score_id, stored, dst_score_id)
    entry = dict(target)
    entry["role"] = "aux"
    dst.setdefault("files", []).append(entry)
    validate_score_files(dst["files"])
    save_score_meta(dst_score_id, dst)
    if was_main:
        _apply_main_out_rules(src)
    else:
        save_score_meta(src_score_id, src)


def split_file_to_new_score(
    src_score_id: str,
    file_id: str,
    library_id: str,
    folder_id: str,
    metadata: dict,
    owner_id: str,
) -> dict:
    src = load_score_meta(src_score_id)
    if not src:
        raise ValueError("Source score not found")
    target = get_file_by_id(src, file_id)
    if not target:
        raise ValueError("File not found")
    if target.get("media") != "pdf":
        raise ValueError("Only PDF can become main score")
    meta_fields = normalize_metadata(metadata)
    created_id = new_score_id()
    score_dir(created_id).mkdir(parents=True, exist_ok=True)
    score_files_dir(created_id).mkdir(exist_ok=True)
    stored = target["stored_name"]
    _move_blob(src_score_id, stored, created_id)
    src["files"] = [f for f in src["files"] if f["id"] != file_id]
    new_file = {
        "id": new_file_id(set()),
        "role": "main",
        "stored_name": stored,
        "name": target.get("name", "Full score"),
        "media": "pdf",
    }
    content_hash = _digest_file(stored_file_path(created_id, stored))
    new_meta = {
        "id": created_id,
        **meta_fields,
        "year": "",
        "owner_id": owner_id,
        MAIN_CONTENT_HASH_META_KEY: content_hash,
        "files": [new_file],
        "created_at": utc_now_iso(),
    }
    validate_score_files(new_meta["files"])
    save_score_meta(created_id, new_meta)
    _apply_main_out_rules(src)
    fid = folder_id if folder_id else ROOT_FOLDER_ID
    assign_score_to_folder(library_id, created_id, fid)
    return new_meta


def delete_score(score_id: str) -> None:
    validate_score_id(score_id)
    if libraries_dir().exists():
        for lib_file in libraries_dir().glob("*.json"):
            library_id = lib_file.stem
            lib = load_library(library_id)
            if _remove_score_refs_from_library(lib, score_id):
                save_library(library_id, lib)
    path = score_dir(score_id)
    if path.exists():
        shutil.rmtree(path)


def transfer_score_to_system(score_id: str) -> None:
    meta = load_score_meta(score_id)
    if not meta:
        return
    meta["owner_id"] = SYSTEM_OWNER_ID
    save_score_meta(score_id, meta)
    if not library_has_score(GLOBAL_LIBRARY_ID, score_id):
        assign_score_to_folder(GLOBAL_LIBRARY_ID, score_id, ROOT_FOLDER_ID)


def delete_user(user_id: str) -> None:
    if not get_user(user_id):
        raise ValueError("User not found")
    if scores_dir().exists():
        for sdir in scores_dir().iterdir():
            if not sdir.is_dir():
                continue
            meta = load_score_meta(sdir.name)
            if meta and meta.get("owner_id") == user_id:
                transfer_score_to_system(meta["id"])
    if not remove_user_record(user_id):
        raise ValueError("User not found")
    lib_path = library_path(user_id)
    if lib_path.exists():
        lib_path.unlink()


def score_matches_filter(meta: dict, query: str, tag: str | None) -> bool:
    if tag:
        if tag.lower() not in meta.get("tags", []):
            return False
    if not query:
        return True
    q = query.lower()
    parts = [
        meta.get("title", ""),
        meta.get("composer", ""),
        meta.get("year", ""),
        meta.get("arranger", ""),
        meta.get("description", ""),
        " ".join(meta.get("tags", [])),
    ]
    return q in " ".join(parts).lower()


def collect_tags(score_ids: list[str]) -> list[str]:
    tags = set()
    for sid in score_ids:
        meta = load_score_meta(sid)
        if meta:
            tags.update(meta.get("tags", []))
    return sorted(tags)


def folder_label(lib: dict, folder_id: str) -> str:
    for folder in lib.get("folders", []):
        if folder["id"] == folder_id:
            return folder["name"]
    return folder_id


def _scores_from_order(order: list[str], query: str, tag: str | None) -> list[dict]:
    result = []
    for sid in order:
        meta = load_score_meta(sid)
        if not meta:
            continue
        if not score_matches_filter(meta, query, tag):
            continue
        result.append(meta)
    return result


def _sort_scores_by_title(scores: list[dict]) -> list[dict]:
    return sorted(scores, key=lambda meta: (meta.get("title") or "").lower())


def scores_for_library(library_id: str, folder_id: str | None, query: str, tag: str | None) -> list[dict]:
    lib = load_library(library_id)
    order = lib.get("score_order", [])
    sf = lib.get("score_folders", {})
    filtered_order = []
    for sid in order:
        if folder_id and sf.get(sid, ROOT_FOLDER_ID) != folder_id:
            continue
        filtered_order.append(sid)
    return _sort_scores_by_title(_scores_from_order(filtered_order, query, tag))


def scores_for_library_sorted(library_id: str, query: str, tag: str | None) -> list[dict]:
    lib = load_library(library_id)
    return _sort_scores_by_title(_scores_from_order(lib.get("score_order", []), query, tag))
