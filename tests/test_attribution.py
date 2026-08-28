"""Cross-layer SDK attribution regression tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

import pytest

from droid_sdk import Runtime, Session, SessionConfig, SessionTag
from tests.helpers import (
    InMemoryTransport,
    expected_sdk_metadata,
    expected_sdk_request_attribution,
    make_success_response,
    wait_for_sent,
)

if TYPE_CHECKING:
    from droid_sdk.types import DroidClientTransport


async def _respond_to_session_lifecycle(
    transport: InMemoryTransport,
    *,
    resume: bool,
) -> None:
    await wait_for_sent(transport, 1)
    start_request = transport.get_sent_parsed(0)
    result = {
        "session": {"id": "session-1", "messages": []},
        "settings": {
            "modelId": "model",
            "reasoningEffort": "medium",
            "tags": [],
        },
    }
    if not resume:
        result["sessionId"] = "session-1"
    transport.inject_message(make_success_response(str(start_request["id"]), result))

    await wait_for_sent(transport, 2)
    close_request = transport.get_sent_parsed(1)
    transport.inject_message(make_success_response(str(close_request["id"]), {}))


@pytest.mark.asyncio
async def test_high_level_create_uses_canonical_sdk_attribution() -> None:
    transport = InMemoryTransport()
    await transport.connect()
    session = Session(
        config=SessionConfig(
            tags=(
                SessionTag(name="custom"),
                SessionTag(
                    name="sdk",
                    metadata={"language": "typescript", "version": "spoofed"},
                ),
            )
        ),
        runtime=Runtime(transport=cast("DroidClientTransport", transport)),
    )
    responder = asyncio.create_task(
        _respond_to_session_lifecycle(transport, resume=False)
    )

    await session.open()
    await session.close()
    await responder

    request = transport.get_sent_parsed(0)
    assert request["params"]["sessionOriginHint"] == "sdk"
    assert request["params"]["tags"] == [
        {"name": "custom"},
        {
            "name": "sdk",
            "metadata": expected_sdk_metadata(),
        },
    ]
    assert request["_meta"]["requestAttribution"] == expected_sdk_request_attribution()


@pytest.mark.asyncio
async def test_high_level_resume_attributes_request_without_creation_tag() -> None:
    transport = InMemoryTransport()
    await transport.connect()
    session = Session.resume(
        "session-1",
        runtime=Runtime(transport=cast("DroidClientTransport", transport)),
    )
    responder = asyncio.create_task(
        _respond_to_session_lifecycle(transport, resume=True)
    )

    await session.open()
    await session.close()
    await responder

    request = transport.get_sent_parsed(0)
    assert request["params"]["sessionOriginHint"] == "sdk"
    assert "tags" not in request["params"]
    assert request["_meta"]["requestAttribution"] == expected_sdk_request_attribution()
