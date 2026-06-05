"""Filesystem JSON store for score portal."""

import hashlib
import json
import os
import re
import shutil
import threading
import base64
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

APP_ROOT = Path(__file__).resolve().parent
INSTANCE_DIR = APP_ROOT / "instance"
INSTANCE_CONFIG_PATH = INSTANCE_DIR / "config.json"
DEFAULT_DATA_DIR_NAME = "data"
DEFAULT_MAESTRO_USERNAME = "admin"
SETUP_PASSWORD_MIN_LEN = 8

MAIN_EXTENSIONS = frozenset({"pdf"})
AUX_EXTENSIONS = frozenset({
    "pdf", "png", "jpeg", "jpg",
    "mscz", "mscx", "xml", "musicxml",
    "mp3", "wav", "m4a", "ogg",
    "mp4", "mkv", "webm",
})
YOUTUBE_DOMAINS = frozenset({"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"})
YOUTUBE_OEMBED_URL = "https://www.youtube.com/oembed"
YOUTUBE_OEMBED_TIMEOUT_SEC = 10
YOUTUBE_DEFAULT_NAME = "YouTube"

ROOT_FOLDER_ID = "root"
ROOT_FOLDER_DISPLAY_NAME = "All scores"
GLOBAL_LIBRARY_DISPLAY_NAME = "Global library"
USER_LIBRARY_ID_PREFIX = "u-"
LIBRARY_VIEW_LIST = "list"
LIBRARY_VIEW_FOLDER = "folder"
DEFAULT_LIBRARY_VIEW = LIBRARY_VIEW_LIST
FILE_NAME_MAX_LEN = 80
TAG_MAX_LEN = 40
GLOBAL_LIBRARY_ID = "_global"
SYSTEM_OWNER_ID = "_system"
MAESTRO_ROLE = "maestro"
PASSWORD_ENCRYPT_PREFIX = "enc:"
SCORE_ID_PREFIX = "s-"
MAIN_CONTENT_HASH_META_KEY = "main_content_hash"
FILE_HASH_READ_BYTES = 65536
BYTES_PER_SIZE_UNIT = 1024
SIZE_UNIT_LABELS = ("B", "KB", "MB", "GB", "TB")
SCORE_TITLE_COLLISION_MSG = "A score with this title already exists"
UNSAFE_PATH_CHAR_PATTERN = re.compile(r'[/\\:*?"<>|\0]')
WHITESPACE_PATTERN = re.compile(r"\s+")
MULTI_SEP_PATTERN = re.compile(r"[-_]+")
SCORE_LEGACY_HASH_PATTERN = re.compile(r"^s-[a-f0-9]{12}$")
USER_LEGACY_HASH_PATTERN = re.compile(r"^u-[a-f0-9]{12}$")
FILE_LEGACY_HASH_PATTERN = re.compile(r"^f-[a-f0-9]{12}$")
FOLDER_PARENT_KEY = "parent_id"
LEGACY_STORED_NAME_PATTERN = re.compile(r"^[a-f0-9]{32}\.[a-z0-9]+$", re.I)

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _read_instance_config() -> dict:
    if not INSTANCE_CONFIG_PATH.exists():
        return {}
    with open(INSTANCE_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _initial_data_dir() -> Path:
    cfg = _read_instance_config()
    if cfg.get("data_dir"):
        return Path(cfg["data_dir"]).expanduser()
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    return APP_ROOT / DEFAULT_DATA_DIR_NAME


DATA_DIR = _initial_data_dir()
USERS_PATH = DATA_DIR / "users.json"
SCORES_DIR = DATA_DIR / "scores"
LIBRARIES_DIR = DATA_DIR / "libraries"


def reconfigure_data_dir(data_dir: Path) -> Path:
    """Point store paths at data_dir (absolute, resolved)."""
    global DATA_DIR, USERS_PATH, SCORES_DIR, LIBRARIES_DIR
    resolved = data_dir.expanduser().resolve()
    DATA_DIR = resolved
    USERS_PATH = DATA_DIR / "users.json"
    SCORES_DIR = DATA_DIR / "scores"
    LIBRARIES_DIR = DATA_DIR / "libraries"
    return resolved


def save_instance_config(data_dir: Path) -> None:
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    resolved = data_dir.expanduser().resolve()
    _write_json(INSTANCE_CONFIG_PATH, {"data_dir": str(resolved)})


def resolve_data_dir(path_str: str) -> Path:
    raw = path_str.strip()
    if not raw:
        raise ValueError("Storage path is required")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (APP_ROOT / candidate).resolve()
    candidate.mkdir(parents=True, exist_ok=True)
    probe = candidate / ".write_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    return candidate


def default_setup_data_dir_display() -> str:
    return str((APP_ROOT / DEFAULT_DATA_DIR_NAME).resolve())


def has_maestro() -> bool:
    return any(u.get("role") == "maestro" for u in load_users())


def env_bootstrap_configured() -> bool:
    return bool(os.environ.get("BOOTSTRAP_MAESTRO_USER") and os.environ.get("BOOTSTRAP_MAESTRO_PASSWORD"))


def needs_setup() -> bool:
    if has_maestro():
        return False
    if env_bootstrap_configured():
        return False
    return True


def complete_setup(username: str, password: str, data_dir: Path, secret: str) -> dict:
    if len(password) < SETUP_PASSWORD_MIN_LEN:
        raise ValueError(f"Password must be at least {SETUP_PASSWORD_MIN_LEN} characters")
    uname = username.strip().lower()
    if not uname:
        raise ValueError("Username is required")
    resolved = resolve_data_dir(str(data_dir))
    save_instance_config(resolved)
    reconfigure_data_dir(resolved)
    ensure_data_dirs()
    user = {
        "id": user_id_from_username(uname),
        "display_name": "Maestro",
        "username": uname,
        "role": MAESTRO_ROLE,
    }
    set_user_password(user, password, secret)
    users = [user]
    save_users(users)
    ensure_library(GLOBAL_LIBRARY_ID)
    return user


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def _read_json(path: Path, default):
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock_for(path):
        if not path.exists():
            return json.loads(json.dumps(default))
        with open(path, encoding="utf-8") as f:
            return json.load(f)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock_for(path):
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        tmp.replace(path)


def ensure_data_dirs() -> None:
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARIES_DIR.mkdir(parents=True, exist_ok=True)


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


def data_dir_size_bytes() -> int:
    if not DATA_DIR.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(DATA_DIR):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def disk_usage_stats() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    used_bytes = data_dir_size_bytes()
    _total, _fs_used, free_bytes = shutil.disk_usage(DATA_DIR)
    return {
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "used_label": format_byte_size(used_bytes),
        "free_label": format_byte_size(free_bytes),
    }


_migrations_done = False


def run_storage_migrations() -> None:
    global _migrations_done
    if _migrations_done:
        return
    migrate_storage_ids()
    normalize_storage()
    _migrations_done = True


def _score_exists(score_id: str) -> bool:
    try:
        return score_meta_path(score_id).exists()
    except ValueError:
        return False


def _migrate_assigned_user_ids() -> None:
    """One-shot startup migration: legacy assigned_user_ids → user library membership."""
    for sid in list_all_score_ids():
        meta = _read_json(score_meta_path(sid), {})
        if "assigned_user_ids" not in meta:
            continue
        assigned = meta.pop("assigned_user_ids")
        save_score_meta(sid, meta)
        for user_id in assigned:
            if is_user_library_id(user_id):
                assign_score_to_folder(user_id, sid, ROOT_FOLDER_ID)


def _normalize_libraries() -> None:
    if not LIBRARIES_DIR.exists():
        return
    for lib_path in LIBRARIES_DIR.glob("*.json"):
        library_id = lib_path.stem
        lib = _read_json(lib_path, default_library(library_id))
        changed = sync_library_metadata(library_id, lib)
        if lib.pop("file_aliases", None) is not None:
            changed = True
        if _prune_library_stale_scores(lib):
            changed = True
        if normalize_library_folders(lib):
            changed = True
        if changed:
            save_library(library_id, lib)


def normalize_storage() -> None:
    _migrate_assigned_user_ids()
    _normalize_libraries()


def _score_slug_label(meta: dict) -> str:
    sid = meta.get("id", "")
    if SCORE_LEGACY_HASH_PATTERN.match(sid):
        return meta.get("title") or "score"
    if sid.startswith(SCORE_ID_PREFIX):
        return sid[len(SCORE_ID_PREFIX):]
    return meta.get("title") or "score"


def _file_slug_label(file_entry: dict) -> str:
    fid = file_entry.get("id", "")
    if FILE_LEGACY_HASH_PATTERN.match(fid):
        return file_entry.get("name") or fid
    if fid.startswith("f-"):
        return file_entry.get("name") or fid[2:]
    return fid or file_entry.get("name") or "file"


def _stored_name_needs_fixup(stored_name: str) -> bool:
    return bool(LEGACY_STORED_NAME_PATTERN.match(stored_name) or " " in stored_name)


def _migrate_file_entry(file_entry: dict, files_dir: Path, taken_ids: set[str], taken_names: set[str]) -> bool:
    changed = False
    old_id = file_entry.get("id", "")
    label = _file_slug_label(file_entry)
    new_id = unique_id(label, taken_ids)
    taken_ids.add(new_id)
    if new_id != old_id:
        file_entry["id"] = new_id
        changed = True
    stored = file_entry.get("stored_name")
    if not stored:
        return changed
    if not _stored_name_needs_fixup(stored):
        taken_names.add(stored)
        return changed
    stem, ext = split_filename(stored)
    if LEGACY_STORED_NAME_PATTERN.match(stored):
        stem = _slug(file_entry.get("name") or new_id)
    else:
        stem = _slug(stem)
    candidate = f"{stem}.{ext}" if ext else stem
    new_stored = candidate
    if new_stored in taken_names:
        new_stored = _unique_basename(stem, ext, taken_names)
    taken_names.add(new_stored)
    src = files_dir / stored
    dst = files_dir / new_stored
    if src.exists() and src != dst:
        if dst.exists():
            dst.unlink()
        src.rename(dst)
    file_entry["stored_name"] = new_stored
    return True


def _remap_library_score_refs(lib: dict, score_map: dict[str, str], folder_map: dict[str, str]) -> bool:
    changed = False
    sf = lib.get("score_folders", {})
    for old_sid in list(sf):
        new_sid = score_map.get(old_sid, old_sid)
        fid = sf[old_sid]
        new_fid = folder_map.get(fid, fid)
        if new_sid != old_sid:
            del sf[old_sid]
            changed = True
        if new_sid not in sf or sf.get(new_sid) != new_fid:
            sf[new_sid] = new_fid
            changed = changed or new_sid != old_sid or new_fid != fid
    order = lib.get("score_order", [])
    new_order = []
    seen = set()
    for sid in order:
        mapped = score_map.get(sid, sid)
        if mapped not in seen:
            new_order.append(mapped)
            seen.add(mapped)
        if mapped != sid:
            changed = True
    if new_order != order:
        lib["score_order"] = new_order
        changed = True
    return changed


def _migrate_library_file(lib_path: Path, user_map: dict[str, str], score_map: dict[str, str]) -> None:
    library_id = lib_path.stem
    lib = _read_json(lib_path, default_library(library_id))
    changed = lib.pop("file_aliases", None) is not None
    if _remap_library_score_refs(lib, score_map, {}):
        changed = True
    new_library_id = user_map.get(library_id, library_id)
    if new_library_id != library_id:
        lib["library_id"] = new_library_id
        changed = True
    if is_user_library_id(new_library_id):
        if lib.get("owner_id") != new_library_id:
            lib["owner_id"] = new_library_id
            changed = True
        user = get_user(new_library_id)
        expected_name = user["display_name"] if user else new_library_id
        if lib.get("display_name") != expected_name:
            lib["display_name"] = expected_name
            changed = True
    elif new_library_id == GLOBAL_LIBRARY_ID:
        if lib.get("display_name") != GLOBAL_LIBRARY_DISPLAY_NAME:
            lib["display_name"] = GLOBAL_LIBRARY_DISPLAY_NAME
            changed = True
    if not changed and new_library_id == library_id:
        return
    target = library_path(new_library_id)
    _write_json(target, lib)
    if target != lib_path and lib_path.exists():
        lib_path.unlink()


def _migrate_score_dir(old_id: str, new_id: str, user_map: dict[str, str]) -> None:
    meta = _read_json(score_meta_path(old_id), {})
    if not meta:
        return
    meta["id"] = new_id
    owner = meta.get("owner_id")
    if owner in user_map:
        meta["owner_id"] = user_map[owner]
    files_dir = score_files_dir(old_id)
    taken_ids: set[str] = set()
    taken_names: set[str] = set()
    file_changed = False
    for entry in meta.get("files", []):
        if _migrate_file_entry(entry, files_dir, taken_ids, taken_names):
            file_changed = True
    save_score_meta(old_id, meta)
    if new_id != old_id:
        dest = score_dir(new_id)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(score_dir(old_id)), str(dest))
        save_score_meta(new_id, meta)
    elif file_changed:
        save_score_meta(old_id, meta)


