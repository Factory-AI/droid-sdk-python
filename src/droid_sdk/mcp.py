"""Public MCP configuration and authenticated in-process MCP tools."""

# ruff: noqa: TC002

from __future__ import annotations

import asyncio
import inspect
import json
import secrets
import socket
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, ParamSpec, cast, get_type_hints, overload

import uvicorn
from mcp import types as mcp_types
from mcp.server.lowlevel import Server as McpServer
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import ConfigDict, TypeAdapter, create_model
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from droid_sdk._high_level._immutable import FrozenJsonValue, thaw_json
from droid_sdk._high_level.extensions import (
    DroidTool,
    HttpHeader,
    HttpMcpServerConfig,
    McpOAuthOptions,
    McpServerConfig,
    SdkMcpServer,
    SseMcpServerConfig,
    StdioMcpServerConfig,
    ToolResponse,
)

P = ParamSpec("P")


def _serialize_structured_content(
    adapter: TypeAdapter[Any],
    value: object,
) -> dict[str, object]:
    validated = adapter.validate_python(value)
    dumped = adapter.dump_python(
        validated,
        mode="json",
        by_alias=True,
    )
    if not isinstance(dumped, Mapping):
        raise TypeError("Structured MCP tools must return an object")
    return dict(cast("Mapping[str, object]", dumped))


@overload
def tool(
    name: str,
    description: str,
) -> Callable[[Callable[P, object]], DroidTool]: ...


@overload
def tool(
    name: str,
    description: str,
    function: Callable[P, object],
) -> DroidTool: ...


def tool(
    name: str,
    description: str,
    function: Callable[P, object] | None = None,
) -> DroidTool | Callable[[Callable[P, object]], DroidTool]:
    """Create a validated MCP tool from an annotated Python callable."""

    def decorate(handler: Callable[P, object]) -> DroidTool:
        signature = inspect.signature(handler)
        hints = get_type_hints(handler)
        fields: dict[str, Any] = {}
        for parameter_name, parameter in signature.parameters.items():
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                raise TypeError("MCP tool parameters must be named parameters")
            annotation = hints.get(parameter_name)
            if annotation is None:
                raise TypeError(
                    f'MCP tool parameter "{parameter_name}" requires an annotation'
                )
            default = (
                ...
                if parameter.default is inspect.Parameter.empty
                else parameter.default
            )
            fields[parameter_name] = (annotation, default)

        arguments_model = create_model(
            f"{handler.__name__.title()}Arguments",
            __config__=ConfigDict(extra="forbid"),
            **fields,
        )
        adapter = TypeAdapter(arguments_model)
        return_annotation = hints.get("return")
        if return_annotation is None:
            raise TypeError("MCP tool handlers require a return annotation")
        output_adapter: TypeAdapter[Any] | None = None
        output_schema: dict[str, Any] | None = None
        if return_annotation not in {str, ToolResponse}:
            output_adapter = TypeAdapter(return_annotation)
            output_schema = output_adapter.json_schema(mode="serialization")
            if output_schema.get("type") != "object":
                raise TypeError(
                    "MCP structured tool return annotations must describe an object"
                )

        async def invoke(arguments: Mapping[str, object]) -> str | ToolResponse:
            parsed = adapter.validate_python(arguments)
            callable_handler = cast("Callable[..., object]", handler)
            value: object = callable_handler(**parsed.model_dump())
            if inspect.isawaitable(value):
                value = await cast("Awaitable[object]", value)
            if isinstance(value, (str, ToolResponse)):
                if output_adapter is not None:
                    if not isinstance(value, ToolResponse):
                        raise TypeError("Structured MCP tools must return an object")
                    if value.structured_content is None:
                        raise TypeError(
                            "Structured MCP ToolResponse requires structured_content"
                        )
                    structured = _serialize_structured_content(
                        output_adapter, value.structured_content
                    )
                    return ToolResponse(
                        content=value.content,
                        is_error=value.is_error,
                        structured_content=structured,
                    )
                return value
            if output_adapter is not None:
                structured = _serialize_structured_content(output_adapter, value)
                return ToolResponse(
                    content=json.dumps(structured, separators=(",", ":")),
                    structured_content=structured,
                )
            raise TypeError("MCP tool handlers must return str or ToolResponse")

        return DroidTool(
            name=name,
            description=description,
            input_schema=arguments_model.model_json_schema(mode="validation"),
            output_schema=output_schema,
            handler=invoke,
        )

    return decorate if function is None else decorate(function)


