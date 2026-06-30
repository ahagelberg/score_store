"""Maestro site configuration model."""

from __future__ import annotations

from datetime import date
from typing import Any

import constants as c
from models.base import JsonModel


class MaestroConfig(JsonModel):
    """Branding and site settings for a maestro account."""

    def __init__(
        self,
        site_title: str,
        logotype: str = "",
        show_site_title: bool = c.DEFAULT_SHOW_SITE_TITLE,
        enable_printing: bool = c.DEFAULT_ENABLE_PRINTING,
        enable_download: bool = c.DEFAULT_ENABLE_DOWNLOAD,
        backup_enabled: bool = c.DEFAULT_BACKUP_ENABLED,
        backup_retention_count: int = c.DEFAULT_BACKUP_RETENTION_COUNT,
        backup_schedule: str = c.DEFAULT_BACKUP_SCHEDULE,
        backup_last_scheduled: str = "",
    ):
        self.site_title = site_title
        self.logotype = logotype
        self.show_site_title = show_site_title
        self.enable_printing = enable_printing
        self.enable_download = enable_download
        self.backup_enabled = backup_enabled
        self.backup_retention_count = self._clamp_backup_retention(backup_retention_count)
        self.backup_schedule = self._normalize_backup_schedule(backup_schedule)
        self.backup_last_scheduled = backup_last_scheduled.strip()

    @staticmethod
    def _clamp_backup_retention(count: int) -> int:
        return max(c.BACKUP_RETENTION_MIN, min(count, c.BACKUP_RETENTION_MAX))

    @staticmethod
    def _normalize_backup_schedule(schedule: str) -> str:
        value = schedule.strip().lower()
        if value in c.BACKUP_SCHEDULE_VALUES:
            return value
        return c.DEFAULT_BACKUP_SCHEDULE

    def to_dict(self) -> dict[str, Any]:
        data = {
            "site_title": self.site_title,
            "logotype": self.logotype,
            "show_site_title": self.show_site_title,
            "enable_printing": self.enable_printing,
            "enable_download": self.enable_download,
            c.MAESTRO_KEY_BACKUP_ENABLED: self.backup_enabled,
            c.MAESTRO_KEY_BACKUP_RETENTION: self.backup_retention_count,
            c.MAESTRO_KEY_BACKUP_SCHEDULE: self.backup_schedule,
        }
        if self.backup_last_scheduled:
            data[c.MAESTRO_KEY_BACKUP_LAST_SCHEDULED] = self.backup_last_scheduled
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MaestroConfig:
        raw_retention = data.get(c.MAESTRO_KEY_BACKUP_RETENTION, c.DEFAULT_BACKUP_RETENTION_COUNT)
        try:
            retention = int(raw_retention)
        except (TypeError, ValueError):
            retention = c.DEFAULT_BACKUP_RETENTION_COUNT
        return cls(
            data.get("site_title", ""),
            data.get("logotype", ""),
            bool(data.get("show_site_title", c.DEFAULT_SHOW_SITE_TITLE)),
            bool(data.get("enable_printing", c.DEFAULT_ENABLE_PRINTING)),
            bool(data.get("enable_download", c.DEFAULT_ENABLE_DOWNLOAD)),
            bool(data.get(c.MAESTRO_KEY_BACKUP_ENABLED, c.DEFAULT_BACKUP_ENABLED)),
            retention,
            data.get(c.MAESTRO_KEY_BACKUP_SCHEDULE, c.DEFAULT_BACKUP_SCHEDULE),
            data.get(c.MAESTRO_KEY_BACKUP_LAST_SCHEDULED, ""),
        )

    def header_show_title(self, has_logotype: bool) -> bool:
        if self.show_site_title:
            return True
        return not has_logotype

    def library_features(self) -> dict[str, bool]:
        return {
            "enable_printing": self.enable_printing,
            "enable_download": self.enable_download,
        }

    def backup_settings(self) -> dict[str, bool | int | str]:
        return {
            "enabled": self.backup_enabled,
            "retention": self.backup_retention_count,
            "schedule": self.backup_schedule,
            "last_scheduled": self.backup_last_scheduled,
        }

    def scheduled_backup_due(self, run_date: date) -> bool:
        if not self.backup_enabled:
            return False
        if self.backup_schedule not in c.BACKUP_SCHEDULE_VALUES:
            return False
        last = self._last_scheduled_date()
        if self.backup_schedule == c.BACKUP_SCHEDULE_DAILY:
            return last != run_date
        if self.backup_schedule == c.BACKUP_SCHEDULE_WEEKLY:
            if last is None:
                return True
            return (run_date - last).days >= c.BACKUP_SCHEDULE_WEEKLY_MIN_DAYS
        if last is None:
            return True
        return run_date.year != last.year or run_date.month != last.month

    def _last_scheduled_date(self) -> date | None:
        raw = self.backup_last_scheduled.strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None
