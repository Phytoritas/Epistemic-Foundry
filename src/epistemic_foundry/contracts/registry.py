"""Load and cache the canonical JSON Schemas.

The bundle ships 124 Draft 2020-12 schemas that cross-reference each other by
`$id`. They are registered into one `referencing` registry so a `$ref` resolves
locally: reaching out to `https://epistemic-foundry.local/...` at validation
time would make the runtime depend on the network for a contract check.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_SUFFIX = ".schema.json"


class SchemaNotFound(LookupError):
    """Raised when a requested canonical schema does not exist."""


def repo_root() -> Path:
    """Repository root, derived from this file's location.

    `src/epistemic_foundry/contracts/registry.py` -> three parents up is
    `src/`, four is the root. Deriving it beats an env var: an installed copy
    and a source checkout both resolve without configuration.
    """
    return Path(__file__).resolve().parents[3]


class SchemaRegistry:
    """Canonical schemas plus compiled validators, keyed by schema name."""

    def __init__(self, schema_dir: Path) -> None:
        if not schema_dir.is_dir():
            raise SchemaNotFound(f"schema directory not found: {schema_dir}")
        self._schema_dir = schema_dir
        self._documents: dict[str, dict[str, Any]] = {}
        self._registry: Registry | None = None
        self._validators: dict[str, Draft202012Validator] = {}

    @property
    def schema_dir(self) -> Path:
        return self._schema_dir

    def names(self) -> list[str]:
        """Sorted canonical schema names (file stem without `.schema`)."""
        return sorted(path.name[: -len(SCHEMA_SUFFIX)] for path in self._iter_files())

    def _iter_files(self) -> Iterator[Path]:
        yield from self._schema_dir.glob(f"*{SCHEMA_SUFFIX}")

    def document(self, name: str) -> dict[str, Any]:
        """Return the raw schema document for `name`."""
        if name in self._documents:
            return self._documents[name]
        path = self._schema_dir / f"{name}{SCHEMA_SUFFIX}"
        if not path.is_file():
            raise SchemaNotFound(f"no canonical schema named {name!r} in {self._schema_dir}")
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise SchemaNotFound(f"schema {name!r} is not a JSON object")
        self._documents[name] = document
        return document

    def registry(self) -> Registry:
        """Registry holding every canonical schema, for local `$ref` resolution."""
        if self._registry is not None:
            return self._registry
        resources = []
        for path in self._iter_files():
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                continue
            # `$schema` is present in every canonical file, but pass the draft
            # explicitly so a schema missing it still registers as 2020-12
            # instead of raising "unknown specification".
            resource = Resource.from_contents(document, default_specification=DRAFT202012)
            identifier = document.get("$id") or path.name
            resources.append((str(identifier), resource))
            # Also expose the bare filename so a relative `$ref` resolves.
            resources.append((path.name, resource))
        self._registry = Registry().with_resources(resources)
        return self._registry

    def validator(self, name: str) -> Draft202012Validator:
        """Compiled validator for `name`; compiled once and reused."""
        if name not in self._validators:
            self._validators[name] = Draft202012Validator(
                self.document(name), registry=self.registry()
            )
        return self._validators[name]


@lru_cache(maxsize=1)
def default_registry() -> SchemaRegistry:
    """Registry rooted at the repository's `schemas/` directory."""
    return SchemaRegistry(repo_root() / "schemas")
