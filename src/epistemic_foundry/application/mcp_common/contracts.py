"""Shared T01 MCP contract kernel: catalog, envelopes, authorization, ports.

The canonical wire literals live in ``contracts/mcp/t01/tool-catalog.yaml``
(HD-EF4-T01-SG001-20260730-001).  This module loads and verifies that catalog,
enforces the frozen authorization order, and produces the exact shared result
and error envelopes used by every transport.  Scientific payloads validate
against canonical domain schemas through the packaged contract registry;
nothing here re-declares a domain shape (EF4-I22).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml
from jsonschema import Draft202012Validator

from ...contracts import default_registry
from ...contracts.registry import SchemaRegistry

PROTOCOL_VERSION = "2026-07-28"
CATALOG_RELATIVE_PATH = "contracts/mcp/t01/tool-catalog.yaml"
RESULT_SCHEMA_RELATIVE_PATH = "contracts/mcp/t01/foundry-mcp-tool-result.schema.json"
ERROR_SCHEMA_RELATIVE_PATH = "contracts/mcp/t01/foundry-mcp-tool-error.schema.json"

SIDE_EFFECT_CLASSES = ("PURE_READ", "DURABLE_PLAN_ARTIFACT")
READ_MODEL_STATES = ("READY", "EMPTY_CONFIRMED", "DEGRADED", "UNAVAILABLE")
AUTHORIZATION_ORDER = (
    "PROTOCOL_VALIDATION",
    "INPUT_SCHEMA_VALIDATION",
    "AUTHENTICATION",
    "WORKSPACE_ISOLATION",
    "CAPABILITY_AUTHORIZATION",
    "CONFIDENTIALITY_CONCEALMENT",
    "HANDLER_EXECUTION",
)
ERROR_CODES = (
    "INVALID_REQUEST",
    "UNKNOWN_TOOL",
    "INVALID_INPUT",
    "UNAUTHENTICATED",
    "WORKSPACE_DENIED",
    "UNAUTHORIZED",
    "NOT_FOUND",
    "IDEMPOTENCY_CONFLICT",
    "PLAN_COMPILATION_REJECTED",
    "INTERNAL",
)
_RETRYABLE_CODES = frozenset({"INTERNAL"})
EXPECTED_READ_TOOL_COUNT = 9
EXPECTED_PLANNING_TOOL_COUNT = 4
_CANONICAL_SCHEMA_ID_PREFIX = "https://epistemic-foundry.local/schemas/"
_CANONICAL_SCHEMA_ID_SUFFIX = ".schema.json"

_TOOL_FIELDS = frozenset(
    {
        "name",
        "title",
        "side_effect_class",
        "handler_operation",
        "input_schema",
        "data_schema_refs",
        "capability",
        "confidentiality_concealment",
    }
)
_CATALOG_FIELDS = frozenset(
    {
        "catalog_id",
        "catalog_version",
        "protocol_version",
        "transports",
        "stateless",
        "result_envelope_schema",
        "error_envelope_schema",
        "read_tool_count",
        "planning_tool_count",
        "authorization_order",
        "tools",
    }
)


class McpContractError(ValueError):
    """Typed fail-closed T01 contract error mapped onto the error envelope."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if error_code not in ERROR_CODES:
            raise AssertionError(f"unknown MCP error code: {error_code}")
        super().__init__(message)
        self.error_code = error_code
        self.retryable = error_code in _RETRYABLE_CODES
        self.details = dict(details) if details is not None else None


