"""Shared high-level Droid client bootstrap and cleanup."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from droid_sdk.client import DroidClient
from droid_sdk.errors import (
    DroidConnectionError,
    DroidError,
    InvalidWorkingDirectoryError,
)
from droid_sdk.transport import ProcessTransport

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from droid_sdk._high_level.runtime import Runtime
    from droid_sdk.observability import ObservabilityAdapter
    from droid_sdk.types import DroidClientTransport


def resolve_working_directory(value: str | Path | None) -> Path:
    path = Path.cwd() if value is None else Path(value)
    try:
        if not path.is_dir():
            raise InvalidWorkingDirectoryError(str(path))
        return path.resolve()
    except OSError as exc:
        raise InvalidWorkingDirectoryError(str(path)) from exc


def _runtime_transport(
    runtime: Runtime,
    *,
    api_key: str | None,
    cwd: Path,
) -> DroidClientTransport:
    if runtime.transport is not None:
        if not runtime.transport.is_connected:
            raise DroidError("A supplied transport must already be connected")
        return runtime.transport

    key = api_key or os.environ.get("FACTORY_API_KEY")
    env = dict(runtime.env)
    if key:
        env["FACTORY_API_KEY"] = key
    executable = "droid" if runtime.executable is None else str(runtime.executable)
    return ProcessTransport(
        exec_path=executable,
        exec_args=[
            "exec",
            "--input-format",
            "stream-jsonrpc",
            "--output-format",
            "stream-jsonrpc",
            *runtime.args,
        ],
        cwd=str(cwd),
        env=env,
    )


async def open_droid_client(
    runtime: Runtime,
    *,
    api_key: str | None,
    cwd: Path,
    observability: ObservabilityAdapter,
) -> DroidClient:
    """Create and connect a client from the shared high-level runtime contract."""
    transport = _runtime_transport(
        runtime,
        api_key=api_key,
        cwd=cwd,
    )
    client = DroidClient(
        transport=transport,
        trace_meta_injector=observability.trace_meta_injector,
        timing_callback=observability.timing_callback,
    )
    try:
        await client.connect()
    except BaseException as exc:
        await _close_after_failure(client, observability)
        if isinstance(exc, FileNotFoundError):
            raise DroidConnectionError(
                "Droid executable was not found",
                exec_path=(
                    None if runtime.executable is None else str(runtime.executable)
                ),
                cwd=str(cwd),
            ) from exc
        raise
    return client


async def _close_after_failure(
    client: DroidClient,
    observability: ObservabilityAdapter,
) -> None:
    try:
        await close_droid_client(client)
    except BaseException as exc:
        observability.log(
            level="error",
            name="droid.sdk.client.close",
            message="Droid client cleanup failed",
            attributes={"status": "error"},
            error=exc,
        )


async def close_droid_client(client: DroidClient) -> None:
    """Close a client to completion without swallowing cleanup failures."""
    close_task = asyncio.create_task(client.close())
    try:
        await asyncio.shield(close_task)
    except asyncio.CancelledError:
        await close_task
        raise


@asynccontextmanager
async def managed_droid_client(
    runtime: Runtime,
    *,
    api_key: str | None,
    cwd: Path,
    observability: ObservabilityAdapter,
) -> AsyncGenerator[DroidClient]:
    """Own one connected client while preserving primary operation failures."""
    client = await open_droid_client(
        runtime,
        api_key=api_key,
        cwd=cwd,
        observability=observability,
    )
    try:
        yield client
    except BaseException:
        await _close_after_failure(client, observability)
        raise
    await close_droid_client(client)


__all__ = [
    "managed_droid_client",
    "open_droid_client",
    "resolve_working_directory",
]
