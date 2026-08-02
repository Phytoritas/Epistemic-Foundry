"""Minimal valid-instance synthesizer for the canonical evolution schemas.

The canonical evolution family is deliberately simple JSON Schema — objects,
arrays, enums, two patterns and two formats, no cross-file references — so a
small deterministic synthesizer can produce one minimal valid instance per
schema.  Anything outside that contract fails loudly instead of guessing: a
synthesized instance that only probably validates would prove nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

#: The only patterns and formats the canonical evolution family uses.  A new
#: one appearing in a schema is a contract change and must fail this table.
PATTERN_VALUES: Final = {
    "^sha256:[0-9a-f]{64}$": "sha256:" + "0" * 64,
    "^[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$": "4.0.0",
}
FORMAT_VALUES: Final = {
    "date": "2026-08-01",
    "date-time": "2026-08-01T12:00:00Z",
}


class SynthesisError(Exception):
    """A schema construct this synthesizer does not model."""

    def __init__(self, message: str, path: str):
        super().__init__(f"{path}: {message}")
        self.path = path


def _string(schema: Mapping[str, Any], path: str, salt: int) -> str:
    pattern = schema.get("pattern")
    if pattern is not None:
        if pattern not in PATTERN_VALUES:
            raise SynthesisError(f"unknown pattern {pattern!r}", path)
        value = PATTERN_VALUES[pattern]
        if salt and pattern == "^sha256:[0-9a-f]{64}$":
            return "sha256:" + f"{salt:064x}"
        return value
    format_name = schema.get("format")
    if format_name is not None:
        if format_name not in FORMAT_VALUES:
            raise SynthesisError(f"unknown format {format_name!r}", path)
        return FORMAT_VALUES[format_name]
    minimum = int(schema.get("minLength", 0) or 0)
    base = f"x{salt}" if salt else "x0"
    return base + "x" * max(0, minimum - len(base))


def _typed(schema: Mapping[str, Any], kind: str, path: str, salt: int) -> Any:
    if kind == "string":
        return _string(schema, path, salt)
    if kind == "integer":
        low = int(schema.get("minimum", 0))
        maximum = schema.get("maximum")
        value = low + salt
        return min(value, int(maximum)) if maximum is not None else value
    if kind == "number":
        low = float(schema.get("minimum", 0))
        maximum = schema.get("maximum")
        value = low + float(salt)
        return min(value, float(maximum)) if maximum is not None else value
    if kind == "boolean":
        return bool(salt % 2)
    if kind == "null":
        return None
    if kind == "array":
        items = schema.get("items")
        if not isinstance(items, Mapping):
            raise SynthesisError("array without an item schema", path)
        count = int(schema.get("minItems", 0) or 0)
        if count == 0:
            return []
        values = [
            synthesize(items, f"{path}[{index}]", salt=index) for index in range(count)
        ]
        if schema.get("uniqueItems") and len({repr(value) for value in values}) != len(
            values
        ):
            raise SynthesisError("cannot salt enough distinct items", path)
        return values
    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, Mapping):
            raise SynthesisError("object without properties", path)
        # The object's own salt flows to every field, so distinctness under
        # uniqueItems comes from salted strings without pushing a numeric
        # field past its ceiling.
        instance: dict[str, Any] = {}
        for name in sorted(str(entry) for entry in required):
            if name not in properties:
                raise SynthesisError(f"required field {name} undeclared", path)
            instance[name] = synthesize(properties[name], f"{path}.{name}", salt=salt)
        return instance
    raise SynthesisError(f"unsupported type {kind!r}", path)


def synthesize(schema: Mapping[str, Any], path: str = "$", *, salt: int = 0) -> Any:
    """One minimal instance of ``schema``; deterministic for a given salt."""

    if not isinstance(schema, Mapping):
        raise SynthesisError("schema node is not an object", path)
    if (
        "$ref" in schema
        or "oneOf" in schema
        or "anyOf" in schema
        or ("allOf" in schema)
    ):
        raise SynthesisError("reference and combinator nodes are not modelled", path)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        values = schema["enum"]
        if not isinstance(values, list) or not values:
            raise SynthesisError("empty enum", path)
        return values[salt % len(values)]

    kind = schema.get("type")
    if isinstance(kind, list):
        chosen = sorted(str(entry) for entry in kind if entry != "null")
        if not chosen:
            return None
        return _typed(schema, chosen[0], path, salt)
    if isinstance(kind, str):
        return _typed(schema, kind, path, salt)
    raise SynthesisError("schema node declares no type", path)