class CatalogIntegrityError(RuntimeError):
    """The canonical tool catalog or its schemas are structurally invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_id(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def canonical_schema_name(schema_ref: str) -> str:
    """Map a canonical schema ``$id`` to its packaged registry name."""

    if not (
        schema_ref.startswith(_CANONICAL_SCHEMA_ID_PREFIX)
        and schema_ref.endswith(_CANONICAL_SCHEMA_ID_SUFFIX)
    ):
        raise CatalogIntegrityError(f"non-canonical data schema ref: {schema_ref}")
    return schema_ref[
        len(_CANONICAL_SCHEMA_ID_PREFIX) : -len(_CANONICAL_SCHEMA_ID_SUFFIX)
    ]


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Transport-derived caller identity; never part of tool arguments."""

    principal_id: str | None
    workspace_id: str | None
    capabilities: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    title: str
    side_effect_class: str
    handler_operation: str
    input_schema_path: str
    data_schema_refs: tuple[str, ...]
    capability: str
    confidentiality_concealment: bool


@dataclass(frozen=True, slots=True)
class ReadOutcome:
    """Read-model provider answer for one PURE_READ invocation."""

    found: bool
    state: str
    data: Mapping[str, Any] | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class StoredPlanArtifact:
    artifact_id: str
    receipt_id: str
    sha256: str
    created: bool


class ReadModelPort(Protocol):
    """Read-only projection provider.  Implementations must not mutate state."""

    def fetch(
        self, operation: str, workspace_id: str, arguments: Mapping[str, Any]
    ) -> ReadOutcome: ...


