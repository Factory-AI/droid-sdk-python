from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest

import droid_sdk._high_level.discovery as discovery_module
from droid_sdk import list_sessions

if TYPE_CHECKING:
    from pathlib import Path


def write_session(
    root: Path,
    session_id: str,
    cwd: Path,
    *,
    title: str,
    mtime: float,
    messages: int = 0,
) -> None:
    lines = [
        json.dumps(
            {
                "type": "session_start",
                "title": title,
                "cwd": str(cwd),
                "owner": "owner@example.com",
            }
        ),
        *(json.dumps({"type": "message"}) for _ in range(messages)),
    ]
    path = root / f"{session_id}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))


@pytest.mark.asyncio
async def test_list_sessions_filters_sorts_limits_and_marks_favorites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "sessions"
    root.mkdir()
    monkeypatch.setattr(discovery_module, "_sessions_root", lambda: root)
    cwd = tmp_path / "project"
    cwd.mkdir()
    write_session(root, "older", cwd, title="Older", mtime=100, messages=2)
    write_session(root, "newer", cwd, title="Newer", mtime=200, messages=1)
    write_session(root, "other", tmp_path, title="Other", mtime=300)
    (root / "malformed.jsonl").write_text("{bad json", encoding="utf-8")
    (root / ".favorites").write_text('["older"]', encoding="utf-8")

    sessions = await list_sessions(cwd=cwd)
    assert [session.id for session in sessions] == ["newer", "older"]
    assert sessions[1].message_count == 2
    assert sessions[1].is_favorite is True
    assert [
        session.id
        for session in await list_sessions(
            cwd=cwd,
            limit=1,
        )
    ] == ["newer"]


@pytest.mark.asyncio
async def test_list_sessions_skips_archived_and_supports_all_workspaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "sessions"
    root.mkdir()
    monkeypatch.setattr(discovery_module, "_sessions_root", lambda: root)
    cwd = tmp_path / "project"
    cwd.mkdir()
    write_session(root, "active", cwd, title="Active", mtime=100)
    write_session(root, "archived", cwd, title="Archived", mtime=200)
    (root / "archived.settings.json").write_text(
        '{"archivedAt":"2025-01-01T00:00:00Z"}',
        encoding="utf-8",
    )

    sessions = await list_sessions(
        cwd=tmp_path,
        all_workspaces=True,
    )
    assert [session.id for session in sessions] == ["active"]


@pytest.mark.asyncio
async def test_list_sessions_rejects_invalid_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        await list_sessions(cwd=tmp_path, limit=-1)
