"""Schema coverage for the extended client protocol surface."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter

import droid_sdk.schemas as schemas

_REQUEST_ENVELOPE = {
    "jsonrpc": "2.0",
    "factoryApiVersion": "1.0.0",
    "type": "request",
    "id": "req-extended",
}

_RESPONSE_ENVELOPE = {
    "jsonrpc": "2.0",
    "factoryApiVersion": "1.0.0",
    "type": "response",
    "id": "req-extended",
}

_REQUEST_CASES: list[tuple[str, dict[str, Any], str]] = [
    (
        "droid.list_models",
        {"includeDisabled": True},
        "ListModelsRequest",
    ),
    (
        "droid.list_tools",
        {"enabledToolIds": [], "disabledToolIds": ["read-cli"]},
        "ListToolsRequest",
    ),
    ("droid.list_commands", {}, "ListCommandsRequest"),
    ("droid.close_session", {"reason": "other"}, "CloseSessionRequest"),
    (
        "droid.compact_session",
        {"customInstructions": "Preserve decisions"},
        "CompactSessionRequest",
    ),
    (
        "droid.fork_session",
        {"title": "fork", "tags": [{"name": "test"}]},
        "ForkSessionRequest",
    ),
    ("droid.rename_session", {"title": "renamed"}, "RenameSessionRequest"),
    ("droid.get_context_stats", {}, "GetContextStatsRequest"),
    ("droid.get_context_breakdown", {}, "GetContextBreakdownRequest"),
    (
        "droid.get_rewind_info",
        {"sessionId": "sess-1", "messageId": "msg-1"},
        "GetRewindInfoRequest",
    ),
    (
        "droid.execute_rewind",
        {
            "sessionId": "sess-1",
            "messageId": "msg-1",
            "filesToRestore": [{"filePath": "a.py", "contentHash": "abc", "size": 10}],
            "filesToDelete": [{"filePath": "b.py"}],
            "forkTitle": "rewound",
        },
        "ExecuteRewindRequest",
    ),
]

_RESPONSE_CASES: list[tuple[str, dict[str, Any]]] = [
    (
        "ListModelsResponse",
        {
            "models": [
                {
                    "id": "model",
                    "displayName": "Model",
                    "shortDisplayName": "Model",
                    "modelProvider": "anthropic",
                    "supportedReasoningEfforts": ["off"],
                    "defaultReasoningEffort": "off",
                }
            ]
        },
    ),
    ("ListToolsResponse", {"tools": []}),
    ("ListCommandsResponse", {"commands": []}),
    ("CloseSessionResponse", {}),
    (
        "CompactSessionResponse",
        {"newSessionId": "sess-2", "removedCount": 3},
    ),
    ("ForkSessionResponse", {"newSessionId": "sess-3"}),
    ("RenameSessionResponse", {"success": True}),
    (
        "GetContextStatsResponse",
        {
            "used": 1,
            "remaining": 9,
            "limit": 10,
            "accuracy": "exact",
            "updatedAt": "2026-08-04T00:00:00Z",
        },
    ),
    (
        "GetContextBreakdownResponse",
        {
            "modelId": "model",
            "modelDisplayName": "Model",
            "contextBudget": 10,
            "usedTokens": 1,
            "freeTokens": 9,
            "categories": [],
            "skills": [],
            "mcpServers": [],
            "droids": [],
        },
    ),
    (
        "GetRewindInfoResponse",
        {"availableFiles": [], "createdFiles": [], "evictedFiles": []},
    ),
    (
        "ExecuteRewindResponse",
        {
            "newSessionId": "sess-4",
            "restoredCount": 0,
            "deletedCount": 0,
            "failedRestoreCount": 0,
            "failedDeleteCount": 0,
        },
    ),
]


@pytest.mark.parametrize(("method", "params", "expected_type"), _REQUEST_CASES)
def test_client_request_union_includes_extended_methods(
    method: str,
    params: dict[str, Any],
    expected_type: str,
) -> None:
    request = schemas.ClientRequest.model_validate(
        {**_REQUEST_ENVELOPE, "method": method, "params": params}
    )

    assert type(request.root).__name__ == expected_type


@pytest.mark.parametrize(("response_name", "result"), _RESPONSE_CASES)
def test_extended_response_types_parse_success(
    response_name: str,
    result: dict[str, Any],
) -> None:
    response_type = getattr(schemas, response_name)
    response = TypeAdapter(response_type).validate_python(
        {**_RESPONSE_ENVELOPE, "result": result}
    )

    assert response.result is not None
