"""Application metadata read from the project root."""

from constants import APP_NAME, APP_ROOT, DEFAULT_VERSION, VERSION_FILENAME


def read_version() -> str:
    path = APP_ROOT / VERSION_FILENAME
    if not path.is_file():
        return DEFAULT_VERSION
    text = path.read_text(encoding="utf-8").strip()
    return text or DEFAULT_VERSION


def system_info() -> dict:
    return {
        "name": APP_NAME,
        "version": read_version(),
    }
