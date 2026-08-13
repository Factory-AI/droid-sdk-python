"""Regression tests for the canonical v5 compliance gaps."""

from __future__ import annotations

import sys

import pytest
from pydantic import ValidationError

import droid_sdk.errors as errors
from droid_sdk.errors import DroidProcessError
from droid_sdk.low_level import (
    ClientRequest,
    ContextStatsAccuracy,
    DroidServerMethod,
    LastCallTokenUsage,
    LlmRetryNotification,
    LlmRetryReason,
    LoadSessionResult,
    McpOAuthOptions,
    McpOAuthTokenEndpointAuthMethod,
    PendingAskUserRequest,
    PendingPermissionRequest,
    ProcessTransport,
    ProtocolEngine,
    QueuedUserMessage,
    RequestPermissionResult,
    SessionData,
    SessionPlatform,
    SessionSource,
    SetSkillDisabledRequest,
    SubmitMcpAuthErrorRequest,
    ToolConfirmationOutcome,
    ToolResultBlock,
)


def test_legacy_exception_aliases_are_not_star_exports() -> None:
    legacy_names = {
        "ConnectionError",
        "DroidClientError",
        "ProcessExitError",
        "ProtocolError",
        "TimeoutError",
    }
    assert legacy_names.isdisjoint(errors.__all__)
    assert hasattr(errors, "ProcessExitError")


@pytest.mark.parametrize(
    ("model", "method", "params"),
    [
        (
            SetSkillDisabledRequest,
            DroidServerMethod.SET_SKILL_DISABLED,
            {
                "skillName": "skill",
                "disabled": True,
                "settingsLevel": "project",
            },
        ),
        (
            SubmitMcpAuthErrorRequest,
            DroidServerMethod.SUBMIT_MCP_AUTH_ERROR,
            {
                "serverName": "server",
                "error": "access_denied",
                "errorDescription": "Denied",
                "state": "state",
            },
        ),
    ],
)
def test_new_rpc_requests_are_in_client_union(
    model: type[object],
    method: DroidServerMethod,
    params: dict[str, object],
) -> None:
    raw = {
        "jsonrpc": "2.0",
        "factoryApiVersion": "1.0.0",
        "factoryProtocolVersion": "1.1.0",
        "type": "request",
        "id": "request-1",
        "method": method.value,
        "params": params,
    }
    parsed = ClientRequest.model_validate(raw)
    assert isinstance(parsed.root, model)


@pytest.mark.parametrize(
    "source",
    [
        {"platform": "slack", "delegationSessionId": "d"},
        {"platform": "web", "delegationSessionId": "d"},
        {"platform": "api", "delegationSessionId": "d"},
        {"platform": "sessions_api", "delegationSessionId": "d"},
        {
            "platform": "linear",
            "delegationSessionId": "d",
            "agentSessionId": "a",
        },
        {
            "platform": "jira",
            "delegationSessionId": "d",
            "cloudId": "c",
            "issueId": "i",
        },
        {
            "platform": "microsoft-teams",
            "delegationSessionId": "d",
            "tenantId": "t",
            "conversationId": "c",
            "serviceUrl": "https://teams.example",
        },
        {
            "platform": "readiness-remediation",
            "reportId": "r",
            "repoUrl": "https://example/repo",
            "criterionId": "c",
        },
        {
            "platform": "readiness-evaluation",
            "repoUrl": "https://example/repo",
        },
        {"platform": "automation", "automationId": "a", "computerId": "c"},
        {"platform": "wiki-generation", "repoUrl": "https://example/repo"},
        {"platform": "wiki-ci-setup", "repoUrl": "https://example/repo"},
        {"platform": "tui"},
        {"platform": "desktop"},
        {"platform": "acp"},
        {"platform": "unknown"},
    ],
)
def test_session_source_variants(source: dict[str, str]) -> None:
    parsed = SessionSource.model_validate(source)
    assert isinstance(parsed.platform, SessionPlatform)


def test_session_source_requires_platform_specific_fields() -> None:
    with pytest.raises(ValidationError):
        SessionSource.model_validate({"platform": "web"})
    with pytest.raises(ValidationError):
        SessionSource.model_validate({"platform": "linear", "delegationSessionId": "d"})
    with pytest.raises(ValidationError):
        SessionSource.model_validate({"platform": "unrecognized"})


