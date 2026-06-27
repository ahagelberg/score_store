"""Maestro site configuration model."""

from __future__ import annotations

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
    ):
        self.site_title = site_title
        self.logotype = logotype
        self.show_site_title = show_site_title

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_title": self.site_title,
            "logotype": self.logotype,
            "show_site_title": self.show_site_title,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MaestroConfig:
        return cls(
            data.get("site_title", ""),
            data.get("logotype", ""),
            bool(data.get("show_site_title", c.DEFAULT_SHOW_SITE_TITLE)),
        )

    def header_show_title(self, has_logotype: bool) -> bool:
        if self.show_site_title:
            return True
        return not has_logotype