def create_sdk_mcp_server(
    name: str,
    tools: Sequence[DroidTool],
    version: str = "1.0.0",
) -> SdkMcpServer:
    """Create a restartable loopback-only Streamable HTTP MCP server."""
    return SdkMcpServer(name=name, version=version, tools=tools)


@dataclass(slots=True)
class _ServerRuntime:
    config: HttpMcpServerConfig
    token: str
    server: uvicorn.Server
    task: asyncio.Task[None]
    listener: socket.socket


@dataclass(slots=True)
class _ServerLifecycle:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    start_task: asyncio.Task[HttpMcpServerConfig] | None = None
    close_task: asyncio.Task[None] | None = None
    start_waiters: int = 0


def _server_lifecycle(server: SdkMcpServer) -> _ServerLifecycle:
    lifecycle = cast(
        "_ServerLifecycle | None",
        object.__getattribute__(server, "_lifecycle"),
    )
    if lifecycle is None:
        lifecycle = _ServerLifecycle()
        object.__setattr__(server, "_lifecycle", lifecycle)
    return lifecycle


class _BearerEndpoint:
    def __init__(
        self,
        manager: StreamableHTTPSessionManager,
        token: str,
    ) -> None:
        self._manager = manager
        self._token = token

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await Response(status_code=404)(scope, receive, send)
            return
        raw_headers = cast(
            "Sequence[tuple[bytes, bytes]]",
            scope.get("headers", ()),
        )
        authorization: bytes = dict(raw_headers).get(b"authorization", b"")
        try:
            scheme, supplied = authorization.decode("ascii").split(" ", 1)
        except (UnicodeDecodeError, ValueError):
            scheme, supplied = "", ""
        if scheme.lower() != "bearer" or not secrets.compare_digest(
            supplied,
            self._token,
        ):
            await JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": "Unauthorized"},
                    "id": None,
                },
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return
        await self._manager.handle_request(scope, receive, send)


def _create_mcp_application(server: SdkMcpServer, token: str) -> Starlette:
    low_level = McpServer(server.name, version=server.version)
    tools_by_name = {item.name: item for item in server.tools}

    @low_level.list_tools()  # type: ignore[untyped-decorator,no-untyped-call]
    async def _list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name=item.name,
                description=item.description,
                inputSchema=cast(
                    "dict[str, Any]",
                    thaw_json(cast("FrozenJsonValue", item.input_schema)),
                ),
                outputSchema=(
                    None
                    if item.output_schema is None
                    else cast(
                        "dict[str, Any]",
                        thaw_json(cast("FrozenJsonValue", item.output_schema)),
                    )
                ),
            )
            for item in server.tools
        ]

    @low_level.call_tool(validate_input=True)  # type: ignore[untyped-decorator]
    async def _call_tool(
        name: str,
        arguments: dict[str, Any],
    ) -> mcp_types.CallToolResult:
        selected = tools_by_name.get(name)
        if selected is None:
            raise ValueError(f"Unknown tool: {name}")
        value = selected.handler(arguments)
        if inspect.isawaitable(value):
            value = await cast("Awaitable[object]", value)
        if isinstance(value, str):
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(type="text", text=value)]
            )
        if not isinstance(value, ToolResponse):
            raise TypeError("MCP tool handlers must return str or ToolResponse")
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=value.content)],
            isError=value.is_error,
            structuredContent=(
                None
                if value.structured_content is None
                else cast(
                    "dict[str, Any]",
                    thaw_json(cast("FrozenJsonValue", value.structured_content)),
                )
            ),
        )

    _registered_handlers = (_list_tools, _call_tool)

    manager = StreamableHTTPSessionManager(
        app=low_level,
        stateless=True,
        json_response=True,
    )

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None, None]:
        async with manager.run():
            yield

    return Starlette(
        routes=[Route("/mcp", endpoint=_BearerEndpoint(manager, token))],
        lifespan=lifespan,
    )


def sdk_server_config(server: SdkMcpServer) -> HttpMcpServerConfig | None:
    runtime = cast(
        "_ServerRuntime | None",
        object.__getattribute__(server, "_runtime"),
    )
    return None if runtime is None else runtime.config


