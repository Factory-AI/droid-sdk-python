"""Deterministic local saved-session discovery."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from droid_sdk._high_level.config import SavedSession


def _sessions_root() -> Path:
    return Path.home() / ".factory" / "sessions"


def _project_directory_name(cwd: Path) -> str:
    try:
        normalized = cwd.expanduser().resolve(strict=True)
    except OSError:
        normalized = cwd.expanduser().resolve(strict=False)
    value = str(normalized).rstrip("/\\")
    if os.name == "nt":
        drive, tail = os.path.splitdrive(value)
        value = f"{drive.rstrip(':')}{tail}"
    return "-" + value.lstrip("/\\").replace("\\", "-").replace("/", "-")


async def list_sessions(
    *,
    cwd: str | Path | None = None,
    all_workspaces: bool = False,
    limit: int | None = None,
) -> list[SavedSession]:
    """Read local session metadata without starting Droid."""
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    selected_cwd = Path(Path.cwd() if cwd is None else cwd).resolve()
    root = _sessions_root()
    return await asyncio.to_thread(
        _list_sessions_sync,
        root,
        selected_cwd,
        all_workspaces,
        limit,
    )


def _list_sessions_sync(
    root: Path,
    cwd: Path,
    all_workspaces: bool,
    limit: int | None,
) -> list[SavedSession]:
    favorites = _favorites(root)
    directories = [root]
    if all_workspaces:
        with contextlib.suppress(OSError):
            directories.extend(
                item
                for item in root.iterdir()
                if item.is_dir() and item.name.startswith("-")
            )
    else:
        directories.append(root / _project_directory_name(cwd))

    candidates: list[tuple[int, str, Path, bool]] = []
    for directory in directories:
        try:
            for path in directory.iterdir():
                if path.is_file() and path.suffix == ".jsonl":
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    candidates.append(
                        (
                            stat.st_mtime_ns,
                            path.stem,
                            path,
                            directory == root,
                        )
                    )
        except OSError:
            continue
    candidates.sort(key=lambda item: (-item[0], item[1], str(item[2])))

    by_id: dict[str, SavedSession] = {}
    for _, session_id, path, legacy in candidates:
        parsed = _parse_session(
            path,
            session_id,
            favorites,
            required_cwd=None if all_workspaces or not legacy else cwd,
        )
        if parsed is None:
            continue
        previous = by_id.get(parsed.id)
        if previous is None or parsed.modified_at > previous.modified_at:
            by_id[parsed.id] = parsed
    values = sorted(
        by_id.values(),
        key=lambda item: (-item.modified_at.timestamp(), item.id),
    )
    return values if limit is None else values[:limit]


def _favorites(root: Path) -> set[str]:
    try:
        value = json.loads((root / ".favorites").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return (
        {item for item in cast("list[object]", value) if isinstance(item, str)}
        if isinstance(value, list)
        else set()
    )


def _parse_session(
    path: Path,
    session_id: str,
    favorites: set[str],
    *,
    required_cwd: Path | None,
) -> SavedSession | None:
    try:
        stat = path.stat()
        with path.open("rb") as handle:
            first = handle.readline()
            if not first.strip():
                return None
            summary = json.loads(first)
            count = sum(1 for line in handle if line.strip())
        if not isinstance(summary, dict):
            return None
        summary_dict = cast("dict[str, Any]", summary)
        if summary_dict.get("type") != "session_start":
            return None
        title = summary_dict.get("title")
        if not isinstance(title, str):
            return None
        raw_cwd = summary_dict.get("cwd")
        parsed_cwd = Path(raw_cwd).resolve() if isinstance(raw_cwd, str) else None
        if required_cwd is not None and parsed_cwd != required_cwd:
            return None
        settings_path = path.with_name(f"{session_id}.settings.json")
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(settings, dict):
                settings_object = cast("dict[str, object]", settings)
                if settings_object.get("archivedAt"):
                    return None
        except (OSError, ValueError):
            pass
        created = getattr(stat, "st_birthtime", stat.st_ctime)
        return SavedSession(
            id=session_id,
            title=title,
            owner=(
                summary_dict["owner"]
                if isinstance(summary_dict.get("owner"), str)
                else ""
            ),
            message_count=count,
            modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
            created_at=datetime.fromtimestamp(created, timezone.utc),
            cwd=parsed_cwd,
            is_favorite=session_id in favorites,
        )
    except (OSError, ValueError, TypeError):
        return None


__all__ = ["list_sessions"]
