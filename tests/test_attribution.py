"""Cross-layer SDK attribution regression tests."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, cast

import pytest

from droid_sdk import Runtime, Session, SessionConfig, SessionTag
from droid_sdk._attribution import SDK_CLIENT_METADATA, SDK_REQUEST_ATTRIBUTION
from tests.helpers import InMemoryTransport, make_success_response

if TYPE_CHECKING:
    from droid_sdk.types import DroidClientTransport


async def _wait_for_sent(
    transport: InMemoryTransport,
    count: int,
) -> dict[str, object]:
    for _ in range(2_000):
        if len(transport.sent_messages) >= count:
            return json.loads(transport.sent_messages[count - 1])  # type: ignore[no-any-return]
        await asyncio.sleep(0)
    raise AssertionError(f"Timed out waiting for request {count}")


async def _respond_to_session_lifecycle(
    transport: InMemoryTransport,
    *,
    resume: bool,
) -> None:
    start_request = await _wait_for_sent(transport, 1)
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

    close_request = await _wait_for_sent(transport, 2)
    transport.inject_message(make_success_response(str(close_request["id"]), {}))


def _expected_request_attribution() -> dict[str, object]:
    return SDK_REQUEST_ATTRIBUTION.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )


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

    request = json.loads(transport.sent_messages[0])
    assert request["params"]["sessionOriginHint"] == "sdk"
    assert request["params"]["tags"] == [
        {"name": "custom"},
        {
            "name": "sdk",
            "metadata": SDK_CLIENT_METADATA.model_dump(mode="json"),
        },
    ]
    assert request["_meta"]["requestAttribution"] == (_expected_request_attribution())


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

    request = json.loads(transport.sent_messages[0])
    assert request["params"]["sessionOriginHint"] == "sdk"
    assert "tags" not in request["params"]
    assert request["_meta"]["requestAttribution"] == (_expected_request_attribution())