def _migrate_score_files_in_place(score_id: str, user_map: dict[str, str]) -> None:
    meta = _read_json(score_meta_path(score_id), {})
    if not meta:
        return
    changed = False
    files_dir = score_files_dir(score_id)
    taken_ids: set[str] = set()
    taken_names: set[str] = set()
    for entry in meta.get("files", []):
        if _migrate_file_entry(entry, files_dir, taken_ids, taken_names):
            changed = True
    owner = meta.get("owner_id")
    if owner in user_map:
        meta["owner_id"] = user_map[owner]
        changed = True
    if changed:
        save_score_meta(score_id, meta)


def migrate_storage_ids() -> None:
    if not USERS_PATH.exists() and not SCORES_DIR.exists():
        return
    users = load_users()
    user_map: dict[str, str] = {}
    taken_users: set[str] = set()
    for user in users:
        old_id = user["id"]
        new_id = unique_id(_username_slug(user["username"]), taken_users, USER_LIBRARY_ID_PREFIX)
        taken_users.add(new_id)
        if new_id != old_id:
            user_map[old_id] = new_id
            user["id"] = new_id
    if user_map:
        save_users(users)
    score_map: dict[str, str] = {}
    taken_scores: set[str] = set()
    for sid in list_all_score_ids():
        meta = _read_json(score_meta_path(sid), {})
        if not meta:
            continue
        label = _score_slug_label(meta)
        new_sid = unique_id(label, taken_scores, SCORE_ID_PREFIX)
        taken_scores.add(new_sid)
        if new_sid != sid:
            score_map[sid] = new_sid
    if LIBRARIES_DIR.exists():
        for lib_path in sorted(LIBRARIES_DIR.glob("*.json")):
            _migrate_library_file(lib_path, user_map, score_map)
    for old_sid, new_sid in score_map.items():
        _migrate_score_dir(old_sid, new_sid, user_map)
    for sid in list_all_score_ids():
        if sid in score_map:
            continue
        _migrate_score_files_in_place(sid, user_map)


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


