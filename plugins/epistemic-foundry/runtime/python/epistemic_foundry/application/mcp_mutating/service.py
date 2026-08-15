"""T02 mutating tool catalog and the receipt-bound mutation service.

The canonical wire literals live in ``contracts/mcp/t02/tool-catalog.yaml``
(HD-EF4-T02-SCOPE-20260801-001); the sealed T01 catalog is untouched.  This
module loads and verifies that catalog and executes the frozen authorization
order with approval verification inside CAPABILITY_AUTHORIZATION, before lease
issuance.  No mutation is representable without a persisted ActionIntent, a
valid exact-scope CapabilityLease, and a resolving EffectReceipt; an
unresolved effect surfaces as UNKNOWN with reconciliation required, never as
success and never as a claim that nothing happened.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from ..mcp_common.contracts import (
    ERROR_SCHEMA_RELATIVE_PATH,
    PROTOCOL_VERSION,
    RESULT_SCHEMA_RELATIVE_PATH,
    AuthContext,
    CatalogIntegrityError,
    McpContractError,
    canonical_json_bytes,
    sha256_id,
)

CATALOG_RELATIVE_PATH: Final = "contracts/mcp/t02/tool-catalog.yaml"
CATALOG_SET_RELATIVE_PATH: Final = "contracts/mcp/catalog-set.yaml"
MUTATING_SIDE_EFFECT_CLASS: Final = "MUTATING_EFFECT"
EXPECTED_MUTATING_TOOL_COUNT: Final = 9

#: Closed mutation subcodes carried in the sealed error envelope's details.
MUTATION_ERROR_CODES: Final = (
    "APPROVAL_REQUIRED",
    "APPROVAL_DENIED",
    "APPROVAL_INVALID",
    "SELF_APPROVAL_FORBIDDEN",
    "LEASE_DENIED",
    "LEASE_INVALID",
    "REVISION_CONFLICT",
    "EFFECT_RECONCILING",
    "RECONCILIATION_FAILED",
)
#: Mapping onto the sealed top-level error_code enum.
MUTATION_ERROR_MAPPING: Final = {
    "APPROVAL_REQUIRED": "UNAUTHORIZED",
    "APPROVAL_DENIED": "UNAUTHORIZED",
    "APPROVAL_INVALID": "UNAUTHORIZED",
    "SELF_APPROVAL_FORBIDDEN": "UNAUTHORIZED",
    "LEASE_DENIED": "UNAUTHORIZED",
    "LEASE_INVALID": "UNAUTHORIZED",
    "REVISION_CONFLICT": "INVALID_REQUEST",
    "EFFECT_RECONCILING": "INTERNAL",
    "RECONCILIATION_FAILED": "INTERNAL",
}
APPROVAL_CLASSES: Final = ("POLICY_CONDITIONAL", "CONSENT_REQUIRED", "HUMAN_REQUIRED")
RISK_CLASSES: Final = ("low", "medium", "high", "critical")

_TOOL_FIELDS: Final = frozenset(
    {
        "name",
        "title",
        "side_effect_class",
        "handler_operation",
        "input_schema",
        "data_schema_refs",
        "capability",
        "risk_class",
        "approval_class",
        "expected_revision_required",
    }
)
_CATALOG_FIELDS: Final = frozenset(
    {
        "catalog_id",
        "catalog_version",
        "protocol_version",
        "mutating_tool_count",
        "common_input_schema",
        "mutation_result_schema",
        "mutation_error_details_schema",
        "tools",
    }
)


class MutationError(McpContractError):
    """A typed mutation failure carrying its closed subcode."""

    def __init__(
        self,
        mutation_error_code: str,
        message: str,
        *,
        intent_candidate_id: str | None = None,
        action_intent_id: str | None = None,
        effect_receipt_id: str | None = None,
        reconciliation_required: bool = False,
    ) -> None:
        if mutation_error_code not in MUTATION_ERROR_CODES:
            raise AssertionError(f"unknown mutation error code: {mutation_error_code}")
        super().__init__(
            MUTATION_ERROR_MAPPING[mutation_error_code],
            message,
            {
                "action_intent_id": action_intent_id,
                "effect_receipt_id": effect_receipt_id,
                "intent_candidate_id": intent_candidate_id,
                "mutation_error_code": mutation_error_code,
                "reconciliation_required": reconciliation_required,
            },
        )
        self.mutation_error_code = mutation_error_code


@dataclass(frozen=True, slots=True)
class MutatingToolSpec:
    name: str
    title: str
    handler_operation: str
    input_schema_path: str
    data_schema_refs: tuple[str, ...]
    capability: str
    risk_class: str
    approval_class: str
    expected_revision_required: bool

    @property
    def side_effect_class(self) -> str:
        """Constant by construction; the catalog verifies every row declares it."""

        return MUTATING_SIDE_EFFECT_CLASS


class MutatingToolCatalog:
    """Verified, immutable projection of the canonical T02 catalog."""

    def __init__(
        self,
        *,
        document: Mapping[str, Any],
        input_schemas: Mapping[str, Mapping[str, Any]],
        result_schema: Mapping[str, Any],
        error_details_schema: Mapping[str, Any],
        envelope_result_schema: Mapping[str, Any],
        envelope_error_schema: Mapping[str, Any],
        common_input_schema: Mapping[str, Any],
    ) -> None:
        # The shared T01 envelopes are reused, never duplicated: T02 adds only
        # its mutation payload and its closed error subcode.
        self._envelope_result_validator = Draft202012Validator(
            dict(envelope_result_schema)
        )
        self._envelope_error_validator = Draft202012Validator(
            dict(envelope_error_schema)
        )
        self._tools = self._verify(document, input_schemas)
        self._input_schemas = {
            name: dict(input_schemas[spec.input_schema_path])
            for name, spec in self._tools.items()
        }
        # The shared common-input schema is resolvable, so every tool schema's
        # $ref to it is actually enforced rather than silently skipped.
        registry = Registry().with_resource(
            str(common_input_schema["$id"]),
            Resource.from_contents(
                dict(common_input_schema), default_specification=DRAFT202012
            ),
        )
        self._input_validators = {
            name: Draft202012Validator(
                dict(input_schemas[spec.input_schema_path]), registry=registry
            )
            for name, spec in self._tools.items()
        }
        Draft202012Validator.check_schema(dict(result_schema))
        Draft202012Validator.check_schema(dict(error_details_schema))
        self._result_validator = Draft202012Validator(dict(result_schema))
        self._error_details_validator = Draft202012Validator(dict(error_details_schema))

    @staticmethod
    def _verify(
        document: Mapping[str, Any],
        input_schemas: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, MutatingToolSpec]:
        missing = sorted(_CATALOG_FIELDS - set(document))
        unknown = sorted(set(document) - _CATALOG_FIELDS)
        if missing or unknown:
            raise CatalogIntegrityError(
                f"T02 catalog field set invalid: missing={missing} unknown={unknown}"
            )
        if document["protocol_version"] != PROTOCOL_VERSION:
            raise CatalogIntegrityError("T02 catalog protocol version drifted")
        rows = document["tools"]
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise CatalogIntegrityError("T02 catalog tools must be an array")
        tools: dict[str, MutatingToolSpec] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise CatalogIntegrityError("T02 catalog tool row must be an object")
            row_missing = sorted(_TOOL_FIELDS - set(row))
            row_unknown = sorted(set(row) - _TOOL_FIELDS)
            if row_missing or row_unknown:
                raise CatalogIntegrityError(
                    f"T02 tool row field set invalid: missing={row_missing} "
                    f"unknown={row_unknown}"
                )
            name = str(row["name"])
            if name in tools:
                raise CatalogIntegrityError(f"duplicate T02 tool name: {name}")
            if row["side_effect_class"] != MUTATING_SIDE_EFFECT_CLASS:
                raise CatalogIntegrityError(
                    f"{name} is not declared as {MUTATING_SIDE_EFFECT_CLASS}"
                )
            if row["approval_class"] not in APPROVAL_CLASSES:
                raise CatalogIntegrityError(
                    f"{name} has a non-canonical approval class"
                )
            if row["risk_class"] not in RISK_CLASSES:
                raise CatalogIntegrityError(f"{name} has a non-canonical risk class")
            input_schema_path = str(row["input_schema"])
            if input_schema_path not in input_schemas:
                raise CatalogIntegrityError(
                    f"input schema unresolved for {name}: {input_schema_path}"
                )
            refs = row["data_schema_refs"]
            if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)):
                raise CatalogIntegrityError(f"data_schema_refs invalid for {name}")
            tools[name] = MutatingToolSpec(
                approval_class=str(row["approval_class"]),
                capability=str(row["capability"]),
                data_schema_refs=tuple(str(ref) for ref in refs),
                expected_revision_required=bool(row["expected_revision_required"]),
                handler_operation=str(row["handler_operation"]),
                input_schema_path=input_schema_path,
                name=name,
                risk_class=str(row["risk_class"]),
                title=str(row["title"]),
            )
        if len(tools) != EXPECTED_MUTATING_TOOL_COUNT or int(
            document["mutating_tool_count"]
        ) != len(tools):
            raise CatalogIntegrityError(
                f"T02 catalog cardinality drifted: {len(tools)}"
            )
        operations = [spec.handler_operation for spec in tools.values()]
        if len(operations) != len(set(operations)):
            raise CatalogIntegrityError("T02 handler operations must be unique")
        return tools

    @property
    def tools(self) -> dict[str, MutatingToolSpec]:
        return dict(self._tools)

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def spec(self, name: str) -> MutatingToolSpec:
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

    def validate_result_payload(self, payload: Mapping[str, Any]) -> None:
        errors = sorted(
            error.message for error in self._result_validator.iter_errors(payload)
        )
        if errors:
            raise CatalogIntegrityError(f"mutation result payload invalid: {errors}")

    def validate_error_details(self, details: Mapping[str, Any]) -> None:
        errors = sorted(
            error.message
            for error in self._error_details_validator.iter_errors(details)
        )
        if errors:
            raise CatalogIntegrityError(f"mutation error details invalid: {errors}")

    def validate_result_envelope(self, envelope: Mapping[str, Any]) -> None:
        """Shared-envelope check plus the required T02 mutation payload."""

        errors = sorted(
            error.message
            for error in self._envelope_result_validator.iter_errors(envelope)
        )
        if errors:
            raise CatalogIntegrityError(f"result envelope invalid: {errors}")
        data = envelope.get("data")
        if not isinstance(data, Mapping):
            raise CatalogIntegrityError(
                "a mutating result must carry a mutation payload"
            )
        self.validate_result_payload(data)

    def validate_error_envelope(self, envelope: Mapping[str, Any]) -> None:
        """Shared-envelope check plus the closed mutation subcode in details."""

        errors = sorted(
            error.message
            for error in self._envelope_error_validator.iter_errors(envelope)
        )
        if errors:
            raise CatalogIntegrityError(f"error envelope invalid: {errors}")
        details = envelope.get("details")
        if isinstance(details, Mapping) and "mutation_error_code" in details:
            self.validate_error_details(details)
            expected = MUTATION_ERROR_MAPPING[str(details["mutation_error_code"])]
            if envelope.get("error_code") != expected:
                raise CatalogIntegrityError(
                    "the mutation subcode does not map to its sealed top-level code"
                )


def load_mutating_catalog(contracts_root: Path) -> MutatingToolCatalog:
    """Load and verify the canonical T02 catalog from a contracts checkout."""

    document = yaml.safe_load(
        (contracts_root / CATALOG_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    if not isinstance(document, Mapping):
        raise CatalogIntegrityError("T02 tool catalog must be a mapping")
    input_schemas: dict[str, Mapping[str, Any]] = {}
    for row in document.get("tools", ()):
        if isinstance(row, Mapping) and isinstance(row.get("input_schema"), str):
            relative = str(row["input_schema"])
            path = contracts_root / relative
            if not path.is_file():
                raise CatalogIntegrityError(f"input schema file missing: {relative}")
            input_schemas[relative] = json.loads(path.read_text(encoding="utf-8"))
    result_schema = json.loads(
        (contracts_root / str(document["mutation_result_schema"])).read_text(
            encoding="utf-8"
        )
    )
    error_details_schema = json.loads(
        (contracts_root / str(document["mutation_error_details_schema"])).read_text(
            encoding="utf-8"
        )
    )
    return MutatingToolCatalog(
        common_input_schema=json.loads(
            (contracts_root / str(document["common_input_schema"])).read_text(
                encoding="utf-8"
            )
        ),
        document=document,
        input_schemas=input_schemas,
        result_schema=result_schema,
        error_details_schema=error_details_schema,
        envelope_result_schema=json.loads(
            (contracts_root / RESULT_SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8")
        ),
        envelope_error_schema=json.loads(
            (contracts_root / ERROR_SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8")
        ),
    )


def load_catalog_set(contracts_root: Path) -> dict[str, Any]:
    """Load and cross-verify the literal-free catalog set.

    Each declared count is checked against the referenced catalog's own count
    fields and its actual row count, so ``tools/list`` cardinality cannot drift
    in one file only.
    """

    text = (contracts_root / CATALOG_SET_RELATIVE_PATH).read_text(encoding="utf-8")
    if "foundry." in text:
        raise CatalogIntegrityError(
            "the catalog set must hold no MCP tool-name literal"
        )
    document = yaml.safe_load(text)
    if not isinstance(document, Mapping):
        raise CatalogIntegrityError("catalog set must be a mapping")
    if document.get("protocol_version") != PROTOCOL_VERSION:
        raise CatalogIntegrityError("catalog set protocol version drifted")
    catalogs = document.get("catalogs")
    if not isinstance(catalogs, Sequence) or len(catalogs) != 2:
        raise CatalogIntegrityError("catalog set must list exactly two catalogs")
    identifiers = [str(entry["catalog_id"]) for entry in catalogs]
    if list(document.get("merge_order", ())) != identifiers:
        raise CatalogIntegrityError("merge order must match declared catalogs")
    total = 0
    for entry in catalogs:
        declared = int(entry["exact_count"])
        total += declared
        referenced = yaml.safe_load(
            (contracts_root / str(entry["ref"])).read_text(encoding="utf-8")
        )
        if str(referenced["catalog_id"]) != str(entry["catalog_id"]):
            raise CatalogIntegrityError(
                f"catalog set reference mismatch for {entry['catalog_id']}"
            )
        summed = sum(int(referenced[field]) for field in entry["count_fields"])
        if summed != declared or len(referenced["tools"]) != declared:
            raise CatalogIntegrityError(
                f"declared count {declared} does not match {entry['catalog_id']}"
            )
    if int(document.get("global_exact_count", -1)) != total:
        raise CatalogIntegrityError("global exact count does not equal the parts")
    return dict(document)


def semantic_fingerprint(
    *,
    tool: str,
    auth: AuthContext,
    arguments: Mapping[str, Any],
) -> str:
    """The idempotency fingerprint of one semantic mutation request.

    ``approval_record_ids`` are authorization evidence rather than
    effect-defining arguments, so supplying approvals after an
    APPROVAL_REQUIRED response is not an idempotency conflict.  ``dry_run`` is
    included, so a dry-run key can never be reused for a live commit.
    """

    return sha256_id(
        canonical_json_bytes(
            {
                "arguments": dict(arguments.get("arguments", {})),
                "dry_run": bool(arguments["dry_run"]),
                "expected_revision": arguments["expected_revision"],
                "principal_id": auth.principal_id,
                "protocol_version": PROTOCOL_VERSION,
                "target_ref": arguments["target_ref"],
                "tool": tool,
                "workspace_id": arguments["workspace_id"],
            }
        )
    )
