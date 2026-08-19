"""Small dependency-free asyncio helpers shared across layers."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine

T = TypeVar("T")


def consume_task_result(task: asyncio.Future[Any]) -> None:
    """Retrieve a background task's outcome so it never warns as unretrieved."""
    with contextlib.suppress(BaseException):
        task.result()


async def wait_shielded(
    task: asyncio.Task[T],
    on_cancelled: Callable[[asyncio.Task[T]], Awaitable[None]] | None = None,
) -> T:
    """Await a shared task without letting the caller's cancellation cancel it.

    When the caller is cancelled, ``on_cancelled`` runs to completion before
    the cancellation propagates, so compensation cannot itself be skipped by
    the cancellation that triggered it.
    """
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        if on_cancelled is not None:
            await on_cancelled(task)
        raise


async def run_to_completion(operation: Coroutine[Any, Any, T]) -> T:
    """Run an async cleanup operation to completion despite caller cancellation."""
    task = asyncio.create_task(operation)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


async def cancel_and_drain(task: asyncio.Task[Any]) -> None:
    """Cancel a task and wait until it settles, swallowing its outcome."""
    if not task.done():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def cancellation_checkpoint() -> None:
    """Yield once so a pending cancellation is delivered at this point."""
    await asyncio.sleep(0)
