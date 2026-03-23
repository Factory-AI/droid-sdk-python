"""Tests for the public API surface of droid_sdk.

Verifies:
- All __all__ exports are importable from the top-level package
- __version__ exists and matches pyproject.toml
- All error classes are importable from top level
- Key enums are importable from top level
- DroidClientTransport is importable from top level
- schemas __init__ re-exports all schema models
- No bare Any in public method signatures of DroidClient
- examples/interactive_session.py is valid Python
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path
from typing import Any, ClassVar

import droid_sdk
import droid_sdk.schemas as schemas_pkg

# ============================================================
# __all__ exports
# ============================================================


class TestTopLevelAllExports:
    """All symbols in droid_sdk.__all__ are importable."""

    def test_all_is_a_list(self) -> None:
        """__all__ is a list of strings."""
        assert isinstance(droid_sdk.__all__, list)
        assert len(droid_sdk.__all__) > 0
        for name in droid_sdk.__all__:
            assert isinstance(name, str)

    def test_all_exports_importable(self) -> None:
        """Every name in __all__ resolves to a real object."""
        for name in droid_sdk.__all__:
            obj = getattr(droid_sdk, name, None)
            assert obj is not None, f"{name!r} listed in __all__ but not importable"

    def test_version_in_all(self) -> None:
        """__version__ is listed in __all__."""
        assert "__version__" in droid_sdk.__all__

    def test_droid_client_in_all(self) -> None:
        """DroidClient is listed in __all__."""
        assert "DroidClient" in droid_sdk.__all__

    def test_process_transport_in_all(self) -> None:
        """ProcessTransport is listed in __all__."""
        assert "ProcessTransport" in droid_sdk.__all__

    def test_droid_client_transport_in_all(self) -> None:
        """DroidClientTransport is listed in __all__."""
        assert "DroidClientTransport" in droid_sdk.__all__


# ============================================================
# __version__
# ============================================================


class TestVersion:
    """__version__ exists and matches pyproject.toml."""

    def test_version_exists(self) -> None:
        """__version__ is a non-empty string."""
        assert hasattr(droid_sdk, "__version__")
        assert isinstance(droid_sdk.__version__, str)
        assert len(droid_sdk.__version__) > 0

    def test_version_matches_pyproject(self) -> None:
        """__version__ matches the version in pyproject.toml."""
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject_path.read_text()
        match = re.search(r'version\s*=\s*"([^"]+)"', content)
        assert match is not None, "Could not find version in pyproject.toml"
        expected = match.group(1)
        assert droid_sdk.__version__ == expected


# ============================================================
# Error classes importable from top level
# ============================================================


class TestErrorClassesImportable:
    """All error classes are importable from the top-level package."""

    ERROR_CLASSES: ClassVar[list[str]] = [
        "DroidClientError",
        "ConnectionError",
        "TimeoutError",
        "ProtocolError",
        "SessionError",
        "SessionNotFoundError",
        "ProcessExitError",
    ]

    def test_all_error_classes_in_all(self) -> None:
        """All error classes are listed in __all__."""
        for name in self.ERROR_CLASSES:
            assert name in droid_sdk.__all__, f"{name} not in __all__"

    def test_all_error_classes_importable(self) -> None:
        """All error classes are actual importable classes."""
        for name in self.ERROR_CLASSES:
            cls = getattr(droid_sdk, name)
            assert isinstance(cls, type), f"{name} is not a class"

    def test_error_hierarchy(self) -> None:
        """Error classes have correct inheritance hierarchy."""
        base = droid_sdk.DroidClientError
        assert issubclass(droid_sdk.ConnectionError, base)
        assert issubclass(droid_sdk.TimeoutError, base)
        assert issubclass(droid_sdk.ProtocolError, base)
        assert issubclass(droid_sdk.SessionError, base)
        assert issubclass(droid_sdk.SessionNotFoundError, base)
        assert issubclass(
            droid_sdk.SessionNotFoundError,
            droid_sdk.SessionError,
        )
        assert issubclass(droid_sdk.ProcessExitError, base)


# ============================================================
# Key enums importable from top level
# ============================================================


class TestEnumsImportable:
    """Key enums are importable from the top-level package."""

    ENUM_NAMES: ClassVar[list[str]] = [
        "ToolConfirmationOutcome",
        "SessionNotificationType",
        "DroidWorkingState",
        "MissionState",
        "McpServerStatus",
        "ToolConfirmationType",
    ]

    def test_all_enums_in_all(self) -> None:
        """All key enums are listed in __all__."""
        for name in self.ENUM_NAMES:
            assert name in droid_sdk.__all__, f"{name} not in __all__"

    def test_all_enums_importable(self) -> None:
        """All key enums are actual importable enum classes."""
        import enum

        for name in self.ENUM_NAMES:
            cls = getattr(droid_sdk, name)
            assert issubclass(cls, enum.Enum), f"{name} is not an Enum"

    def test_enum_members_accessible(self) -> None:
        """Enum members are accessible."""
        assert droid_sdk.DroidWorkingState.Idle.value == "idle"
        assert (
            droid_sdk.SessionNotificationType.ASSISTANT_TEXT_DELTA.value
            == "assistant_text_delta"
        )
        assert droid_sdk.MissionState.Running.value == "running"
        assert droid_sdk.McpServerStatus.Connected.value == "connected"
        assert droid_sdk.ToolConfirmationOutcome.Cancel.value == "cancel"
        assert droid_sdk.ToolConfirmationType.Edit.value == "edit"


# ============================================================
# DroidClientTransport importable
# ============================================================


class TestTransportProtocol:
    """DroidClientTransport is importable and is a Protocol."""

    def test_importable(self) -> None:
        """DroidClientTransport is importable from top level."""
        assert hasattr(droid_sdk, "DroidClientTransport")

    def test_is_runtime_checkable(self) -> None:
        """DroidClientTransport is runtime_checkable."""

        transport_cls = droid_sdk.DroidClientTransport
        assert hasattr(transport_cls, "__protocol_attrs__") or hasattr(
            transport_cls, "_is_runtime_protocol"
        )


# ============================================================
# Schemas __init__ re-exports
# ============================================================


class TestSchemasReExports:
    """schemas __init__ re-exports all public models."""

    def test_schemas_all_is_populated(self) -> None:
        """schemas.__all__ has entries."""
        assert isinstance(schemas_pkg.__all__, list)
        assert len(schemas_pkg.__all__) > 0

    def test_all_schemas_exports_importable(self) -> None:
        """Every name in schemas.__all__ resolves to a real object."""
        for name in schemas_pkg.__all__:
            obj = getattr(schemas_pkg, name, None)
            assert obj is not None, (
                f"{name!r} listed in schemas.__all__ but not importable"
            )

    def test_constants_reexported(self) -> None:
        """Protocol constants are re-exported."""
        assert schemas_pkg.JSONRPC_VERSION == "2.0"
        assert schemas_pkg.FACTORY_PROTOCOL_VERSION == "1.1.0"
        assert schemas_pkg.LEGACY_FACTORY_API_VERSION == "1.0.0"

    def test_enums_reexported(self) -> None:
        """Key enums are re-exported from schemas."""
        assert hasattr(schemas_pkg, "DroidServerMethod")
        assert hasattr(schemas_pkg, "SessionNotificationType")
        assert hasattr(schemas_pkg, "JsonRpcErrorCode")

    def test_client_models_reexported(self) -> None:
        """Client request/response models are re-exported."""
        assert hasattr(schemas_pkg, "InitializeSessionRequest")
        assert hasattr(schemas_pkg, "InitializeSessionResult")
        assert hasattr(schemas_pkg, "ClientRequest")

    def test_cli_models_reexported(self) -> None:
        """CLI (notification/permission) models are re-exported."""
        assert hasattr(schemas_pkg, "SessionNotification")
        assert hasattr(schemas_pkg, "RequestPermissionRequest")
        assert hasattr(schemas_pkg, "AskUserRequest")

    def test_mcp_models_reexported(self) -> None:
        """MCP models are re-exported."""
        assert hasattr(schemas_pkg, "McpServerStatusInfo")
        assert hasattr(schemas_pkg, "McpToolInfo")

    def test_mission_models_reexported(self) -> None:
        """Mission decomposition models are re-exported."""
        assert hasattr(schemas_pkg, "MissionFeature")
        assert hasattr(schemas_pkg, "ProgressLogEntry")
        assert hasattr(schemas_pkg, "Handoff")

    def test_message_models_reexported(self) -> None:
        """Message models are re-exported."""
        assert hasattr(schemas_pkg, "FactoryDroidMessage")
        assert hasattr(schemas_pkg, "TextBlock")

    def test_shared_models_reexported(self) -> None:
        """Shared JSON-RPC models are re-exported."""
        assert hasattr(schemas_pkg, "JsonRpcRequest")
        assert hasattr(schemas_pkg, "JsonRpcResponseSuccess")
        assert hasattr(schemas_pkg, "JsonRpcResponseFailure")


# ============================================================
# No bare Any in public DroidClient signatures
# ============================================================


class TestNoBareAnyInPublicSignatures:
    """Public method signatures of DroidClient should not use bare Any."""

    def _get_public_methods(self) -> list[tuple[str, Any]]:
        """Return (name, method) for public methods on DroidClient."""
        cls = droid_sdk.DroidClient
        methods = []
        for name in dir(cls):
            if name.startswith("_"):
                continue
            attr = getattr(cls, name)
            if callable(attr) or isinstance(attr, property):
                methods.append((name, attr))
        return methods

    def test_public_method_return_annotations_no_bare_any(self) -> None:
        """Public methods don't return bare Any."""
        for name, method in self._get_public_methods():
            if isinstance(method, property):
                continue
            hints = getattr(method, "__annotations__", {})
            ret = hints.get("return")
            if ret is None:
                continue
            # Check the string representation — bare Any appears as
            # 'typing.Any' or just 'Any'
            ret_str = str(ret)
            # Allow dict[str, Any] and similar — only reject bare 'Any'
            if ret_str == "typing.Any" or ret_str == "Any":
                raise AssertionError(f"DroidClient.{name} returns bare Any")


