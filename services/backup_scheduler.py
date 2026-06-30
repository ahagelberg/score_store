"""Background scheduler for automatic maestro backups."""

from __future__ import annotations

import fcntl
import os
import threading
from datetime import datetime, timedelta

import constants as c
import paths
from services import maestro_backup as maestro_backup_service

FLASK_RELOADER_PARENT = "false"
_scheduler_started = False
_scheduler_start_lock = threading.Lock()
_leader_lock_handle = None


def _seconds_until_next_schedule(when: datetime) -> float:
    local = when.astimezone()
    target = local.replace(
        hour=c.BACKUP_SCHEDULE_HOUR,
        minute=c.BACKUP_SCHEDULE_MINUTE,
        second=0,
        microsecond=0,
    )
    if local >= target:
        target += timedelta(days=1)
    return (target - local).total_seconds()


def _try_acquire_leader_lock() -> bool:
    global _leader_lock_handle
    lock_path = paths.backup_scheduler_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _leader_lock_handle = handle
    return True


def _scheduler_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        now = datetime.now().astimezone()
        if maestro_backup_service.past_schedule_time(now):
            maestro_backup_service.run_due_scheduled_backups(now)
        wait_sec = _seconds_until_next_schedule(now)
        stop_event.wait(timeout=min(wait_sec, c.BACKUP_SCHEDULER_WAKE_INTERVAL_SEC))


def _should_start_in_process() -> bool:
    if os.environ.get("WERKZEUG_RUN_MAIN") == FLASK_RELOADER_PARENT:
        return False
    return True


def ensure_started() -> None:
    global _scheduler_started
    if not _should_start_in_process():
        return
    with _scheduler_start_lock:
        if _scheduler_started:
            return
        if not _try_acquire_leader_lock():
            return
        stop_event = threading.Event()
        thread = threading.Thread(
            target=_scheduler_loop,
            args=(stop_event,),
            name="backup-scheduler",
            daemon=True,
        )
        thread.start()
        _scheduler_started = True
