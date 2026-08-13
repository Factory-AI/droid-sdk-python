"""List local saved sessions without starting Droid."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from droid_sdk import list_sessions


async def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        sessions = await list_sessions(
            cwd=Path(directory),
            limit=10,
        )
        assert sessions == []
        print("saved sessions:", len(sessions))


if __name__ == "__main__":
    asyncio.run(main())