async def start_sdk_server(server: SdkMcpServer) -> HttpMcpServerConfig:
    lifecycle = _server_lifecycle(server)
    async with lifecycle.lock:
        current = cast(
            "_ServerRuntime | None",
            object.__getattribute__(server, "_runtime"),
        )
        if current is not None and (
            lifecycle.close_task is None or lifecycle.close_task.done()
        ):
            return current.config
        if lifecycle.start_task is not None and not lifecycle.start_task.done():
            task = lifecycle.start_task
        elif lifecycle.close_task is not None and not lifecycle.close_task.done():
            task = asyncio.create_task(_start_after_close(server, lifecycle.close_task))
            lifecycle.start_task = task
        else:
            task = asyncio.create_task(_start_sdk_server_impl(server))
            lifecycle.start_task = task
        lifecycle.start_waiters += 1
    cancelled = False
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        cancelled = True
        raise
    finally:
        lifecycle.start_waiters -= 1
        if cancelled and lifecycle.start_waiters == 0 and lifecycle.start_task is task:
            lifecycle.start_task = None
            lifecycle.close_task = asyncio.create_task(_close_after_start(server, task))


async def _start_after_close(
    server: SdkMcpServer,
    close_task: asyncio.Task[None],
) -> HttpMcpServerConfig:
    with suppress(BaseException):
        await close_task
    return await _start_sdk_server_impl(server)


async def _start_sdk_server_impl(server: SdkMcpServer) -> HttpMcpServerConfig:
    token = secrets.token_urlsafe(32)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    uvicorn_server: uvicorn.Server | None = None
    task: asyncio.Task[None] | None = None
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.setblocking(False)
        port = cast("tuple[str, int]", listener.getsockname())[1]
        app = _create_mcp_application(server, token)
        uvicorn_server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_level="critical",
                access_log=False,
                lifespan="on",
            )
        )
        task = asyncio.create_task(uvicorn_server.serve(sockets=[listener]))
        for _ in range(500):
            if uvicorn_server.started:
                break
            if task.done():
                await task
                raise RuntimeError("SDK MCP server stopped during startup")
            await asyncio.sleep(0.01)
        else:
            raise RuntimeError("Timed out starting SDK MCP server")
        config = HttpMcpServerConfig(
            name=server.name,
            url=f"http://127.0.0.1:{port}/mcp",
            headers=(HttpHeader("Authorization", f"Bearer {token}"),),
            oauth=False,
        )
        runtime = _ServerRuntime(config, token, uvicorn_server, task, listener)
        object.__setattr__(server, "_runtime", runtime)
        return config
    except BaseException:
        if uvicorn_server is not None:
            uvicorn_server.should_exit = True
        listener.close()
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        raise


async def close_sdk_server(server: SdkMcpServer) -> None:
    lifecycle = _server_lifecycle(server)
    async with lifecycle.lock:
        if lifecycle.start_task is not None and not lifecycle.start_task.done():
            task = asyncio.create_task(_close_after_start(server, lifecycle.start_task))
            lifecycle.start_task = None
            lifecycle.close_task = task
        elif lifecycle.close_task is not None and not lifecycle.close_task.done():
            task = lifecycle.close_task
        else:
            runtime = cast(
                "_ServerRuntime | None",
                object.__getattribute__(server, "_runtime"),
            )
            if runtime is None:
                return
            task = asyncio.create_task(_close_sdk_server_impl(server, runtime))
            lifecycle.close_task = task
    await asyncio.shield(task)


async def _close_after_start(
    server: SdkMcpServer,
    start_task: asyncio.Task[HttpMcpServerConfig],
) -> None:
    try:
        await start_task
    except BaseException:
        return
    runtime = cast(
        "_ServerRuntime | None",
        object.__getattribute__(server, "_runtime"),
    )
    if runtime is not None:
        await _close_sdk_server_impl(server, runtime)


async def _close_sdk_server_impl(
    server: SdkMcpServer,
    runtime: _ServerRuntime,
) -> None:
    runtime.server.should_exit = True
    try:
        await asyncio.wait_for(runtime.task, timeout=5)
    except asyncio.TimeoutError:
        runtime.task.cancel()
        await asyncio.gather(runtime.task, return_exceptions=True)
    finally:
        runtime.listener.close()
        if object.__getattribute__(server, "_runtime") is runtime:
            object.__setattr__(server, "_runtime", None)


__all__ = [
    "DroidTool",
    "HttpHeader",
    "HttpMcpServerConfig",
    "McpOAuthOptions",
    "McpServerConfig",
    "SdkMcpServer",
    "SseMcpServerConfig",
    "StdioMcpServerConfig",
    "ToolResponse",
    "create_sdk_mcp_server",
    "tool",
]
