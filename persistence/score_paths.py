"""Score path validation helpers."""

from pathlib import Path

import paths
from paths import scores_dir


def _reject_path_segments(value: str, label: str) -> str:
    text = value.strip()
    if not text or text in (".", ".."):
        raise ValueError(f"Invalid {label}")
    basename = Path(text).name.replace("\\", "/").split("/")[-1]
    if text != basename:
        raise ValueError(f"Invalid {label}")
    return text


def _assert_path_under_base(path: Path, base: Path) -> None:
    resolved = path.resolve()
    base_resolved = base.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise ValueError("Path escapes base directory")


def validate_score_id(score_id: str) -> str:
    score_id = _reject_path_segments(score_id, "score id")
    _assert_path_under_base(scores_dir() / score_id, scores_dir())
    return score_id


def validate_stored_name(stored_name: str) -> str:
    return _reject_path_segments(stored_name, "stored file name")


def score_dir(score_id: str) -> Path:
    score_id = validate_score_id(score_id)
    return scores_dir() / score_id


def score_files_dir(score_id: str) -> Path:
    return score_dir(score_id) / "files"


def score_meta_path(score_id: str) -> Path:
    return score_dir(score_id) / "meta.json"


def stored_file_path(score_id: str, stored_name: str) -> Path:
    name = validate_stored_name(stored_name)
    files_dir = score_files_dir(score_id)
    path = files_dir / name
    _assert_path_under_base(path, files_dir)
    return path
