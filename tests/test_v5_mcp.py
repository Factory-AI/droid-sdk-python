from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx
import jsonschema
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, Field, ValidationError

import droid_sdk.mcp as mcp_module
from droid_sdk.mcp import ToolResponse, create_sdk_mcp_server, tool

if TYPE_CHECKING:
    from collections.abc import Mapping


@tool("add", "Add two integers")
def add(a: int, b: int) -> ToolResponse:
    return ToolResponse(str(a + b), structured_content={"result": a + b})


@tool("echo_async", "Echo text asynchronously")
async def echo_async(text: str) -> str:
    return text


class SumOutput(BaseModel):
    result: int


@tool("typed_add", "Return a typed sum")
def typed_add(a: int, b: int) -> SumOutput:
    return SumOutput(result=a + b)


class AliasedOutput(BaseModel):
    result_value: int = Field(serialization_alias="resultValue")
    generated_at: datetime = Field(serialization_alias="generatedAt")


@tool("aliased", "Return aliased, JSON-safe structured content")
def aliased() -> AliasedOutput:
    return AliasedOutput(
        result_value=7,
        generated_at=datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc),
    )


def test_mcp_module_requires_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "droid_sdk.mcp", raising=False)
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    with pytest.raises(ImportError, match=r"droid-sdk\[mcp\]"):
        importlib.import_module("droid_sdk.mcp")


def test_package_root_imports_without_mcp_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("uvicorn", "starlette", "mcp"):
        monkeypatch.setitem(sys.modules, name, None)
    for name in [key for key in sys.modules if key.split(".")[0] == "droid_sdk"]:
        monkeypatch.delitem(sys.modules, name)
    module = importlib.import_module("droid_sdk")
    assert module.StdioMcpServerConfig is not None


@pytest.mark.asyncio
async def test_tool_validates_arguments_for_sync_and_async_handlers() -> None:
    result = await add.handler({"a": 2, "b": 3})
    assert result.content == "5"
    assert result.structured_content == {"result": 5}
    assert await echo_async.handler({"text": "hello"}) == "hello"

    with pytest.raises(ValidationError):
        await add.handler({"a": "not-an-integer", "b": 3})

    assert typed_add.output_schema is not None
    assert typed_add.output_schema["type"] == "object"
    typed = await typed_add.handler({"a": 4, "b": 5})
    assert isinstance(typed, ToolResponse)
    assert typed.structured_content == {"result": 9}


def test_tool_rejects_unsupported_return_schema() -> None:
    with pytest.raises(TypeError, match="must describe an object"):

        @tool("bad", "Bad output")
        def bad() -> list[str]:
            return []


@pytest.mark.asyncio
async def test_sdk_mcp_server_supports_official_client() -> None:
    server = create_sdk_mcp_server("calculator", [add, typed_add, aliased])
    config = await server.start()
    headers: Mapping[str, str] = {
        header.name: header.value for header in config.headers
    }

    try:
        async with (
            httpx.AsyncClient(headers=headers) as http_client,
            streamable_http_client(
                config.url,
                http_client=http_client,
            ) as streams,
            ClientSession(streams[0], streams[1]) as client,
        ):
            await client.initialize()
            tools = await client.list_tools()
            assert [item.name for item in tools.tools] == [
                "add",
                "typed_add",
                "aliased",
            ]
            output_schema = tools.tools[1].outputSchema
            assert output_schema is not None
            assert output_schema["type"] == "object"
            assert output_schema["properties"]["result"]["type"] == "integer"
            assert output_schema["required"] == ["result"]

            result = await client.call_tool("add", {"a": 2, "b": 3})
            assert result.isError is False
            assert result.structuredContent == {"result": 5}

            typed_result = await client.call_tool(
                "typed_add",
                {"a": 4, "b": 5},
            )
            assert typed_result.structuredContent == {"result": 9}

            aliased_tool = tools.tools[2]
            aliased_schema = aliased_tool.outputSchema
            assert aliased_schema is not None
            assert set(aliased_schema["properties"]) == {
                "resultValue",
                "generatedAt",
            }
            aliased_result = await client.call_tool("aliased", {})
            assert aliased_result.structuredContent == {
                "resultValue": 7,
                "generatedAt": "2025-01-02T03:04:00Z",
            }
            jsonschema.validate(
                instance=aliased_result.structuredContent,
                schema=aliased_schema,
            )

            invalid = await client.call_tool(
                "add",
                {"a": "invalid", "b": 3},
            )
            assert invalid.isError is True
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_sdk_mcp_server_restarts_with_rotated_auth() -> None:
    server = create_sdk_mcp_server("calculator", [add])
    first = await server.start()
    await server.close()
    second = await server.start()
    try:
        assert first.url != second.url
        assert first.headers != second.headers
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_sdk_mcp_concurrent_start_and_cancellation_share_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = create_sdk_mcp_server("calculator", [add])
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    original = mcp_module._start_sdk_server_impl

    async def gated_start(server_value: object) -> object:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return await original(server_value)  # type: ignore[arg-type]

    monkeypatch.setattr(mcp_module, "_start_sdk_server_impl", gated_start)
    first = asyncio.create_task(server.start())
    await entered.wait()
    second = asyncio.create_task(server.start())
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert not second.done()

    release.set()
    config = await second
    try:
        assert calls == 1
        assert server.config is config
        runtime = server._runtime
        assert runtime is not None
        assert not runtime.task.done()  # type: ignore[attr-defined]
        assert runtime.listener.fileno() >= 0  # type: ignore[attr-defined]
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_sdk_mcp_lone_cancelled_start_is_cleaned_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = create_sdk_mcp_server("calculator", [add])
    entered = asyncio.Event()
    release = asyncio.Event()
    original = mcp_module._start_sdk_server_impl

    async def gated_start(server_value: object) -> object:
        entered.set()
        await release.wait()
        return await original(server_value)  # type: ignore[arg-type]

    monkeypatch.setattr(mcp_module, "_start_sdk_server_impl", gated_start)
    start = asyncio.create_task(server.start())
    await entered.wait()
    start.cancel()
    with pytest.raises(asyncio.CancelledError):
        await start

    release.set()
    await server.close()
    assert server.config is None
    lifecycle = server._lifecycle
    assert lifecycle is not None
    assert lifecycle.close_task.done()  # type: ignore[attr-defined]

    restarted = await server.start()
    try:
        assert restarted.url
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_sdk_mcp_cancelled_close_finishes_once_and_restarts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = create_sdk_mcp_server("calculator", [add])
    await server.start()
    runtime = server._runtime
    assert runtime is not None
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    original = mcp_module._close_sdk_server_impl

    async def gated_close(server_value: object, runtime_value: object) -> None:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        await original(server_value, runtime_value)  # type: ignore[arg-type]

    monkeypatch.setattr(mcp_module, "_close_sdk_server_impl", gated_close)
    first = asyncio.create_task(server.close())
    await entered.wait()
    second = asyncio.create_task(server.close())
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert not second.done()

    release.set()
    await second
    assert calls == 1
    assert server.config is None
    assert runtime.task.done()  # type: ignore[attr-defined]
    assert runtime.listener.fileno() == -1  # type: ignore[attr-defined]

    restarted = await server.start()
    try:
        assert restarted.url
    finally:
        await server.close()