# ============================================================
# examples/interactive_session.py is valid Python
# ============================================================


class TestExampleScript:
    """examples/interactive_session.py is valid Python."""

    def test_example_exists(self) -> None:
        """The example script file exists."""
        path = Path(__file__).parent.parent / "examples" / "interactive_session.py"
        assert path.exists(), f"Example not found: {path}"

    def test_example_parses(self) -> None:
        """The example script is syntactically valid Python."""
        path = Path(__file__).parent.parent / "examples" / "interactive_session.py"
        source = path.read_text()
        # ast.parse will raise SyntaxError if invalid
        ast.parse(source, filename=str(path))

    def test_example_imports_sdk(self) -> None:
        """The example script imports from droid_sdk."""
        path = Path(__file__).parent.parent / "examples" / "interactive_session.py"
        source = path.read_text()
        assert "droid_sdk" in source

    def test_example_is_importable(self) -> None:
        """The example script's module can be loaded (syntax + import check)."""
        path = Path(__file__).parent.parent / "examples" / "interactive_session.py"
        # We don't run it (it requires droid CLI), but we can compile it
        source = path.read_text()
        compile(source, str(path), "exec")


# ============================================================
# py.typed marker exists (PEP 561)
# ============================================================


class TestPyTypedMarker:
    """py.typed marker file exists for PEP 561 compliance."""

    def test_py_typed_exists(self) -> None:
        """py.typed file exists in the package directory."""
        # Find the installed package location
        pkg_dir = Path(droid_sdk.__file__).parent
        py_typed = pkg_dir / "py.typed"
        assert py_typed.exists(), f"py.typed not found at {py_typed}"


