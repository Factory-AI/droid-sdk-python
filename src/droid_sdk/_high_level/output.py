"""Structured-output preparation and local adaptation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar, cast, overload

from pydantic import BaseModel, ValidationError

from droid_sdk._high_level._immutable import (
    FrozenJsonObject,
    JsonObject,
    freeze_json_object,
    thaw_json,
)
from droid_sdk._high_level.config import JsonSchema
from droid_sdk.schemas.client import OutputFormat

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class OutputAdaptation(Generic[T_co]):
    output: T_co | None
    structured_output: FrozenJsonObject | None
    validation_error: ValidationError | None


class OutputAdapter(Generic[T_co]):
    """Prepared wire schema plus a local output validator."""

    __slots__ = ("_model", "output_format")

    def __init__(
        self,
        output_format: OutputFormat | None,
        model: type[BaseModel] | None = None,
    ) -> None:
        self.output_format = output_format
        self._model = model

    def adapt(self, raw: object | None) -> OutputAdaptation[T_co]:
        if self.output_format is None:
            return OutputAdaptation(None, None, None)

        if self._model is not None:
            structured_output = _raw_object(raw)
            validation_input = (
                thaw_json(structured_output)
                if structured_output is not None
                else raw
            )
            try:
                value = self._model.model_validate(validation_input)
            except ValidationError as exc:
                return OutputAdaptation(None, structured_output, exc)
            return OutputAdaptation(cast("T_co", value), structured_output, None)

        raw_value = _validate_json_object(raw)
        return OutputAdaptation(
            cast("T_co", thaw_json(raw_value)),
            raw_value,
            None,
        )


@overload
def prepare_output_adapter(output: None = None) -> OutputAdapter[None]: ...


@overload
def prepare_output_adapter(output: type[ModelT]) -> OutputAdapter[ModelT]: ...


@overload
def prepare_output_adapter(output: JsonSchema) -> OutputAdapter[JsonObject]: ...


def prepare_output_adapter(
    output: object = None,
) -> OutputAdapter[object]:
    if output is None:
        return OutputAdapter(None)
    if isinstance(output, JsonSchema):
        _ensure_object_schema(output.schema)
        schema: JsonObject = {
            key: thaw_json(value) for key, value in output.schema.items()
        }
        return OutputAdapter(
            OutputFormat.model_validate({"type": "json_schema", "schema": schema})
        )
    if isinstance(output, type) and issubclass(output, BaseModel):
        schema = output.model_json_schema(mode="validation")
        _ensure_object_schema(schema)
        return OutputAdapter(
            OutputFormat.model_validate({"type": "json_schema", "schema": schema}),
            output,
        )
    raise TypeError("output must be None, JsonSchema, or a Pydantic BaseModel class")


def _ensure_object_schema(schema: Mapping[str, object]) -> None:
    if schema.get("type") != "object":
        raise TypeError("structured output schema must describe a top-level object")


def _raw_object(raw: object | None) -> FrozenJsonObject | None:
    try:
        return _validate_json_object(raw)
    except (TypeError, ValueError):
        return None


def _validate_json_object(raw: object | None) -> FrozenJsonObject:
    if not isinstance(raw, Mapping):
        raise TypeError("structured output must be a JSON object")
    return freeze_json_object(
        cast("Mapping[str, object]", raw), where="structured output"
    )
