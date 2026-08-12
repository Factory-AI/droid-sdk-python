"""Small dependency-free asyncio helpers shared across layers."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncio


def consume_task_result(task: asyncio.Future[Any]) -> None:
    """Retrieve a background task's outcome so it never warns as unretrieved."""
    with contextlib.suppress(BaseException):
        task.result()
