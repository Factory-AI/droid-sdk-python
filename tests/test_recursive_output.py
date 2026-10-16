import pytest
from pydantic import BaseModel, Field

from droid_sdk import JsonSchema
from droid_sdk._high_level.output import prepare_output_adapter


class Node(BaseModel):
    name: str
    children: list["Node"] = Field(default_factory=list)


def test_recursive_pydantic_object_output() -> None:
    adapter = prepare_output_adapter(Node)
    assert adapter.output_format is not None
    assert adapter.output_format.schema_ == Node.model_json_schema(mode="validation")
    result = adapter.adapt({"name": "root", "children": [{"name": "leaf"}]})
    assert result.output == Node(name="root", children=[Node(name="leaf")])
    assert result.validation_error is None


def test_referenced_object_json_schema_preserves_wire_schema() -> None:
    schema: dict[str, object] = {
        "$defs": {
            "a/b~c": {"type": "object", "properties": {"name": {"type": "string"}}}
        },
        "$ref": "#/$defs/a~1b~0c",
    }
    adapter = prepare_output_adapter(JsonSchema(schema))
    assert adapter.output_format is not None
    assert adapter.output_format.schema_ == schema
    assert adapter.adapt({"name": "root"}).output == {"name": "root"}


@pytest.mark.parametrize(
    "schema",
    [
        {"$defs": {"Node": {"type": "array"}}, "$ref": "#/$defs/Node"},
        {"$ref": "#/$defs/missing"},
        {"$defs": {"Node": {"$ref": "#/$defs/Node"}}, "$ref": "#/$defs/Node"},
        {"$ref": "https://example.invalid/schema"},
        {"$defs": {"Node": 1}, "$ref": "#/$defs/Node"},
    ],
)
def test_invalid_or_non_object_references_are_rejected(
    schema: dict[str, object],
) -> None:
    with pytest.raises(TypeError, match="top-level object"):
        prepare_output_adapter(JsonSchema(schema))
