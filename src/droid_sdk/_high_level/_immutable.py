"""Small normalization helpers shared by the public immutable models."""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import TypeAlias, cast

JsonValue: TypeAlias = (
    bool | int | float | str | None | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]
Scalar: TypeAlias = str | int | float | bool | None
FrozenJsonValue: TypeAlias = (
    bool
    | int
    | float
    | str
    | None
    | tuple["FrozenJsonValue", ...]
    | Mapping[str, "FrozenJsonValue"]
)
FrozenJsonObject: TypeAlias = Mapping[str, FrozenJsonValue]


class RedactedStrMapping(Mapping[str, str]):
    """Immutable string mapping whose representation never exposes values."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = MappingProxyType(dict(values))

    def __getitem__(self, key: str) -> str:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        entries = ", ".join(f"{key!r}: '<redacted>'" for key in self._values)
        return f"{{{entries}}}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return False
        return self._values == other


def freeze_json(value: object, *, where: str = "value") -> FrozenJsonValue:
    """Validate a JSON value and recursively replace mutable containers."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{where} must contain only finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        source = cast("Mapping[object, object]", value)
        frozen: dict[str, FrozenJsonValue] = {}
        for key, item in source.items():
            if not isinstance(key, str):
                raise TypeError(f"{where} must have string object keys")
            frozen[key] = freeze_json(item, where=where)
        return MappingProxyType(frozen)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        source_sequence = cast("Sequence[object]", value)
        return tuple(freeze_json(item, where=where) for item in source_sequence)
    raise TypeError(f"{where} contains a non-JSON value of type {type(value).__name__}")


def freeze_json_object(
    value: Mapping[str, object], *, where: str = "value"
) -> FrozenJsonObject:
    frozen = freeze_json(value, where=where)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{where} must be a JSON object")
    return frozen


def thaw_json(value: FrozenJsonValue) -> JsonValue:
    """Return ordinary list/dict containers suitable for a JSON boundary."""
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [thaw_json(item) for item in value]
    return value


def freeze_secret_mapping(value: Mapping[str, str]) -> Mapping[str, str]:
    return RedactedStrMapping(value)


def freeze_scalar_mapping(
    value: Mapping[str, object] | None,
) -> Mapping[str, Scalar]:
    if value is None:
        return MappingProxyType({})
    result: dict[str, Scalar] = {}
    for key, item in value.items():
        if item is None or isinstance(item, (str, int, float, bool)):
            if isinstance(item, float) and not math.isfinite(item):
                continue
            result[key] = item
    return MappingProxyType(result)