def sanitize_stored_filename(filename: str) -> str:
    stem, ext = split_filename(filename)
    stem = sanitize_stored_stem(stem)
    if ext:
        ext = sanitize_stored_stem(ext, max_len=20).lower()
        return f"{stem}.{ext}" if ext else stem
    return stem


def _unique_with_suffix(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def unique_id(label: str, taken: set[str], prefix: str = "") -> str:
    return _unique_with_suffix(f"{prefix}{_slug(label)}", taken)


def _unique_basename(stem: str, ext: str, taken: set[str]) -> str:
    candidate = f"{stem}.{ext}" if ext else stem
    if candidate not in taken:
        return candidate
    n = 2
    while True:
        suffixed = f"{stem}_{n}.{ext}" if ext else f"{stem}_{n}"
        if suffixed not in taken:
            return suffixed
        n += 1


def unique_stored_filename(filename: str, files_dir: Path) -> str:
    stored = sanitize_stored_filename(filename)
    taken = {p.name for p in files_dir.iterdir() if p.is_file()} if files_dir.exists() else set()
    if stored not in taken:
        return stored
    stem, ext = split_filename(stored)
    return _unique_basename(stem, ext, taken)


def file_id_from_name(filename: str, existing_ids: set[str]) -> str:
    stem, _ = split_filename(filename)
    return unique_id(stem, existing_ids)


def _existing_score_dir_names() -> set[str]:
    if not SCORES_DIR.exists():
        return set()
    return {p.name for p in SCORES_DIR.iterdir() if p.is_dir()}


def score_id_from_label(label: str) -> str:
    return unique_id(label, _existing_score_dir_names(), SCORE_ID_PREFIX)


def canonical_score_id(label: str) -> str:
    return f"{SCORE_ID_PREFIX}{_slug(label)}"


def score_storage_exists(score_id: str) -> bool:
    try:
        if score_meta_path(score_id).exists():
            return True
        path = score_dir(score_id)
    except ValueError:
        return False
    return path.exists()


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


def user_id_from_username(username: str) -> str:
    label = _username_slug(username)
    if not label:
        raise ValueError("Username is required")
    return unique_id(label, {u["id"] for u in load_users()}, USER_LIBRARY_ID_PREFIX)


def _username_slug(username: str) -> str:
    return _slug(username.strip().lower())


def _apply_user_id_map(user_map: dict[str, str]) -> None:
    if not user_map:
        return
    empty_score_map: dict[str, str] = {}
    if LIBRARIES_DIR.exists():
        for lib_path in sorted(LIBRARIES_DIR.glob("*.json")):
            _migrate_library_file(lib_path, user_map, empty_score_map)
    for sid in list_all_score_ids():
        _migrate_score_files_in_place(sid, user_map)


def rename_user_id(old_id: str, username: str) -> str:
    taken = {u["id"] for u in load_users() if u["id"] != old_id}
    new_id = unique_id(_username_slug(username), taken, USER_LIBRARY_ID_PREFIX)
    if new_id == old_id:
        return old_id
    _apply_user_id_map({old_id: new_id})
    return new_id


def score_owner_id(user: dict) -> str:
    if user.get("role") == MAESTRO_ROLE:
        return SYSTEM_OWNER_ID
    return user["id"]


def is_maestro_role(role: str) -> bool:
    return role == MAESTRO_ROLE


def password_storage_secret() -> str:
    return os.environ.get("SECRET_KEY", "dev-change-me-in-production")


def _password_fernet(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def is_encrypted_password(stored: str) -> bool:
    return stored.startswith(PASSWORD_ENCRYPT_PREFIX)


def encrypt_stored_password(plain: str, secret: str) -> str:
    token = _password_fernet(secret).encrypt(plain.encode("utf-8")).decode("ascii")
    return PASSWORD_ENCRYPT_PREFIX + token


def decrypt_stored_password(stored: str, secret: str) -> str:
    if not is_encrypted_password(stored):
        raise ValueError("Password is not encrypted")
    token = stored[len(PASSWORD_ENCRYPT_PREFIX):].encode("ascii")
    return _password_fernet(secret).decrypt(token).decode("utf-8")


def set_user_password(user: dict, password: str, secret: str) -> None:
    if is_maestro_role(user.get("role", "")):
        user["password"] = encrypt_stored_password(password, secret)
    else:
        user["password"] = password


def finalize_user_role(user: dict, secret: str) -> None:
    stored = user.get("password")
    if not stored:
        return
    if is_maestro_role(user.get("role", "")):
        if not is_encrypted_password(stored):
            user["password"] = encrypt_stored_password(stored, secret)
    elif is_encrypted_password(stored):
        user.pop("password", None)


def password_for_display(user: dict) -> str:
    if is_maestro_role(user.get("role", "")):
        return ""
    stored = user.get("password") or ""
    if is_encrypted_password(stored):
        return ""
    return stored


def verify_user_password(user: dict, password: str, secret: str) -> bool:
    stored = user.get("password")
    if not stored:
        return False
    if is_encrypted_password(stored):
        try:
            return decrypt_stored_password(stored, secret) == password
        except InvalidToken:
            return False
    return stored == password


def load_users() -> list[dict]:
    return _read_json(USERS_PATH, [])


def save_users(users: list[dict]) -> None:
    _write_json(USERS_PATH, users)


def get_user(user_id: str) -> dict | None:
    for u in load_users():
        if u["id"] == user_id:
            return u
    return None


def get_user_by_username(username: str) -> dict | None:
    uname = username.strip().lower()
    for u in load_users():
        if u["username"].lower() == uname:
            return u
    return None


def library_path(library_id: str) -> Path:
    return LIBRARIES_DIR / f"{library_id}.json"


def is_user_library_id(library_id: str) -> bool:
    return library_id.startswith(USER_LIBRARY_ID_PREFIX)


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
        user = get_user(library_id)
        lib["display_name"] = user["display_name"] if user else library_id
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
        user = get_user(library_id)
        expected_name = user["display_name"] if user else library_id
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
    for lib_file in LIBRARIES_DIR.glob("*.json"):
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
    _assert_path_under_base(SCORES_DIR / score_id, SCORES_DIR)
    return score_id


def validate_stored_name(stored_name: str) -> str:
    return _reject_path_segments(stored_name, "stored file name")


def score_dir(score_id: str) -> Path:
    score_id = validate_score_id(score_id)
    return SCORES_DIR / score_id


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
    if not SCORES_DIR.exists():
        return []
    return [p.name for p in SCORES_DIR.iterdir() if p.is_dir() and (p / "meta.json").exists()]


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
    stored_name = unique_stored_filename(upload_file.filename or "file", dest_dir)
    dest = dest_dir / stored_name
    upload_file.save(dest)
    return stored_name, extension_of(stored_name)


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
    score_id = canonical_score_id(meta_fields["title"])
    if score_storage_exists(score_id):
        raise ValueError(SCORE_TITLE_COLLISION_MSG)
    upload_name = upload_file.filename or "score.pdf"
    sdir = score_dir(score_id)
    sdir.mkdir(parents=True, exist_ok=True)
    stored_name, _ = _write_uploaded_file(score_id, upload_file)
    file_id = file_id_from_name(upload_name, set())
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
        "owner_id": owner_id,
        MAIN_CONTENT_HASH_META_KEY: content_hash,
        "files": files,
        "created_at": utc_now_iso(),
    }
    save_score_meta(score_id, meta)
    fid = folder_id if folder_id else ROOT_FOLDER_ID
    assign_score_to_folder(library_id, score_id, fid)
    return meta


def update_score_metadata(score_id: str, metadata: dict) -> dict:
    meta = load_score_meta(score_id)
    if not meta:
        raise ValueError("Score not found")
    fields = normalize_metadata(metadata)
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
        "id": file_id_from_name(upload_name, existing_ids),
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
        "id": file_id_from_name(display, existing_ids),
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
    new_score_id = canonical_score_id(meta_fields["title"])
    if score_storage_exists(new_score_id):
        raise ValueError(SCORE_TITLE_COLLISION_MSG)
    score_dir(new_score_id).mkdir(parents=True, exist_ok=True)
    score_files_dir(new_score_id).mkdir(exist_ok=True)
    stored = target["stored_name"]
    _move_blob(src_score_id, stored, new_score_id)
    src["files"] = [f for f in src["files"] if f["id"] != file_id]
    new_file = {
        "id": target["id"],
        "role": "main",
        "stored_name": stored,
        "name": target.get("name", "Full score"),
        "media": "pdf",
    }
    content_hash = _digest_file(stored_file_path(new_score_id, stored))
    new_meta = {
        "id": new_score_id,
        **meta_fields,
        "owner_id": owner_id,
        MAIN_CONTENT_HASH_META_KEY: content_hash,
        "files": [new_file],
        "created_at": utc_now_iso(),
    }
    validate_score_files(new_meta["files"])
    save_score_meta(new_score_id, new_meta)
    _apply_main_out_rules(src)
    fid = folder_id if folder_id else ROOT_FOLDER_ID
    assign_score_to_folder(library_id, new_score_id, fid)
    return new_meta


def delete_score(score_id: str) -> None:
    validate_score_id(score_id)
    if LIBRARIES_DIR.exists():
        for lib_file in LIBRARIES_DIR.glob("*.json"):
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
    if SCORES_DIR.exists():
        for sdir in SCORES_DIR.iterdir():
            if not sdir.is_dir():
                continue
            meta = load_score_meta(sdir.name)
            if meta and meta.get("owner_id") == user_id:
                transfer_score_to_system(meta["id"])
    users = [u for u in load_users() if u["id"] != user_id]
    save_users(users)
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
