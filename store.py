"""Filesystem JSON store for score portal."""

import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

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

ROOT_FOLDER_ID = "root"
LIBRARY_VIEW_LIST = "list"
LIBRARY_VIEW_FOLDER = "folder"
DEFAULT_LIBRARY_VIEW = LIBRARY_VIEW_LIST
FILE_NAME_MAX_LEN = 80
TAG_MAX_LEN = 40
GLOBAL_LIBRARY_ID = "_global"

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


def complete_setup(username: str, password: str, data_dir: Path, password_hash_fn) -> dict:
    if len(password) < SETUP_PASSWORD_MIN_LEN:
        raise ValueError(f"Password must be at least {SETUP_PASSWORD_MIN_LEN} characters")
    uname = username.strip().lower()
    if not uname:
        raise ValueError("Username is required")
    resolved = resolve_data_dir(str(data_dir))
    save_instance_config(resolved)
    reconfigure_data_dir(resolved)
    ensure_data_dirs()
    users = [{
        "id": new_id("u-"),
        "display_name": "Maestro",
        "username": uname,
        "password_hash": password_hash_fn(password),
        "role": "maestro",
    }]
    save_users(users)
    load_library(GLOBAL_LIBRARY_ID)
    return users[0]


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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str = "") -> str:
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}{uid}" if prefix else uid


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


def default_library() -> dict:
    return {
        "folders": [{"id": ROOT_FOLDER_ID, "name": "All scores"}],
        "score_folders": {},
        "score_order": [],
        "file_aliases": {},
    }


def load_library(library_id: str) -> dict:
    lib = _read_json(library_path(library_id), default_library())
    if not lib.get("folders"):
        lib["folders"] = [{"id": ROOT_FOLDER_ID, "name": "All scores"}]
    for key in ("score_folders", "score_order", "file_aliases"):
        lib.setdefault(key, {} if key != "score_order" else [])
    return lib


def save_library(library_id: str, lib: dict) -> None:
    _write_json(library_path(library_id), lib)


def score_dir(score_id: str) -> Path:
    return SCORES_DIR / score_id


def score_meta_path(score_id: str) -> Path:
    return score_dir(score_id) / "meta.json"


def load_score_meta(score_id: str) -> dict | None:
    path = score_meta_path(score_id)
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


def file_display_name(score_meta: dict, file_id: str, user_id: str | None, library_id: str | None) -> str:
    aliases = {}
    if library_id:
        lib = load_library(library_id)
        aliases = lib.get("file_aliases", {}).get(user_id or "", {})
    if file_id in aliases and aliases[file_id]:
        return aliases[file_id]
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
    return score_dir(score_id) / "files" / stored_name


def assign_score_to_folder(library_id: str, score_id: str, folder_id: str) -> None:
    lib = load_library(library_id)
    lib["score_folders"][score_id] = folder_id
    if score_id not in lib["score_order"]:
        lib["score_order"].insert(0, score_id)
    save_library(library_id, lib)


def remove_score_from_library(library_id: str, score_id: str) -> None:
    lib = load_library(library_id)
    lib["score_folders"].pop(score_id, None)
    if score_id in lib["score_order"]:
        lib["score_order"].remove(score_id)
    save_library(library_id, lib)


def _write_uploaded_file(score_id: str, upload_file) -> tuple[str, str]:
    ext = extension_of(upload_file.filename or "file")
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest_dir = score_dir(score_id) / "files"
    dest_dir.mkdir(parents=True, exist_ok=True)
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
    score_id = new_id("s-")
    sdir = score_dir(score_id)
    sdir.mkdir(parents=True, exist_ok=True)
    stored_name, _ = _write_uploaded_file(score_id, upload_file)
    file_id = new_id("f-")
    files = [{
        "id": file_id,
        "role": "main",
        "stored_name": stored_name,
        "name": basename_display_name(upload_file.filename or "score.pdf"),
        "media": "pdf",
    }]
    validate_score_files(files)
    meta = {
        "id": score_id,
        **meta_fields,
        "owner_id": owner_id,
        "assigned_user_ids": [],
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
    entry = {
        "id": new_id("f-"),
        "role": "aux",
        "stored_name": stored_name,
        "name": basename_display_name(upload_file.filename or "file"),
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
    display = (name or "YouTube").strip()[:FILE_NAME_MAX_LEN] or "YouTube"
    entry = {
        "id": new_id("f-"),
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
    dst_dir = score_dir(dst_score_id) / "files"
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
    new_score_id = new_id("s-")
    score_dir(new_score_id).mkdir(parents=True, exist_ok=True)
    (score_dir(new_score_id) / "files").mkdir(exist_ok=True)
    stored = target["stored_name"]
    _move_blob(src_score_id, stored, new_score_id)
    src["files"] = [f for f in src["files"] if f["id"] != file_id]
    new_file = {
        "id": new_id("f-"),
        "role": "main",
        "stored_name": stored,
        "name": target.get("name", "Full score"),
        "media": "pdf",
    }
    new_meta = {
        "id": new_score_id,
        **meta_fields,
        "owner_id": owner_id,
        "assigned_user_ids": [],
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
    path = score_dir(score_id)
    if path.exists():
        shutil.rmtree(path)
    for lib_file in LIBRARIES_DIR.glob("*.json"):
        lib = _read_json(lib_file, default_library())
        changed = False
        if score_id in lib.get("score_folders", {}):
            lib["score_folders"].pop(score_id, None)
            changed = True
        if score_id in lib.get("score_order", []):
            lib["score_order"].remove(score_id)
            changed = True
        if changed:
            _write_json(lib_file, lib)


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


def custom_folders(lib: dict) -> list[dict]:
    return [folder for folder in lib.get("folders", []) if folder["id"] != ROOT_FOLDER_ID]


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


def user_can_edit_score(user: dict, meta: dict) -> bool:
    if user["role"] == "maestro":
        return True
    return meta.get("owner_id") == user["id"]


def user_can_view_score(user: dict, meta: dict, library_id: str | None = None) -> bool:
    if user["role"] == "maestro":
        return True
    if meta.get("owner_id") == user["id"]:
        return True
    if user["id"] in meta.get("assigned_user_ids", []):
        return True
    if library_id:
        lib = load_library(library_id)
        if sid := meta.get("id"):
            if sid in lib.get("score_order", []):
                return True
    return False
