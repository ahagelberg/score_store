"""Filesystem path resolution for data storage."""

import json
import os
from pathlib import Path

import constants as c
from json_io.json_store import JsonStore
from scope import require_maestro_data

DATA_DIR = Path(__file__).resolve().parent / c.DEFAULT_DATA_DIR_NAME
USERS_PATH = DATA_DIR / "users.json"


def _read_instance_config() -> dict:
    if not c.INSTANCE_CONFIG_PATH.exists():
        return {}
    with open(c.INSTANCE_CONFIG_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _initial_data_dir() -> Path:
    cfg = _read_instance_config()
    if cfg.get("data_dir"):
        return Path(cfg["data_dir"]).expanduser()
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    return c.APP_ROOT / c.DEFAULT_DATA_DIR_NAME


def init_paths() -> None:
    global DATA_DIR, USERS_PATH
    DATA_DIR = _initial_data_dir()
    USERS_PATH = DATA_DIR / "users.json"


init_paths()


def reconfigure_data_dir(data_dir: Path) -> Path:
    global DATA_DIR, USERS_PATH
    resolved = data_dir.expanduser().resolve()
    DATA_DIR = resolved
    USERS_PATH = DATA_DIR / "users.json"
    return resolved


def reload_data_dir_from_instance() -> Path:
    cfg = _read_instance_config()
    if cfg.get("data_dir"):
        return reconfigure_data_dir(Path(cfg["data_dir"]))
    return DATA_DIR


def save_instance_config(data_dir: Path) -> None:
    c.INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    resolved = data_dir.expanduser().resolve()
    cfg = _read_instance_config()
    cfg["data_dir"] = str(resolved)
    JsonStore.write_dict(c.INSTANCE_CONFIG_PATH, cfg)


def read_instance_config() -> dict:
    return _read_instance_config()


def update_instance_config(updates: dict) -> None:
    c.INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    cfg = _read_instance_config()
    cfg.update(updates)
    JsonStore.write_dict(c.INSTANCE_CONFIG_PATH, cfg)


def backups_root() -> Path:
    return DATA_DIR.parent / c.BACKUPS_DIRNAME


def maestro_backups_dir(maestro_username: str) -> Path:
    uname = maestro_username.strip().lower()
    if not uname:
        raise ValueError("Maestro username is required")
    return backups_root() / uname


def backup_scheduler_lock_path() -> Path:
    return c.INSTANCE_DIR / c.BACKUP_SCHEDULER_LOCK_FILENAME


def resolve_data_dir(path_str: str) -> Path:
    raw = path_str.strip()
    if not raw:
        raise ValueError("Storage path is required")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (c.APP_ROOT / candidate).resolve()
    candidate.mkdir(parents=True, exist_ok=True)
    probe = candidate / ".write_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    return candidate


def default_setup_data_dir_display() -> str:
    return str((c.APP_ROOT / c.DEFAULT_DATA_DIR_NAME).resolve())


def default_data_dir() -> Path:
    return (c.APP_ROOT / c.DEFAULT_DATA_DIR_NAME).resolve()


def maestro_data_dir(maestro_username: str) -> Path:
    uname = maestro_username.strip().lower()
    if not uname:
        raise ValueError("Maestro username is required")
    return DATA_DIR / uname


def maestro_users_path(maestro_username: str) -> Path:
    return maestro_data_dir(maestro_username) / c.MAESTRO_USERS_FILENAME


def scores_dir() -> Path:
    return maestro_data_dir(require_maestro_data()) / "scores"


def libraries_dir() -> Path:
    return maestro_data_dir(require_maestro_data()) / "libraries"


def user_notes_dir() -> Path:
    return maestro_data_dir(require_maestro_data()) / c.USER_NOTES_DIRNAME


def user_notes_path(user_id: str) -> Path:
    return user_notes_dir() / f"{user_id}.json"


def maestro_config_path(maestro_username: str) -> Path:
    return maestro_data_dir(maestro_username) / c.MAESTRO_CONFIG_FILENAME


def maestro_theme_path(maestro_username: str) -> Path:
    return maestro_data_dir(maestro_username) / c.MAESTRO_THEME_FILENAME


def library_path(library_id: str) -> Path:
    return libraries_dir() / f"{library_id}.json"


def ensure_maestro_data_dirs(maestro_username: str) -> None:
    base = maestro_data_dir(maestro_username)
    (base / "scores").mkdir(parents=True, exist_ok=True)
    (base / "libraries").mkdir(parents=True, exist_ok=True)
    (base / c.USER_NOTES_DIRNAME).mkdir(parents=True, exist_ok=True)
    (base / c.MAESTRO_ASSETS_DIRNAME).mkdir(parents=True, exist_ok=True)


from persistence.score_paths import (  # noqa: E402
    score_dir,
    score_files_dir,
    score_meta_path,
    stored_file_path,
    validate_score_id,
    validate_stored_name,
)