def test_tool_result_content_is_a_typed_union() -> None:
    result = ToolResultBlock.model_validate(
        {
            "type": "tool_result",
            "toolUseId": "tool-1",
            "content": [
                {"type": "text", "text": "done"},
                {
                    "type": "document",
                    "source": {
                        "type": "text",
                        "mediaType": "text/plain",
                        "data": "contents",
                    },
                },
            ],
        }
    )
    assert isinstance(result.content, list)
    with pytest.raises(ValidationError):
        ToolResultBlock.model_validate(
            {
                "type": "tool_result",
                "toolUseId": "tool-1",
                "content": [{"type": "thinking", "thinking": "not supported"}],
            }
        )


def test_load_result_uses_typed_snapshots_and_last_call_usage() -> None:
    result = LoadSessionResult.model_validate(
        {
            "session": {
                "messages": [
                    {
                        "id": "message-1",
                        "role": "user",
                        "content": [{"type": "text", "text": "hello"}],
                        "createdAt": 1,
                        "updatedAt": 1,
                    }
                ]
            },
            "settings": {"modelId": "model", "reasoningEffort": "medium"},
            "pendingPermissions": [
                {"requestId": "permission-1", "toolUses": [], "options": []}
            ],
            "pendingAskUserRequests": [
                {
                    "requestId": "question-1",
                    "toolCallId": "tool-1",
                    "questions": [],
                }
            ],
            "queuedMessages": [{"requestId": "message-1", "text": "queued"}],
            "lastCallTokenUsage": {"inputTokens": 12, "cacheReadTokens": 3},
        }
    )
    assert isinstance(result.session, SessionData)
    assert isinstance(result.pending_permissions[0], PendingPermissionRequest)
    assert isinstance(result.pending_ask_user_requests[0], PendingAskUserRequest)
    assert isinstance(result.queued_messages[0], QueuedUserMessage)
    assert isinstance(result.last_call_token_usage, LastCallTokenUsage)
    assert result.last_call_token_usage.output_tokens is None


def test_canonical_retry_and_context_enums() -> None:
    retry = LlmRetryNotification.model_validate(
        {"type": "llm_retry", "attempt": 2, "reason": "rate_limited"}
    )
    assert retry.reason is LlmRetryReason.RateLimited
    assert ContextStatsAccuracy.Exact.value == "exact"


@pytest.mark.parametrize(
    "oauth",
    [
        {"scopes": [" "]},
        {"resource": "not-a-url"},
        {"authorizationServerIssuer": "not-a-url"},
        {"clientId": " "},
        {"clientSecret": " "},
        {"callbackPort": 0},
        {"callbackPort": 65536},
        {
            "clientMetadataUrl": "https://client.example/oauth/%2e%2e/metadata.json",
        },
        {
            "clientMetadataUrl": "https://client.example/oauth/metadata.json",
            "clientId": "client",
            "authorizationServerIssuer": "https://issuer.example",
        },
        {
            "clientMetadataUrl": "https://client.example/oauth/metadata.json",
            "tokenEndpointAuthMethod": "client_secret_post",
        },
        {"clientId": "client"},
    ],
)
def test_oauth_validation_rejects_invalid_combinations(
    oauth: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        McpOAuthOptions.model_validate(oauth)


def test_oauth_validation_accepts_typed_public_client() -> None:
    oauth = McpOAuthOptions.model_validate(
        {
            "scopes": [" read "],
            "clientMetadataUrl": "https://client.example/oauth/metadata.json",
            "tokenEndpointAuthMethod": "none",
        }
    )
    assert oauth.scopes == ["read"]
    assert oauth.token_endpoint_auth_method is McpOAuthTokenEndpointAuthMethod.None_


def test_permission_edit_requires_edited_content() -> None:
    with pytest.raises(ValidationError):
        RequestPermissionResult.model_validate(
            {"selectedOption": ToolConfirmationOutcome.ProceedEdit.value}
        )
    result = RequestPermissionResult.model_validate(
        {
            "selectedOption": ToolConfirmationOutcome.ProceedEdit.value,
            "editedSpecContent": "edited",
        }
    )
    assert result.edited_spec_content == "edited"


@pytest.mark.asyncio
async def test_normal_process_exit_rejects_pending_and_future_requests() -> None:
    transport = ProcessTransport(
        exec_path=sys.executable,
        exec_args=["-c", "import time; time.sleep(0.2)"],
    )
    await transport.connect()
    protocol = ProtocolEngine(transport=transport)
    await protocol.start()
    try:
        with pytest.raises(DroidProcessError) as first:
            await protocol.send_request(
                method="droid.never_responds",
                params={},
                timeout=2,
            )
        assert first.value.exit_code == 0
        with pytest.raises(DroidProcessError) as second:
            await protocol.send_request(method="droid.future", params={})
        assert second.value is first.value
    finally:
        await protocol.close()
        await transport.close()
