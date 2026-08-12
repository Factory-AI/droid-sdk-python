"""Immutable custom-runtime configuration."""

# ruff: noqa: TC001, TC003

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from droid_sdk._high_level._immutable import freeze_secret_mapping
from droid_sdk.observability import Observability
from droid_sdk.types import DroidClientTransport

Transport = DroidClientTransport


def _empty_str_mapping() -> Mapping[str, str]:
    return {}


@dataclass(frozen=True, slots=True)
class Runtime:
    executable: str | Path | None = None
    args: Sequence[str] = ()
    env: Mapping[str, str] = field(default_factory=_empty_str_mapping)
    transport: Transport | None = None
    observability: Observability | None = None

    def __post_init__(self) -> None:
        if self.executable is not None:
            object.__setattr__(self, "executable", Path(self.executable))
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "env", freeze_secret_mapping(self.env))

    @property
    def uses_supplied_transport(self) -> bool:
        """Whether transport takes precedence over process configuration."""
        return self.transport is not None