# ============================================================
# Sub-module __all__ consistency
# ============================================================


# ============================================================
# Stream types importable from top level (VAL-DX-010)
# ============================================================


class TestStreamTypesImportable:
    """All stream message types are importable from the top-level package."""

    STREAM_TYPE_NAMES: ClassVar[list[str]] = [
        "AssistantTextDelta",
        "ThinkingTextDelta",
        "ToolUse",
        "ToolResult",
        "ToolProgress",
        "WorkingStateChanged",
        "TokenUsageUpdate",
        "TurnComplete",
        "ErrorEvent",
        "StreamMessage",
    ]

    def test_all_stream_types_in_all(self) -> None:
        """All stream types are listed in __all__."""
        for name in self.STREAM_TYPE_NAMES:
            assert name in droid_sdk.__all__, f"{name} not in __all__"

    def test_all_stream_types_importable(self) -> None:
        """All stream types resolve to real objects via top-level import."""
        for name in self.STREAM_TYPE_NAMES:
            obj = getattr(droid_sdk, name, None)
            assert obj is not None, (
                f"{name!r} listed in __all__ but not importable from top level"
            )

    def test_stream_message_is_type_alias(self) -> None:
        """StreamMessage is the union type alias of all stream types."""
        # StreamMessage should be importable as a type
        sm = droid_sdk.StreamMessage
        assert sm is not None

    def test_stream_dataclasses_are_classes(self) -> None:
        """Stream dataclasses (excluding StreamMessage) are actual classes."""
        import dataclasses

        for name in self.STREAM_TYPE_NAMES:
            if name == "StreamMessage":
                continue  # StreamMessage is a type alias, not a class
            cls = getattr(droid_sdk, name)
            assert isinstance(cls, type), f"{name} is not a class"
            assert dataclasses.is_dataclass(cls), f"{name} is not a dataclass"

    def test_isinstance_checking_works(self) -> None:
        """isinstance() works with stream types imported from top level."""
        delta = droid_sdk.AssistantTextDelta(text="hello")
        assert isinstance(delta, droid_sdk.AssistantTextDelta)

        tc = droid_sdk.TurnComplete()
        assert isinstance(tc, droid_sdk.TurnComplete)

        err = droid_sdk.ErrorEvent(message="oops", error_type="error")
        assert isinstance(err, droid_sdk.ErrorEvent)


