"""Maestro account backup archives."""

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import constants as c
import paths
import store
from models.maestro_config import MaestroConfig

FORM_BACKUP_ENABLED = c.MAESTRO_KEY_BACKUP_ENABLED
FORM_BACKUP_RETENTION = c.MAESTRO_KEY_BACKUP_RETENTION


def backup_settings(maestro_username: str) -> dict[str, bool | int]:
    cfg = MaestroConfig.from_dict(store.load_maestro_config(maestro_username))
    return cfg.backup_settings()


def apply_backup_config(maestro_username: str, form) -> dict[str, bool | int]:
    cfg = store.load_maestro_config(maestro_username)
    mc = MaestroConfig.from_dict(cfg)
    mc.backup_enabled = store.form_show_site_title_checked(form.get(FORM_BACKUP_ENABLED))
    raw = form.get(FORM_BACKUP_RETENTION, "")
    try:
        count = int(raw)
    except (TypeError, ValueError):
        raise ValueError("Invalid number of backups to keep")
    mc.backup_retention_count = MaestroConfig._clamp_backup_retention(count)
    store.save_maestro_config(maestro_username, mc.to_dict())
    return mc.backup_settings()


def _backup_filename(maestro_username: str, when: datetime) -> str:
    stamp = when.strftime(c.BACKUP_FILENAME_TIMESTAMP_FORMAT)
    return f"{stamp}_{maestro_username}{c.BACKUP_ZIP_EXTENSION}"


def _account_user_records(maestro_username: str) -> list[dict]:
    maestro = store.get_user_by_username(maestro_username)
    if not maestro or not maestro.is_maestro():
        raise ValueError("Unknown maestro")
    records = [maestro.to_dict()]
    for user in store.get_users_for_maestro(maestro_username):
        if user.username != maestro_username:
            records.append(user.to_dict())
    return records


def _write_maestro_zip(source_dir: Path, dest: Path, account_users: list[dict]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            archive.write(path, path.relative_to(source_dir).as_posix())
        archive.writestr(
            c.BACKUP_ACCOUNT_USERS_ARCHIVE_NAME,
            json.dumps(account_users, indent=2, ensure_ascii=False) + "\n",
        )


def prune_maestro_backups(maestro_username: str, keep: int) -> list[str]:
    backup_dir = paths.maestro_backups_dir(maestro_username)
    if not backup_dir.is_dir():
        return []
    archives = sorted(
        (
            path for path in backup_dir.iterdir()
            if path.is_file() and path.name.endswith(c.BACKUP_ZIP_EXTENSION)
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    removed: list[str] = []
    for path in archives[keep:]:
        path.unlink()
        removed.append(path.name)
    return removed


def create_maestro_backup(maestro_username: str) -> dict:
    uname = maestro_username.strip().lower()
    settings = backup_settings(uname)
    if not settings["enabled"]:
        raise ValueError("Backups are disabled for this account")
    source = paths.maestro_data_dir(uname)
    if not source.is_dir():
        raise ValueError("Maestro data folder not found")
    when = datetime.now(timezone.utc)
    filename = _backup_filename(uname, when)
    dest = paths.maestro_backups_dir(uname) / filename
    account_users = _account_user_records(uname)
    _write_maestro_zip(source, dest, account_users)
    keep = int(settings["retention"])
    removed = prune_maestro_backups(uname, keep)
    size_bytes = dest.stat().st_size
    return {
        "filename": filename,
        "path": str(dest),
        "size_bytes": size_bytes,
        "size_label": store.format_byte_size(size_bytes),
        "created_at": when.isoformat(),
        "removed": removed,
        "retention": keep,
        "enabled": True,
    }


def list_maestro_backups(maestro_username: str) -> list[dict]:
    uname = maestro_username.strip().lower()
    backup_dir = paths.maestro_backups_dir(uname)
    if not backup_dir.is_dir():
        return []
    rows: list[dict] = []
    for path in sorted(backup_dir.iterdir(), key=lambda item: item.name, reverse=True):
        if not path.is_file() or not path.name.endswith(c.BACKUP_ZIP_EXTENSION):
            continue
        stat = path.stat()
        rows.append({
            "filename": path.name,
            "size_bytes": stat.st_size,
            "size_label": store.format_byte_size(stat.st_size),
            "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    return rows


def resolve_backup_file(maestro_username: str, filename: str) -> Path:
    uname = maestro_username.strip().lower()
    if not filename.endswith(c.BACKUP_ZIP_EXTENSION) or Path(filename).name != filename:
        raise ValueError("Invalid backup filename")
    path = paths.maestro_backups_dir(uname) / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path


def delete_maestro_backup(maestro_username: str, filename: str) -> str:
    path = resolve_backup_file(maestro_username, filename)
    path.unlink()
    return path.name
