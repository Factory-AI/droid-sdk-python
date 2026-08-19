"""Canonical model-discovery protocol and high-level API tests."""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest
from pydantic import ValidationError

import droid_sdk._high_level.models as models_module
from droid_sdk import (
    ModelInfo,
    ModelProvider,
    ReasoningEffort,
    Runtime,
    list_models,
)
from droid_sdk.client import DroidClient
from droid_sdk.errors import DroidConnectionError, InvalidWorkingDirectoryError
from droid_sdk.low_level import (
    ClientRequest,
    DroidServerMethod,
    ListModelsRequest,
)
from droid_sdk.schemas.models import (
    ListModelsResult,
)
from droid_sdk.schemas.models import (
    ModelInfo as WireModelInfo,
)
from tests.helpers import InMemoryTransport, make_success_response

if TYPE_CHECKING:
    from pathlib import Path

    from droid_sdk.types import DroidClientTransport


def model_payload(**overrides: object) -> dict[str, object]:
    return {
        "id": "model-1",
        "displayName": "Model 1",
        "shortDisplayName": "M1",
        "modelProvider": "anthropic",
        "supportedReasoningEfforts": ["off", "medium"],
        "defaultReasoningEffort": "medium",
        "isCustom": False,
        **overrides,
    }


def test_model_info_wire_schema_enforces_disabled_reason() -> None:
    enabled = WireModelInfo.model_validate(
        model_payload(disabled=False, futureField="preserved")
    )
    assert enabled.disabled is False
    assert enabled.model_extra == {"futureField": "preserved"}

    disabled = WireModelInfo.model_validate(
        model_payload(disabled=True, disabledReason="Disabled by admin")
    )
    assert disabled.disabled_reason == "Disabled by admin"

    with pytest.raises(ValidationError, match="disabledReason"):
        WireModelInfo.model_validate(model_payload(disabled=True))
    with pytest.raises(ValidationError, match="must not include"):
        WireModelInfo.model_validate(
            model_payload(disabled=False, disabledReason="unexpected")
        )


def test_list_models_request_is_in_client_union() -> None:
    request = ClientRequest.model_validate(
        {
            "jsonrpc": "2.0",
            "factoryApiVersion": "1.0.0",
            "factoryProtocolVersion": "1.1.0",
            "type": "request",
            "id": "models-1",
            "method": "droid.list_models",
            "params": {"includeDisabled": True},
        }
    )
    assert isinstance(request.root, ListModelsRequest)
    assert request.root.params.include_disabled is True


@pytest.mark.parametrize(
    ("include_disabled", "expected_params"),
    [(None, {}), (True, {"includeDisabled": True})],
)
@pytest.mark.asyncio
async def test_low_level_list_models_is_sessionless(
    include_disabled: bool | None,
    expected_params: dict[str, object],
) -> None:
    transport = InMemoryTransport()
    client = DroidClient(transport=transport)
    await client.connect()

    task = asyncio.create_task(client.list_models(include_disabled=include_disabled))
    await asyncio.sleep(0)
    request = transport.get_last_sent_parsed()
    assert request["method"] == DroidServerMethod.LIST_MODELS.value
    assert request["params"] == expected_params
    assert client.session_id is None

    transport.inject_message(
        make_success_response(request["id"], {"models": [model_payload()]})
    )
    result = await task
    assert result.models[0].id == "model-1"
    await client.close()


@pytest.mark.asyncio
async def test_high_level_list_models_returns_immutable_models(
    tmp_path: Path,
) -> None:
    transport = InMemoryTransport()
    await transport.connect()

    task = asyncio.create_task(
        list_models(
            include_disabled=True,
            cwd=tmp_path,
            runtime=Runtime(transport=cast("DroidClientTransport", transport)),
        )
    )
    await asyncio.sleep(0)
    request = transport.get_last_sent_parsed()
    assert request["params"] == {"includeDisabled": True}
    transport.inject_message(
        make_success_response(
            request["id"],
            {
                "models": [
                    model_payload(
                        supportsImageGeneration=True,
                        tier="premium",
                        kind="chat",
                        variantBadge="Fast",
                    )
                ]
            },
        )
    )

    models = await task
    assert models == [
        ModelInfo(
            id="model-1",
            display_name="Model 1",
            short_display_name="M1",
            model_provider=ModelProvider.ANTHROPIC,
            supported_reasoning_efforts=(
                ReasoningEffort.OFF,
                ReasoningEffort.MEDIUM,
            ),
            default_reasoning_effort=ReasoningEffort.MEDIUM,
            supports_image_generation=True,
            tier="premium",
            kind="chat",
            variant_badge="Fast",
        )
    ]
    assert isinstance(models[0].supported_reasoning_efforts, tuple)
    with pytest.raises(FrozenInstanceError):
        models[0].display_name = "changed"  # type: ignore[misc]
    assert transport.is_connected is False


