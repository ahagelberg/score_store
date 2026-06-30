"""Maestro account backup archives."""

import json
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import constants as c
import paths
import store
from models.maestro_config import MaestroConfig

FORM_BACKUP_ENABLED = c.MAESTRO_KEY_BACKUP_ENABLED
FORM_BACKUP_RETENTION = c.MAESTRO_KEY_BACKUP_RETENTION
FORM_BACKUP_SCHEDULE = c.MAESTRO_KEY_BACKUP_SCHEDULE


def backup_settings(maestro_username: str) -> dict[str, bool | int | str]:
    cfg = MaestroConfig.from_dict(store.load_maestro_config(maestro_username))
    return cfg.backup_settings()


def apply_backup_config(maestro_username: str, form) -> dict[str, bool | int | str]:
    cfg = store.load_maestro_config(maestro_username)
    mc = MaestroConfig.from_dict(cfg)
    mc.backup_enabled = store.form_show_site_title_checked(form.get(FORM_BACKUP_ENABLED))
    raw = form.get(FORM_BACKUP_RETENTION, "")
    try:
        count = int(raw)
    except (TypeError, ValueError):
        raise ValueError("Invalid number of backups to keep")
    schedule = form.get(FORM_BACKUP_SCHEDULE, "").strip().lower()
    if schedule not in c.BACKUP_SCHEDULE_VALUES:
        raise ValueError("Invalid backup schedule")
    mc.backup_retention_count = MaestroConfig._clamp_backup_retention(count)
    mc.backup_schedule = schedule
    store.save_maestro_config(maestro_username, mc.to_dict())
    return mc.backup_settings()


def mark_scheduled_backup_done(maestro_username: str, run_date: date) -> None:
    cfg = store.load_maestro_config(maestro_username)
    mc = MaestroConfig.from_dict(cfg)
    mc.backup_last_scheduled = run_date.isoformat()
    store.save_maestro_config(maestro_username, mc.to_dict())


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
    return _create_maestro_backup(uname, count_as_scheduled=True)


def run_scheduled_maestro_backup(maestro_username: str, run_date: date) -> dict | None:
    uname = maestro_username.strip().lower()
    mc = MaestroConfig.from_dict(store.load_maestro_config(uname))
    if not mc.scheduled_backup_due(run_date):
        return None
    result = _create_maestro_backup(uname, count_as_scheduled=True)
    result["scheduled"] = True
    return result


def run_due_scheduled_backups(run_at: datetime | None = None) -> list[dict]:
    when = (run_at or datetime.now().astimezone()).astimezone()
    if not past_schedule_time(when):
        return []
    run_date = when.date()
    results: list[dict] = []
    for maestro in store.get_maestro_accounts():
        try:
            result = run_scheduled_maestro_backup(maestro.username, run_date)
        except (ValueError, OSError):
            continue
        if result:
            results.append(result)
    return results


def past_schedule_time(when: datetime) -> bool:
    local = when.astimezone()
    target = local.replace(
        hour=c.BACKUP_SCHEDULE_HOUR,
        minute=c.BACKUP_SCHEDULE_MINUTE,
        second=0,
        microsecond=0,
    )
    return local >= target


def _create_maestro_backup(maestro_username: str, *, count_as_scheduled: bool = False) -> dict:
    uname = maestro_username.strip().lower()
    source = paths.maestro_data_dir(uname)
    if not source.is_dir():
        raise ValueError("Maestro data folder not found")
    when = datetime.now(timezone.utc)
    filename = _backup_filename(uname, when)
    dest = paths.maestro_backups_dir(uname) / filename
    account_users = _account_user_records(uname)
    _write_maestro_zip(source, dest, account_users)
    settings = backup_settings(uname)
    keep = int(settings["retention"])
    removed = prune_maestro_backups(uname, keep)
    if count_as_scheduled:
        mark_scheduled_backup_done(uname, when.astimezone().date())
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
