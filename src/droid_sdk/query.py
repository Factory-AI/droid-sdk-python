"""Top-level ``query()`` convenience function and ``DroidQueryOptions`` config.

Provides a high-level async generator that hides the full session lifecycle
(connect → initialize → message → yield → close).

Usage::

    from droid_sdk import query, DroidQueryOptions

    async for msg in query("Fix the bug in main.py", cwd="/my/project"):
        print(msg)

    # Or with an options object:
    opts = DroidQueryOptions(cwd="/my/project", model_id="claude-sonnet-4")
    async for msg in query("Fix the bug", options=opts):
        print(msg)
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator  # noqa: TC003
from dataclasses import dataclass
from typing import Any

from droid_sdk.schemas.enums import (  # noqa: TC001
    AutonomyLevel,
    DroidInteractionMode,
    ReasoningEffort,
)
from droid_sdk.stream import StreamMessage  # noqa: TC001
from droid_sdk.transport import ProcessTransport

__all__ = [
    "DroidQueryOptions",
    "query",
]


@dataclass
class DroidQueryOptions:
    """Configuration options for the :func:`query` convenience function.

    Bundles common session parameters so callers can pre-configure a
    reusable options object.  All optional fields default to ``None``
    and are omitted when passed to ``initialize_session``.

    Attributes:
        cwd: Working directory for the session. Defaults to ``"."``.
        machine_id: Machine identifier. Defaults to ``"default"``.
        model_id: Optional LLM model identifier.
        autonomy_level: Optional autonomy level for the session.
        interaction_mode: Optional interaction mode.
        reasoning_effort: Optional reasoning effort level.
        mcp_servers: Optional list of MCP server configurations.
        enabled_tool_ids: Optional list of additional tool IDs to enable.
        exec_path: Path to the ``droid`` executable. When ``None``,
            defaults to ``"droid"``.
    """

    cwd: str = "."
    machine_id: str = "default"
    model_id: str | None = None
    autonomy_level: AutonomyLevel | None = None
    interaction_mode: DroidInteractionMode | None = None
    reasoning_effort: ReasoningEffort | None = None
    mcp_servers: list[dict[str, Any]] | None = None
    enabled_tool_ids: list[str] | None = None
    exec_path: str | None = None


async def query(
    prompt: str,
    *,
    options: DroidQueryOptions | None = None,
    **kwargs: Any,
) -> AsyncIterator[StreamMessage]:
    """Top-level async generator that hides the full session lifecycle.

    Creates a :class:`~droid_sdk.transport.ProcessTransport` and
    :class:`~droid_sdk.client.DroidClient`, connects, initializes
    a session, sends the user *prompt*, and yields
    :class:`~droid_sdk.stream.StreamMessage` objects from
    :meth:`~droid_sdk.client.DroidClient.receive_response`.

    All resources are cleaned up in a ``finally`` block, even if the
    caller breaks out early or an exception occurs.

    Args:
        prompt: The user message text to send.
        options: Optional :class:`DroidQueryOptions` for session config.
        **kwargs: Convenience keyword arguments that mirror
            :class:`DroidQueryOptions` fields. When both *options* and
            a keyword argument are provided, the keyword argument wins.
            Accepted keys: ``cwd``, ``machine_id``, ``model_id``,
            ``autonomy_level``, ``interaction_mode``, ``reasoning_effort``,
            ``mcp_servers``, ``enabled_tool_ids``, ``exec_path``.

    Yields:
        :class:`~droid_sdk.stream.StreamMessage` objects (text
        deltas, tool events, state changes, token usage, errors). The
        final yielded message is always
        :class:`~droid_sdk.stream.TurnComplete`.

    Example::

        async for msg in query("Hello", cwd="/tmp"):
            if isinstance(msg, AssistantTextDelta):
                print(msg.text, end="", flush=True)
    """
    # Merge options + kwargs
    opts = options if options is not None else DroidQueryOptions()

    # Apply kwargs overrides onto a copy of the options
    merged_fields: dict[str, Any] = dataclasses.asdict(opts)
    for key, value in kwargs.items():
        if key in merged_fields:
            merged_fields[key] = value

    exec_path: str = merged_fields.get("exec_path") or "droid"
    cwd: str = merged_fields["cwd"]
    machine_id: str = merged_fields["machine_id"]

    # Import here to avoid circular import at module level
    from droid_sdk.client import DroidClient

    transport = ProcessTransport(exec_path=exec_path, cwd=cwd)
    client = DroidClient(transport=transport)

    try:
        await client.connect()

        # Build init kwargs from merged options (omit None values)
        init_kwargs: dict[str, Any] = {
            "machine_id": machine_id,
            "cwd": cwd,
        }
        if merged_fields.get("model_id") is not None:
            init_kwargs["model_id"] = merged_fields["model_id"]
        if merged_fields.get("autonomy_level") is not None:
            init_kwargs["autonomy_level"] = merged_fields["autonomy_level"]
        if merged_fields.get("interaction_mode") is not None:
            init_kwargs["interaction_mode"] = merged_fields["interaction_mode"]
        if merged_fields.get("reasoning_effort") is not None:
            init_kwargs["reasoning_effort"] = merged_fields["reasoning_effort"]
        if merged_fields.get("mcp_servers") is not None:
            init_kwargs["mcp_servers"] = merged_fields["mcp_servers"]
        if merged_fields.get("enabled_tool_ids") is not None:
            init_kwargs["enabled_tool_ids"] = merged_fields["enabled_tool_ids"]

        await client.initialize_session(**init_kwargs)
        await client.add_user_message(text=prompt)

        async for msg in client.receive_response():
            yield msg
    finally:
        await client.close()
