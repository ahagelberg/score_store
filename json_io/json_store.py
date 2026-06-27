"""Thread-safe JSON file persistence."""

import json
import threading
from pathlib import Path

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


class JsonStore:
    """Read and write JSON documents atomically with per-path locking."""

    @staticmethod
    def read(path: Path, default):
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock_for(path):
            if not path.exists():
                return json.loads(json.dumps(default))
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)

    @staticmethod
    def write(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock_for(path):
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            tmp.replace(path)

    @staticmethod
    def read_list(path: Path) -> list:
        return JsonStore.read(path, [])

    @staticmethod
    def write_list(path: Path, items: list) -> None:
        JsonStore.write(path, items)

    @staticmethod
    def read_dict(path: Path) -> dict:
        return JsonStore.read(path, {})

    @staticmethod
    def write_dict(path: Path, data: dict) -> None:
        JsonStore.write(path, data)