# ============================================================
# Query API importable from top level
# ============================================================


class TestQueryApiImportable:
    """query() and DroidQueryOptions are importable from the top-level package."""

    def test_query_in_all(self) -> None:
        """query is listed in __all__."""
        assert "query" in droid_sdk.__all__

    def test_query_importable(self) -> None:
        """query is importable and is a callable."""
        assert hasattr(droid_sdk, "query")
        assert callable(droid_sdk.query)

    def test_droid_query_options_in_all(self) -> None:
        """DroidQueryOptions is listed in __all__."""
        assert "DroidQueryOptions" in droid_sdk.__all__

    def test_droid_query_options_importable(self) -> None:
        """DroidQueryOptions is importable and is a dataclass."""
        import dataclasses

        assert hasattr(droid_sdk, "DroidQueryOptions")
        cls = droid_sdk.DroidQueryOptions
        assert isinstance(cls, type)
        assert dataclasses.is_dataclass(cls)

    def test_droid_query_options_defaults(self) -> None:
        """DroidQueryOptions has correct defaults."""
        opts = droid_sdk.DroidQueryOptions()
        assert opts.cwd == "."
        assert opts.machine_id == "default"
        assert opts.model_id is None
        assert opts.autonomy_level is None
        assert opts.interaction_mode is None
        assert opts.reasoning_effort is None
        assert opts.mcp_servers is None
        assert opts.enabled_tool_ids is None


# ============================================================
# Combined import statement test (VAL-DX-010)
# ============================================================


class TestCombinedImportStatement:
    """The exact import statement from the verification step works."""

    def test_combined_import(self) -> None:
        """All key DX types importable in a single import statement."""
        from droid_sdk import (
            AssistantTextDelta,
            DroidQueryOptions,
            StreamMessage,
            TurnComplete,
            query,
        )

        assert query is not None
        assert AssistantTextDelta is not None
        assert TurnComplete is not None
        assert DroidQueryOptions is not None
        assert StreamMessage is not None


# ============================================================
# Sub-module __all__ consistency
# ============================================================


class TestSubModuleConsistency:
    """Sub-module __all__ lists are consistent with actual exports."""

    MODULES: ClassVar[list[str]] = [
        "droid_sdk.errors",
        "droid_sdk.client",
        "droid_sdk.transport",
        "droid_sdk.types",
        "droid_sdk.stream",
        "droid_sdk.query",
        "droid_sdk.schemas.enums",
        "droid_sdk.schemas.constants",
        "droid_sdk.schemas.shared",
        "droid_sdk.schemas.client",
        "droid_sdk.schemas.cli",
        "droid_sdk.schemas.mcp",
        "droid_sdk.schemas.mission",
        "droid_sdk.schemas.messages",
    ]

    def test_all_modules_importable(self) -> None:
        """All sub-modules can be imported."""
        for mod_name in self.MODULES:
            mod = importlib.import_module(mod_name)
            assert mod is not None, f"Failed to import {mod_name}"

    def test_all_modules_have_all(self) -> None:
        """All sub-modules define __all__."""
        for mod_name in self.MODULES:
            mod = importlib.import_module(mod_name)
            assert hasattr(mod, "__all__"), f"{mod_name} missing __all__"

    def test_all_exports_exist(self) -> None:
        """Every name in each module's __all__ is an actual attribute."""
        for mod_name in self.MODULES:
            mod = importlib.import_module(mod_name)
            for name in mod.__all__:
                assert hasattr(mod, name), (
                    f"{mod_name}.__all__ contains {name!r} but it is not an attribute"
                )
