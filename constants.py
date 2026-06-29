"""Shared constants for the score portal."""

import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
APP_NAME = "Score Store"
VERSION_FILENAME = "VERSION"
DEFAULT_VERSION = "0.0.0"
INSTANCE_DIR = APP_ROOT / "instance"
INSTANCE_CONFIG_PATH = INSTANCE_DIR / "config.json"
DEFAULT_DATA_DIR_NAME = "data"
DEFAULT_ADMIN_USERNAME = "admin"
MAESTRO_USERS_FILENAME = "users.json"
SETUP_PASSWORD_MIN_LEN = 8
MAESTRO_CONFIG_FILENAME = "config.json"
DEFAULT_SHOW_SITE_TITLE = True
DEFAULT_ENABLE_PRINTING = True
DEFAULT_ENABLE_DOWNLOAD = True
MAESTRO_THEME_FILENAME = "theme.css"
MAESTRO_ASSETS_DIRNAME = "assets"
LOGOTYPE_STORED_BASENAME = "logotype"
LOGOTYPE_EXTENSIONS = frozenset({"png", "jpeg", "jpg", "gif", "webp", "svg"})

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
LIBRARY_VIEW_LIST = "list"
LIBRARY_VIEW_FOLDER = "folder"
DEFAULT_LIBRARY_VIEW = LIBRARY_VIEW_LIST
FILE_NAME_MAX_LEN = 80
TAG_MAX_LEN = 40
GLOBAL_LIBRARY_ID = "_global"
SYSTEM_OWNER_ID = "_system"
ADMIN_ROLE = "admin"
MAESTRO_ROLE = "maestro"
SINGER_ROLE = "singer"
CHOIR_ROLE = "choir"
PASSWORD_ENCRYPT_PREFIX = "enc:"
ROLES_WITH_ENCRYPTED_PASSWORD = frozenset({ADMIN_ROLE, MAESTRO_ROLE})
SUB_ACCOUNT_ROLES = frozenset({SINGER_ROLE, CHOIR_ROLE})
DEFAULT_MAESTRO_THEME_CSS = """\
:root {
  --color-primary: #8b4513;
  --color-primary-hover: #6d3610;
  --color-bg: #faf6f0;
  --color-accent-bg: #f0e6d8;
}
"""
SCORE_ID_PREFIX = "s-"
FILE_ID_PREFIX = "f-"
SCORE_RANDOM_ID_BYTES = 6
FILE_RANDOM_ID_BYTES = 6
STORED_NAME_RANDOM_BYTES = 16
STARTUP_LOCK_FILENAME = ".startup.lock"
DISK_USAGE_CACHE_TTL_SEC = 60
MAIN_CONTENT_HASH_META_KEY = "main_content_hash"
FILE_HASH_READ_BYTES = 65536
BYTES_PER_SIZE_UNIT = 1024
SIZE_UNIT_LABELS = ("B", "KB", "MB", "GB", "TB")
SCORE_YEAR_PATTERN = re.compile(r"^\d{4}$")
SCORE_YEAR_MIN = 1000
SCORE_YEAR_MAX = 9999
UNSAFE_PATH_CHAR_PATTERN = re.compile(r'[/\\:*?"<>|\0]')
WHITESPACE_PATTERN = re.compile(r"\s+")
MULTI_SEP_PATTERN = re.compile(r"[-_]+")
FOLDER_PARENT_KEY = "parent_id"
USER_NOTES_DIRNAME = "user-notes"
BACKUPS_DIRNAME = "backups"
BACKUP_ZIP_EXTENSION = ".zip"
BACKUP_FILENAME_TIMESTAMP_FORMAT = "%Y-%m-%d_%H%M%S"
BACKUP_ACCOUNT_USERS_ARCHIVE_NAME = "account_users.json"
MAESTRO_KEY_BACKUP_ENABLED = "backup_enabled"
MAESTRO_KEY_BACKUP_RETENTION = "backup_retention_count"
DEFAULT_BACKUP_ENABLED = False
DEFAULT_BACKUP_RETENTION_COUNT = 5
BACKUP_RETENTION_MIN = 1
BACKUP_RETENTION_MAX = 100