@pytest.mark.asyncio
async def test_high_level_list_models_closes_transport_when_cancelled(
    tmp_path: Path,
) -> None:
    transport = InMemoryTransport()
    await transport.connect()
    task = asyncio.create_task(
        list_models(
            cwd=tmp_path,
            runtime=Runtime(transport=cast("DroidClientTransport", transport)),
        )
    )
    await asyncio.sleep(0)
    assert transport.sent_messages

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.is_connected is False


class FakeProcessTransport:
    instances: ClassVar[list[FakeProcessTransport]] = []

    def __init__(self, **options: Any) -> None:
        self.options = options
        self.is_connected = False
        self.__class__.instances.append(self)


class FakeClient:
    instances: ClassVar[list[FakeClient]] = []

    def __init__(self, *, transport: object, **_options: object) -> None:
        self.transport = transport
        self.closed = False
        self.__class__.instances.append(self)

    async def connect(self) -> None:
        pass

    async def list_models(
        self, *, include_disabled: bool | None = None
    ) -> ListModelsResult:
        assert include_disabled is None
        return ListModelsResult(models=[WireModelInfo.model_validate(model_payload())])

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_list_models_maps_process_options_and_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeProcessTransport.instances.clear()
    FakeClient.instances.clear()
    monkeypatch.setattr(models_module, "ProcessTransport", FakeProcessTransport)
    monkeypatch.setattr(models_module, "DroidClient", FakeClient)

    runtime = Runtime(
        executable="/opt/factory/droid",
        args=("--example",),
        env={"EXISTING": "value", "FACTORY_API_KEY": "old"},
    )
    await list_models(cwd=tmp_path, runtime=runtime, api_key="new")

    options = FakeProcessTransport.instances[0].options
    assert options == {
        "exec_path": "/opt/factory/droid",
        "exec_args": [
            "exec",
            "--input-format",
            "stream-jsonrpc",
            "--output-format",
            "stream-jsonrpc",
            "--example",
        ],
        "cwd": str(tmp_path.resolve()),
        "env": {"EXISTING": "value", "FACTORY_API_KEY": "new"},
    }
    assert FakeClient.instances[0].closed is True


class FailingClient(FakeClient):
    async def list_models(
        self, *, include_disabled: bool | None = None
    ) -> ListModelsResult:
        raise RuntimeError("catalog failed")


@pytest.mark.asyncio
async def test_list_models_closes_client_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FailingClient.instances.clear()
    monkeypatch.setattr(models_module, "ProcessTransport", FakeProcessTransport)
    monkeypatch.setattr(models_module, "DroidClient", FailingClient)

    with pytest.raises(RuntimeError, match="catalog failed"):
        await list_models(cwd=tmp_path)

    assert FailingClient.instances[0].closed is True


class MissingExecutableClient(FakeClient):
    async def connect(self) -> None:
        raise FileNotFoundError


@pytest.mark.asyncio
async def test_list_models_maps_missing_executable_and_invalid_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    MissingExecutableClient.instances.clear()
    monkeypatch.setattr(models_module, "ProcessTransport", FakeProcessTransport)
    monkeypatch.setattr(models_module, "DroidClient", MissingExecutableClient)

    with pytest.raises(DroidConnectionError, match="Droid executable was not found"):
        await list_models(cwd=tmp_path)
    assert MissingExecutableClient.instances[0].closed is True

    with pytest.raises(InvalidWorkingDirectoryError, match="Invalid working directory"):
        await list_models(cwd=tmp_path / "missing")