class PlanCompilerPort(Protocol):
    """Domain-owned plan compiler; T01 never re-implements domain logic."""

    def compile(
        self, operation: str, workspace_id: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class PlanRejected(Exception):
    """Raised by a plan compiler when the domain rejects the proposal."""

    def __init__(self, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details) if details is not None else None


class IdempotencyConflict(Exception):
    """Raised by the artifact store on key reuse with a different request."""


class PlanArtifactStorePort(Protocol):
    """Append-only durable store binding plan artifacts to receipts."""

    def put(
        self,
        *,
        workspace_id: str,
        kind: str,
        content: bytes,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> StoredPlanArtifact: ...


class ToolCatalog:
    """Verified, immutable projection of the canonical tool catalog."""

    def __init__(
        self,
        *,
        document: Mapping[str, Any],
        input_schemas: Mapping[str, Mapping[str, Any]],
        result_schema: Mapping[str, Any],
        error_schema: Mapping[str, Any],
    ) -> None:
        self._document = document
        self._tools = self._verify(document, input_schemas)
        self._input_validators = {
            name: Draft202012Validator(dict(input_schemas[spec.input_schema_path]))
            for name, spec in self._tools.items()
        }
        Draft202012Validator.check_schema(dict(result_schema))
        Draft202012Validator.check_schema(dict(error_schema))
        self._result_validator = Draft202012Validator(dict(result_schema))
        self._error_validator = Draft202012Validator(dict(error_schema))
        self._input_schemas = {
            name: dict(input_schemas[spec.input_schema_path])
            for name, spec in self._tools.items()
        }

    @staticmethod
    def _verify(
        document: Mapping[str, Any],
        input_schemas: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, ToolSpec]:
        missing = sorted(_CATALOG_FIELDS - set(document))
        unknown = sorted(set(document) - _CATALOG_FIELDS)
        if missing or unknown:
            raise CatalogIntegrityError(
                f"catalog field set invalid: missing={missing} unknown={unknown}"
            )
        if document["protocol_version"] != PROTOCOL_VERSION:
            raise CatalogIntegrityError("catalog protocol version drifted")
        if list(document["authorization_order"]) != list(AUTHORIZATION_ORDER):
            raise CatalogIntegrityError("catalog authorization order drifted")
        if document["stateless"] is not True:
            raise CatalogIntegrityError("catalog transports must be stateless")
        rows = document["tools"]
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise CatalogIntegrityError("catalog tools must be an array")
        tools: dict[str, ToolSpec] = {}
        read_count = 0
        planning_count = 0
        for row in rows:
            if not isinstance(row, Mapping):
                raise CatalogIntegrityError("catalog tool row must be an object")
            row_missing = sorted(_TOOL_FIELDS - set(row))
            row_unknown = sorted(set(row) - _TOOL_FIELDS)
            if row_missing or row_unknown:
                raise CatalogIntegrityError(
                    f"tool row field set invalid: missing={row_missing} unknown={row_unknown}"
                )
            name = str(row["name"])
            if name in tools:
                raise CatalogIntegrityError(f"duplicate tool name: {name}")
            side_effect_class = str(row["side_effect_class"])
            if side_effect_class not in SIDE_EFFECT_CLASSES:
                raise CatalogIntegrityError(
                    f"unknown side-effect class for {name}: {side_effect_class}"
                )
            if side_effect_class == "PURE_READ":
                read_count += 1
            else:
                planning_count += 1
            input_schema_path = str(row["input_schema"])
            if input_schema_path not in input_schemas:
                raise CatalogIntegrityError(
                    f"input schema unresolved for {name}: {input_schema_path}"
                )
            refs = row["data_schema_refs"]
            if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)):
                raise CatalogIntegrityError(f"data_schema_refs invalid for {name}")
            for ref in refs:
                canonical_schema_name(str(ref))
            if side_effect_class == "DURABLE_PLAN_ARTIFACT" and len(refs) != 1:
                raise CatalogIntegrityError(
                    f"planning tool {name} must bind exactly one canonical artifact schema"
                )
            tools[name] = ToolSpec(
                name=name,
                title=str(row["title"]),
                side_effect_class=side_effect_class,
                handler_operation=str(row["handler_operation"]),
                input_schema_path=input_schema_path,
                data_schema_refs=tuple(str(ref) for ref in refs),
                capability=str(row["capability"]),
                confidentiality_concealment=bool(row["confidentiality_concealment"]),
            )
        if (
            read_count != EXPECTED_READ_TOOL_COUNT
            or planning_count != EXPECTED_PLANNING_TOOL_COUNT
            or int(document["read_tool_count"]) != read_count
            or int(document["planning_tool_count"]) != planning_count
        ):
            raise CatalogIntegrityError(
                f"catalog cardinality drifted: read={read_count} planning={planning_count}"
            )
        operations = [spec.handler_operation for spec in tools.values()]
        if len(operations) != len(set(operations)):
            raise CatalogIntegrityError("handler operations must be unique")
        return tools

    @property
    def tools(self) -> dict[str, ToolSpec]:
        return dict(self._tools)

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def spec(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise McpContractError("UNKNOWN_TOOL", f"unknown tool: {name}") from None

    def input_schema(self, name: str) -> dict[str, Any]:
        return json.loads(json.dumps(self._input_schemas[name]))

    def validate_arguments(self, name: str, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise McpContractError("INVALID_INPUT", "tool arguments must be an object")
        errors = sorted(
            error.message
            for error in self._input_validators[name].iter_errors(arguments)
        )
        if errors:
            raise McpContractError(
                "INVALID_INPUT",
                f"arguments do not satisfy the canonical input schema for {name}",
                {"schema_errors": errors},
            )
        return {str(key): value for key, value in arguments.items()}

    def validate_result_envelope(self, envelope: Mapping[str, Any]) -> None:
        errors = sorted(
            error.message for error in self._result_validator.iter_errors(envelope)
        )
        if errors:
            raise CatalogIntegrityError(f"result envelope invalid: {errors}")

    def validate_error_envelope(self, envelope: Mapping[str, Any]) -> None:
        errors = sorted(
            error.message for error in self._error_validator.iter_errors(envelope)
        )
        if errors:
            raise CatalogIntegrityError(f"error envelope invalid: {errors}")


def load_catalog(contracts_root: Path) -> ToolCatalog:
    """Load and verify the canonical catalog from a contracts checkout root."""

    catalog_path = contracts_root / CATALOG_RELATIVE_PATH
    document = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise CatalogIntegrityError("tool catalog must be a mapping")
    input_schemas: dict[str, Mapping[str, Any]] = {}
    for row in document.get("tools", ()):
        if isinstance(row, Mapping) and isinstance(row.get("input_schema"), str):
            relative = str(row["input_schema"])
            path = contracts_root / relative
            if not path.is_file():
                raise CatalogIntegrityError(f"input schema file missing: {relative}")
            input_schemas[relative] = json.loads(path.read_text(encoding="utf-8"))
    result_schema = json.loads(
        (contracts_root / RESULT_SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    error_schema = json.loads(
        (contracts_root / ERROR_SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    return ToolCatalog(
        document=document,
        input_schemas=input_schemas,
        result_schema=result_schema,
        error_schema=error_schema,
    )


class ToolHandler(Protocol):
    def execute(
        self,
        spec: ToolSpec,
        arguments: Mapping[str, Any],
        auth: AuthContext,
        *,
        request_id: str,
        generated_at: str,
    ) -> dict[str, Any]: ...


class ToolService:
    """Transport-neutral dispatcher enforcing the frozen authorization order."""

    def __init__(
        self,
        catalog: ToolCatalog,
        handlers: Mapping[str, ToolHandler],
        *,
        clock: Callable[[], str],
    ) -> None:
        registered = set(handlers)
        declared = set(catalog.tool_names)
        if registered != declared:
            raise CatalogIntegrityError(
                "handler registry does not match the canonical catalog: "
                f"missing={sorted(declared - registered)} "
                f"extra={sorted(registered - declared)}"
            )
        self._catalog = catalog
        self._handlers = dict(handlers)
        self._clock = clock

    @property
    def catalog(self) -> ToolCatalog:
        return self._catalog

    def call(
        self,
        tool_name: str,
        arguments: Any,
        auth: AuthContext,
        *,
        request_id: str,
    ) -> tuple[dict[str, Any], bool]:
        """Execute one tool call; returns ``(envelope, is_error)``."""

        try:
            spec = self._catalog.spec(tool_name)
            validated = self._catalog.validate_arguments(tool_name, arguments)
            if auth.principal_id is None:
                raise McpContractError(
                    "UNAUTHENTICATED", "the transport supplied no principal"
                )
            workspace_id = str(validated["workspace_id"])
            if auth.workspace_id is None or auth.workspace_id != workspace_id:
                raise McpContractError(
                    "WORKSPACE_DENIED",
                    "cross-workspace access is denied by default (EF4-I19)",
                )
            if spec.capability not in auth.capabilities:
                raise McpContractError(
                    "UNAUTHORIZED",
                    f"principal lacks capability {spec.capability}",
                )
            envelope = self._handlers[tool_name].execute(
                spec,
                validated,
                auth,
                request_id=request_id,
                generated_at=self._clock(),
            )
            self._catalog.validate_result_envelope(envelope)
            return envelope, False
        except McpContractError as error:
            envelope = {
                "protocol_version": PROTOCOL_VERSION,
                "tool": tool_name
                if tool_name in set(self._catalog.tool_names)
                else None,
                "request_id": request_id,
                "error_code": error.error_code,
                "message": str(error),
                "retryable": error.retryable,
                "details": error.details,
            }
            self._catalog.validate_error_envelope(envelope)
            return envelope, True


def result_envelope(
    spec: ToolSpec,
    *,
    request_id: str,
    workspace_id: str,
    read_model_state: str,
    data: Mapping[str, Any] | None,
    receipts: Sequence[Mapping[str, Any]] = (),
    degradation_reason: str | None = None,
    generated_at: str,
) -> dict[str, Any]:
    if read_model_state not in READ_MODEL_STATES:
        raise McpContractError(
            "INTERNAL",
            f"provider returned an unknown read-model state: {read_model_state}",
        )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "tool": spec.name,
        "request_id": request_id,
        "workspace_id": workspace_id,
        "read_model_state": read_model_state,
        "data": dict(data) if data is not None else None,
        "data_schema_refs": list(spec.data_schema_refs),
        "receipts": [dict(receipt) for receipt in receipts],
        "degradation_reason": degradation_reason,
        "generated_at": generated_at,
    }


def plan_artifact_registry() -> SchemaRegistry:
    """Canonical registry used to validate compiled plan artifacts."""

    return default_registry()
