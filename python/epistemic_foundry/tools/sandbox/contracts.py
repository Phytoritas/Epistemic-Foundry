"""T04 deterministic sandbox and external tool adapter gate contracts.

An external tool is admitted through its declared ``ValidationTargetManifest``
and nothing else.  The manifest already names the sandbox profile, the network
policy, the capabilities the adapter requires, the safety class, the approval
policy and the data classes it may touch, so this gate reads those vocabularies
from the canonical schemas rather than restating them.  A value the schema does
not declare fails closed instead of falling through to a permissive default.

Two things the exit criteria demand are derived here, never asserted.  Every
byte an adapter returns is content-addressed before it can become evidence: a
receipt that declares a hash the payload does not produce is refused, and a
truncated capture is hashed as what was actually captured.  Every invocation
runs inside a bounded envelope: a call and wall-clock ceiling are mandatory, a
breach resolves through the ``BudgetEnvelope``'s own breach policy, and a run
that is cancelled or times out still yields an ``EffectReceipt`` whose status
follows what was observed rather than what was intended.  ``UNKNOWN`` carries
``reconciliation_required`` because an interrupted external effect is not the
same as an effect that never happened.

Isolation is the third axis and it dominates the other two.  The holdout
manifest declares candidate, mutation-model, prompt and backend access as
constant ``false``; a profile that grants a sandboxed principal reach into a
hidden partition or the evaluator is refused even when every capability and
quota check would otherwise pass.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Final

SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)

#: The external tool adapter descriptor.  T04 governs what it declares.
TARGET_SCHEMA_PATH: Final = "schemas/validation-target-manifest.schema.json"
#: Quota dimensions, enforcement modes and breach policy.
BUDGET_SCHEMA_PATH: Final = "schemas/budget-envelope.schema.json"
#: Effect status vocabulary for a completed, cancelled or timed-out run.
EFFECT_SCHEMA_PATH: Final = "schemas/effect-receipt.schema.json"
#: Hashed-output receipt shape.
ARTIFACT_SCHEMA_PATH: Final = "schemas/artifact-receipt.schema.json"
#: Evaluator and holdout isolation constants.
HOLDOUT_SCHEMA_PATH: Final = "schemas/holdout-manifest.schema.json"
#: The lease that must already grant everything the adapter requires.
LEASE_SCHEMA_PATH: Final = "schemas/capability-lease.schema.json"


class Denial(str, Enum):
    """Typed refusals.  Every path out of this gate is one of these or ALLOW."""

    ADAPTER_UNSEALED = "ADAPTER_UNSEALED"
    APPROVAL_MISSING = "APPROVAL_MISSING"
    APPROVAL_UNLEASED = "APPROVAL_UNLEASED"
    CAPABILITY_UNDECLARED = "CAPABILITY_UNDECLARED"
    DATA_CLASS_DENIED = "DATA_CLASS_DENIED"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    EGRESS_DENIED = "EGRESS_DENIED"
    ISOLATION_BREACH = "ISOLATION_BREACH"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    LEASE_INVALID = "LEASE_INVALID"
    LEASE_INSUFFICIENT = "LEASE_INSUFFICIENT"
    LEASE_NOT_YET_VALID = "LEASE_NOT_YET_VALID"
    LEASE_REVOKED = "LEASE_REVOKED"
    LEASE_SCOPE_DENIED = "LEASE_SCOPE_DENIED"
    LEASE_UNSEALED = "LEASE_UNSEALED"
    PATH_ESCAPE = "PATH_ESCAPE"
    POLICY_UNPINNED = "POLICY_UNPINNED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    QUOTA_UNBOUNDED = "QUOTA_UNBOUNDED"
    STALE_FENCING_TOKEN = "STALE_FENCING_TOKEN"


class Observation(str, Enum):
    """What the adapter could actually observe about the external side."""

    NOT_STARTED = "NOT_STARTED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class GateStatus(str, Enum):
    """Gate outcomes, weakest first; a declared status above the derived one
    is an overclaim."""

    FAIL = "FAIL"
    CONDITIONAL = "CONDITIONAL"
    PASS = "PASS"


DENIALS: Final = tuple(entry.value for entry in Denial)
OBSERVATIONS: Final = tuple(entry.value for entry in Observation)
GATE_LADDER: Final = (
    GateStatus.FAIL.value,
    GateStatus.CONDITIONAL.value,
    GateStatus.PASS.value,
)

#: What each canonical network policy demands of a request.  Verified against
#: the manifest schema on every read, so a policy value this table does not
#: know fails loudly instead of being treated as permissive.
NETWORK_POLICY_RULE: Final = {
    "disabled": "NO_EGRESS",
    "allowlist": "EXACT_ORIGIN",
    "unrestricted_with_approval": "APPROVAL_REQUIRED",
}
#: Which safety classes an approval policy actually gates.
APPROVAL_RULE: Final = {
    "none": (),
    "high_risk_only": ("high_risk",),
    "all_effects": ("controlled_effect", "high_risk"),
}
#: Metering strength, weakest first.  UNMETERED never satisfies any class.
ENFORCEMENT_STRENGTH: Final = {
    "UNMETERED": 0,
    "SOFT_ESTIMATE": 1,
    "HARD_METERED": 2,
    "HARD_PREALLOCATED": 3,
}
#: The weakest metering each safety class may run under.
SAFETY_CLASS_METERING: Final = {
    "read_only": "SOFT_ESTIMATE",
    "bounded_compute": "HARD_METERED",
    "controlled_effect": "HARD_METERED",
    "high_risk": "HARD_PREALLOCATED",
}
#: How a quota breach resolves.  The action is the envelope's own policy, not
#: this component's preference.
BREACH_ACTION: Final = {
    "CANCEL": "DENIED",
    "PAUSE_AND_ESCALATE": "ESCALATED",
    "MARK_PARTIAL": "TRUNCATED",
    "WARN": "WARNED",
}
#: Breach actions that stop the invocation rather than continue it.
STOPPING_BREACH_ACTIONS: Final = ("DENIED", "ESCALATED")
#: Observed outcome -> (effect status, reconciliation_required).  An
#: interrupted run is UNKNOWN and must reconcile; a proven non-start is not.
OBSERVATION_STATUS: Final = {
    Observation.NOT_STARTED.value: ("NOT_EXECUTED", False),
    Observation.STARTED.value: ("UNKNOWN", True),
    Observation.COMPLETED.value: ("SUCCEEDED", False),
    Observation.FAILED.value: ("FAILED", False),
    Observation.ROLLED_BACK.value: ("ROLLED_BACK", False),
}
#: Ceilings every admitted invocation must carry, whatever it does.
REQUIRED_BOUNDED_DIMENSIONS: Final = ("calls", "wall_seconds")
#: An adapter that may reach the network must also bound what it sends.
EGRESS_BOUNDED_DIMENSIONS: Final = ("network_bytes",)
#: Safety classes whose adapters must be reproducibly pinned.
PINNED_SAFETY_CLASSES: Final = APPROVAL_RULE["all_effects"]
#: Gate criteria, all of which must hold for a PASS.
GATE_CRITERIA: Final = (
    "capabilities_declared",
    "isolation_verified",
    "lease_bound",
    "quotas_bounded",
    "deadline_enforced",
    "outputs_hashed",
    "effects_reconciled",
)

_WINDOWS_RESERVED = re.compile(
    r"^(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9]|LPT[1-9])$", re.IGNORECASE
)
_REQUEST_FIELDS: Final = frozenset(
    {
        "approval_record_ids",
        "capabilities",
        "data_class",
        "network_url",
        "paths",
        "principal_id",
        "principal_type",
    }
)
_PATH_FIELDS: Final = frozenset({"operation", "relative_path", "root_id"})
#: Principal types whose reach into a holdout partition the schema forbids.
SANDBOXED_PRINCIPAL_TYPES: Final = ("agent", "service", "tool")


class SandboxGateError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    raise SandboxGateError(code, message, context)


@dataclass(frozen=True)
class SealedArtifact:
    """Immutable canonical JSON snapshot with a fresh projection on access."""

    artifact_type: str
    _canonical_bytes: bytes

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self._canonical_bytes.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("sealed artifact is not an object")
        return value


@dataclass(frozen=True)
class SandboxDecision:
    """An allow decision naming exactly what it allowed and why."""

    adapter_id: str
    sandbox_profile: str
    network_policy: str
    safety_class: str
    data_class: str
    granted_capabilities: tuple[str, ...]
    granted_roots: tuple[str, ...]
    egress_origin: str | None
    isolation_verified: tuple[str, ...]
    lease_id: str
    lease_hash: str
    lease_policy_hash: str
    lease_fencing_token: int
    scope_fencing_heads: tuple[tuple[str, int], ...]
    scope_fencing_heads_hash: str


@dataclass(frozen=True)
class QuotaLedger:
    """Bounded consumption state.  Limits come from the sealed envelope."""

    budget_id: str
    enforcement: str
    breach_policy: str
    limits: Mapping[str, int | None]
    consumed: Mapping[str, int]


@dataclass(frozen=True)
class QuotaOutcome:
    """The ledger after a consumption attempt plus the breach it caused."""

    ledger: QuotaLedger
    breach: dict[str, Any] | None

    @property
    def stopped(self) -> bool:
        return (
            self.breach is not None and self.breach["action"] in STOPPING_BREACH_ACTIONS
        )


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _fail("CANONICALIZATION_FAILED", f"value is not canonical JSON: {error}")
        raise  # pragma: no cover - _fail always raises


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _hash_excluding(payload: Mapping[str, Any], field: str) -> str:
    return _digest({key: value for key, value in payload.items() if key != field})


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping")
    result: dict[str, Any] = {}
    for key, entry in value.items():  # type: ignore[union-attr]
        if not isinstance(key, str):
            _fail("INPUT_INVALID", f"{label} keys must be strings")
        result[key] = entry
    return result


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("INPUT_INVALID", f"{label} must be an array")
    return list(value)  # type: ignore[arg-type]


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            f"{label} field set is invalid",
            {"missing": missing, "unknown": unknown},
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string")
    return str(value)


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label)
    if RFC3339_PATTERN.fullmatch(text) is None:
        _fail("INPUT_INVALID", f"{label} must be an RFC3339 timestamp")
    return text


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    entries = [
        _text(entry, f"{label}[{index}]")
        for index, entry in enumerate(_sequence(value, label))
    ]
    if len(set(entries)) != len(entries):
        _fail("INPUT_INVALID", f"{label} must not repeat an entry")
    return tuple(entries)


def _utf16_sorted(values: Sequence[str], label: str) -> tuple[str, ...]:
    """Match JavaScript's default string ordering used by the E03 issuer."""

    try:
        return tuple(sorted(values, key=lambda value: value.encode("utf-16-be")))
    except UnicodeEncodeError:
        _fail(Denial.LEASE_INVALID.value, f"{label} must contain Unicode scalars")
        raise  # pragma: no cover - _fail always raises


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        _fail("INPUT_INVALID", f"{label} must be a boolean")
    return bool(value)


def _bounded_text(
    value: object,
    label: str,
    *,
    minimum: int = 1,
    maximum: int | None = None,
    code: str = "INPUT_INVALID",
) -> str:
    text = _scalar_text(value, label, code=code)
    if len(text) < minimum or (maximum is not None and len(text) > maximum):
        upper = "unbounded" if maximum is None else str(maximum)
        _fail(
            code,
            f"{label} length must be within {minimum}..{upper}",
        )
    return text


def _scalar_text(value: object, label: str, *, code: str = "INPUT_INVALID") -> str:
    text = _text(value, label)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        _fail(code, f"{label} must contain Unicode scalar values")
        raise  # pragma: no cover - _fail always raises
    return text


def _schema(repository_root: str | Path, relative: str) -> dict[str, Any]:
    path = Path(repository_root) / relative
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail("SCHEMA_UNREADABLE", f"{relative} could not be read: {error}")
        raise  # pragma: no cover - _fail always raises
    return _mapping(loaded, relative)


def _enum(repository_root: str | Path, relative: str, *path: str) -> tuple[str, ...]:
    node: Any = _schema(repository_root, relative)
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            _fail("SCHEMA_UNREADABLE", f"{relative} does not declare {'.'.join(path)}")
        node = node[key]  # type: ignore[index]
    if not isinstance(node, list) or not node:
        _fail("SCHEMA_UNREADABLE", f"{relative} declares an empty {'.'.join(path)}")
    return tuple(str(entry) for entry in node)  # type: ignore[union-attr]


def _pattern(repository_root: str | Path, relative: str, *path: str) -> re.Pattern[str]:
    node: Any = _schema(repository_root, relative)
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            _fail("SCHEMA_UNREADABLE", f"{relative} does not declare {'.'.join(path)}")
        node = node[key]  # type: ignore[index]
    if not isinstance(node, str) or not node:
        _fail("SCHEMA_UNREADABLE", f"{relative} declares an empty {'.'.join(path)}")
    return re.compile(str(node))


def _assert_table(
    table: Mapping[str, Any], declared: Sequence[str], label: str
) -> None:
    """A local decision table must cover the declaring source exactly."""

    missing = sorted(set(declared) - set(table))
    unknown = sorted(set(table) - set(declared))
    if missing or unknown:
        _fail(
            "VOCABULARY_DRIFT",
            f"the {label} table no longer matches the schema that declares it",
            {"missing": missing, "unknown": unknown},
        )


def target_manifest_fields(repository_root: str | Path) -> frozenset[str]:
    """The exact field set a ValidationTargetManifest must carry."""

    schema = _schema(repository_root, TARGET_SCHEMA_PATH)
    required = schema.get("required")
    if not isinstance(required, list) or not required:
        _fail(
            "SCHEMA_UNREADABLE", "the target manifest schema declares no required set"
        )
    return frozenset(str(entry) for entry in required)  # type: ignore[union-attr]


def capability_lease_fields(repository_root: str | Path) -> frozenset[str]:
    """The exact field set the canonical CapabilityLease schema requires."""

    schema = _schema(repository_root, LEASE_SCHEMA_PATH)
    required = schema.get("required")
    properties = schema.get("properties")
    if (
        schema.get("additionalProperties") is not False
        or not isinstance(required, list)
        or not required
        or not isinstance(properties, Mapping)
        or any(not isinstance(entry, str) or not entry for entry in required)
    ):
        _fail("SCHEMA_UNREADABLE", "the capability lease schema is incomplete")
    fields = frozenset(required)
    if len(fields) != len(required) or fields != frozenset(properties):
        _fail(
            "SCHEMA_UNREADABLE",
            "the capability lease schema required/properties sets disagree",
        )
    return fields


def lease_principal_types(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root,
        LEASE_SCHEMA_PATH,
        "properties",
        "principal_type",
        "enum",
    )


def network_policies(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, TARGET_SCHEMA_PATH, "properties", "network_policy", "enum"
    )


def safety_classes(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, TARGET_SCHEMA_PATH, "properties", "safety_class", "enum"
    )


def approval_policies(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, TARGET_SCHEMA_PATH, "properties", "approval_policy", "enum"
    )


def data_classes(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root,
        TARGET_SCHEMA_PATH,
        "properties",
        "allowed_data_classes",
        "items",
        "enum",
    )


def target_types(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, TARGET_SCHEMA_PATH, "properties", "target_type", "enum"
    )


def quota_dimensions(repository_root: str | Path) -> tuple[str, ...]:
    schema = _schema(repository_root, BUDGET_SCHEMA_PATH)
    limits = schema.get("properties", {}).get("hard_limits", {})
    required = limits.get("required") if isinstance(limits, Mapping) else None
    if not isinstance(required, list) or not required:
        _fail("SCHEMA_UNREADABLE", "the budget schema declares no hard_limits set")
    return tuple(str(entry) for entry in required)  # type: ignore[union-attr]


def enforcement_modes(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, BUDGET_SCHEMA_PATH, "properties", "enforcement", "enum"
    )


def breach_policies(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, BUDGET_SCHEMA_PATH, "properties", "breach_policy", "enum"
    )


def effect_statuses(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(repository_root, EFFECT_SCHEMA_PATH, "properties", "status", "enum")


def artifact_check_statuses(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root,
        ARTIFACT_SCHEMA_PATH,
        "properties",
        "validation_results",
        "items",
        "properties",
        "status",
        "enum",
    )


def isolation_boundaries(repository_root: str | Path) -> tuple[str, ...]:
    """Holdout access flags the schema pins to a constant ``false``.

    These are the boundaries a sandbox may not cross.  Reading them keeps the
    gate honest if the holdout contract ever adds another one.
    """

    schema = _schema(repository_root, HOLDOUT_SCHEMA_PATH)
    properties = _mapping(schema.get("properties", {}), "holdout properties")
    boundaries = tuple(
        sorted(
            name
            for name, node in properties.items()
            if isinstance(node, Mapping) and node.get("const") is False
        )
    )
    if not boundaries:
        _fail(
            "SCHEMA_UNREADABLE", "the holdout schema pins no access boundary to false"
        )
    return boundaries


def holdout_manifest_fields(repository_root: str | Path) -> frozenset[str]:
    """Return the exact closed field set of the canonical holdout manifest."""

    schema = _schema(repository_root, HOLDOUT_SCHEMA_PATH)
    properties = _mapping(schema.get("properties", {}), "holdout properties")
    required = schema.get("required")
    if (
        not isinstance(required, list)
        or not required
        or any(not isinstance(field, str) or not field for field in required)
        or len(set(required)) != len(required)
        or frozenset(required) != frozenset(properties)
        or schema.get("additionalProperties") is not False
    ):
        _fail(
            "SCHEMA_UNREADABLE",
            "the holdout schema does not declare one exact closed required field set",
        )
    return frozenset(required)


def seal_adapter(
    repository_root: str | Path, payload: Mapping[str, Any]
) -> SealedArtifact:
    """Validate and content-address an external tool adapter manifest."""

    value = _mapping(payload, "ValidationTargetManifest")
    _exact_fields(
        value, target_manifest_fields(repository_root), "ValidationTargetManifest"
    )

    target_id = _text(value["target_id"], "target_id")
    identifier = _pattern(
        repository_root, TARGET_SCHEMA_PATH, "properties", "target_id", "pattern"
    )
    if identifier.fullmatch(target_id) is None:
        _fail(
            "ADAPTER_ID_INVALID",
            "an adapter id must match the pattern its own manifest schema declares",
            {"pattern": identifier.pattern, "target_id": target_id},
        )
    target_type = _text(value["target_type"], "target_type")
    if target_type not in target_types(repository_root):
        _fail(
            "TARGET_TYPE_INVALID", f"{target_id} declares a non-canonical target_type"
        )

    network_policy = _text(value["network_policy"], "network_policy")
    declared_policies = network_policies(repository_root)
    _assert_table(NETWORK_POLICY_RULE, declared_policies, "network policy")
    if network_policy not in declared_policies:
        _fail(
            "NETWORK_POLICY_INVALID", f"{target_id} declares an unknown network policy"
        )

    safety_class = _text(value["safety_class"], "safety_class")
    declared_classes = safety_classes(repository_root)
    _assert_table(SAFETY_CLASS_METERING, declared_classes, "safety class metering")
    if safety_class not in declared_classes:
        _fail("SAFETY_CLASS_INVALID", f"{target_id} declares an unknown safety class")

    approval_policy = _text(value["approval_policy"], "approval_policy")
    declared_approvals = approval_policies(repository_root)
    _assert_table(APPROVAL_RULE, declared_approvals, "approval policy")
    if approval_policy not in declared_approvals:
        _fail(
            "APPROVAL_POLICY_INVALID",
            f"{target_id} declares an unknown approval policy",
        )
    for policy, gated in APPROVAL_RULE.items():
        unknown = sorted(set(gated) - set(declared_classes))
        if unknown:
            _fail(
                "VOCABULARY_DRIFT",
                f"approval policy {policy} gates a class the schema does not declare",
                {"unknown": unknown},
            )

    allowed = _string_tuple(value["allowed_data_classes"], "allowed_data_classes")
    if not allowed:
        _fail("DATA_CLASS_UNDECLARED", f"{target_id} allows no data class")
    unknown_classes = sorted(set(allowed) - set(data_classes(repository_root)))
    if unknown_classes:
        _fail(
            "DATA_CLASS_INVALID",
            f"{target_id} allows a data class the schema does not declare",
            {"unknown": unknown_classes},
        )

    capabilities = _string_tuple(
        value["capability_requirements"], "capability_requirements"
    )
    if not capabilities:
        _fail(
            "CAPABILITY_UNDECLARED",
            f"{target_id} requires no capability; an adapter must name what it needs",
        )

    hashes = _string_tuple(value["artifact_hashes"], "artifact_hashes")
    if not hashes:
        _fail("ADAPTER_UNPINNED", f"{target_id} pins no artifact hash")
    for entry in hashes:
        if SHA256_PATTERN.fullmatch(entry) is None:
            _fail(
                "ADAPTER_UNPINNED", f"{target_id} declares a non-sha256 artifact hash"
            )

    reproducibility = _mapping(
        value["reproducibility_contract"], "reproducibility_contract"
    )
    _exact_fields(
        reproducibility,
        frozenset({"container_digest_required", "environment_capture", "seed_control"}),
        "reproducibility_contract",
    )
    pinned = {
        key: _boolean(reproducibility[key], key) for key in sorted(reproducibility)
    }
    if (
        safety_class in PINNED_SAFETY_CLASSES
        and not pinned["container_digest_required"]
    ):
        _fail(
            "REPRODUCIBILITY_UNPINNED",
            f"{target_id} takes effects but does not require a container digest",
        )

    sealed = {
        "adapter_id": target_id,
        "allowed_data_classes": sorted(allowed),
        "artifact_hashes": sorted(hashes),
        "approval_policy": approval_policy,
        "capability_requirements": sorted(capabilities),
        "entrypoint": _text(value["entrypoint"], "entrypoint"),
        "interface_version": _text(value["interface_version"], "interface_version"),
        "network_policy": network_policy,
        "reproducibility_contract": pinned,
        "safety_class": safety_class,
        "sandbox_profile": _text(value["sandbox_profile"], "sandbox_profile"),
        "supply_chain_attestation_artifact_id": _text(
            value["supply_chain_attestation_artifact_id"],
            "supply_chain_attestation_artifact_id",
        ),
        "target_type": target_type,
        "version": _text(value["version"], "version"),
    }
    sealed["adapter_hash"] = _digest(sealed)
    return SealedArtifact("tool_adapter", _canonical_json(sealed))


def seal_quota_envelope(
    repository_root: str | Path, payload: Mapping[str, Any]
) -> SealedArtifact:
    """Validate and content-address the quota-bearing subset of a BudgetEnvelope.

    The sealed projection is this gate's own artifact, not a BudgetEnvelope: it
    carries only the fields that bound an invocation, under this component's
    own hash field.
    """

    value = _mapping(payload, "quota envelope")
    _exact_fields(
        value,
        frozenset({"budget_id", "breach_policy", "enforcement", "hard_limits"}),
        "quota envelope",
    )
    budget_id = _text(value["budget_id"], "budget_id")

    declared_modes = enforcement_modes(repository_root)
    _assert_table(ENFORCEMENT_STRENGTH, declared_modes, "enforcement strength")
    enforcement = _text(value["enforcement"], "enforcement")
    if enforcement not in declared_modes:
        _fail(
            "ENFORCEMENT_INVALID", f"{budget_id} declares an unknown enforcement mode"
        )

    declared_breaches = breach_policies(repository_root)
    _assert_table(BREACH_ACTION, declared_breaches, "breach action")
    breach_policy = _text(value["breach_policy"], "breach_policy")
    if breach_policy not in declared_breaches:
        _fail("BREACH_POLICY_INVALID", f"{budget_id} declares an unknown breach policy")

    dimensions = quota_dimensions(repository_root)
    unknown_required = sorted(set(REQUIRED_BOUNDED_DIMENSIONS) - set(dimensions))
    unknown_egress = sorted(set(EGRESS_BOUNDED_DIMENSIONS) - set(dimensions))
    if unknown_required or unknown_egress:
        _fail(
            "VOCABULARY_DRIFT",
            "a mandatory ceiling names a dimension the budget schema does not declare",
            {"unknown": sorted(set(unknown_required + unknown_egress))},
        )

    limits_value = _mapping(value["hard_limits"], "hard_limits")
    _exact_fields(limits_value, frozenset(dimensions), "hard_limits")
    limits: dict[str, int | None] = {}
    for dimension in dimensions:
        entry = limits_value[dimension]
        if entry is None:
            limits[dimension] = None
            continue
        if not isinstance(entry, int) or isinstance(entry, bool) or entry < 0:
            _fail(
                "LIMIT_INVALID",
                f"hard_limits.{dimension} must be a non-negative integer or null",
            )
        limits[dimension] = int(entry)

    sealed = {
        "breach_policy": breach_policy,
        "budget_id": budget_id,
        "enforcement": enforcement,
        "hard_limits": limits,
    }
    sealed["quota_hash"] = _digest(sealed)
    return SealedArtifact("quota_envelope", _canonical_json(sealed))


def _sealed_payload(
    artifact: object, artifact_type: str, hash_field: str, code: str
) -> dict[str, Any]:
    if (
        not isinstance(artifact, SealedArtifact)
        or artifact.artifact_type != artifact_type
    ):
        _fail(code, f"a sealed {artifact_type} is required")
    payload = artifact.payload  # type: ignore[union-attr]
    if _hash_excluding(payload, hash_field) != payload[hash_field]:
        _fail(code, f"the sealed {artifact_type} does not match its own hash")
    return payload


def verify_isolation(
    repository_root: str | Path, holdout: Mapping[str, Any]
) -> tuple[str, ...]:
    """Confirm the holdout declares every pinned boundary as the schema does."""

    value = _mapping(holdout, "HoldoutManifest")
    manifest_fields = holdout_manifest_fields(repository_root)
    _exact_fields(value, manifest_fields, "HoldoutManifest")
    boundaries = isolation_boundaries(repository_root)
    unknown = sorted(set(boundaries) - manifest_fields)
    if unknown:
        _fail(
            "VOCABULARY_DRIFT",
            "the holdout schema pins a boundary this gate does not read",
            {"unknown": unknown},
        )
    for boundary in boundaries:
        if _boolean(value[boundary], boundary) is not False:
            _fail(
                Denial.ISOLATION_BREACH.value,
                f"{boundary} is pinned false by the holdout schema",
                {"boundary": boundary},
            )
    if (
        _boolean(
            value["unblinding_approval_required"],
            "unblinding_approval_required",
        )
        is not unblinding_requires_approval(repository_root)
    ):
        _fail(
            Denial.ISOLATION_BREACH.value,
            "unblinding_approval_required contradicts the holdout schema",
        )
    manifest_hash = _text(value["manifest_hash"], "manifest_hash")
    if (
        SHA256_PATTERN.fullmatch(manifest_hash) is None
        or _hash_excluding(value, "manifest_hash") != manifest_hash
    ):
        _fail(
            "HOLDOUT_UNSEALED",
            "manifest_hash does not match the canonical holdout fields",
        )
    for field in (
        "holdout_id",
        "evaluator_id",
        "split_strategy",
        "log_redaction_policy",
        "cache_isolation_policy",
    ):
        _text(value[field], field)
    for field in ("acl_policy_hash",):
        digest = _text(value[field], field)
        if SHA256_PATTERN.fullmatch(digest) is None:
            _fail("INPUT_INVALID", f"{field} must be a canonical SHA-256 digest")
    sealed_at = _timestamp(value["sealed_at"], "sealed_at")
    try:
        _instant(sealed_at)
    except ValueError:
        _fail("INPUT_INVALID", "sealed_at must be a real RFC3339 instant")
        raise  # pragma: no cover - _fail always raises
    for field in (
        "public_partition_refs",
        "adversarial_partition_handles",
        "hidden_partition_handles",
        "ood_partition_handles",
    ):
        entries = _string_tuple(value[field], field)
        if field == "hidden_partition_handles" and not entries:
            _fail("INPUT_INVALID", f"{field} must contain at least one entry")
    content_hashes = _string_tuple(value["content_hashes"], "content_hashes")
    if not content_hashes:
        _fail("INPUT_INVALID", "content_hashes must contain at least one entry")
    for index, digest in enumerate(content_hashes):
        if SHA256_PATTERN.fullmatch(digest) is None:
            _fail(
                "INPUT_INVALID",
                f"content_hashes[{index}] must be a canonical SHA-256 digest",
            )
    return boundaries


def unblinding_requires_approval(repository_root: str | Path) -> bool:
    """Whether the holdout contract pins unblinding behind an approval."""

    schema = _schema(repository_root, HOLDOUT_SCHEMA_PATH)
    properties = _mapping(schema.get("properties", {}), "holdout properties")
    node = properties.get("unblinding_approval_required")
    if not isinstance(node, Mapping) or "const" not in node:
        _fail("SCHEMA_UNREADABLE", "the holdout schema pins no unblinding rule")
    return bool(node["const"])  # type: ignore[index]


def _protected_handles(holdout: Mapping[str, Any]) -> frozenset[str]:
    handles = {str(holdout["evaluator_id"])}
    for field in (
        "adversarial_partition_handles",
        "hidden_partition_handles",
        "ood_partition_handles",
    ):
        handles.update(str(entry) for entry in holdout[field])
    return frozenset(handles)


def _validate_relative_path(value: object, label: str) -> str:
    text = _text(value, label)
    if "\\" in text or ":" in text or text.startswith("/") or text.startswith("~"):
        _fail(
            Denial.PATH_ESCAPE.value,
            f"{label} must be a portable forward-slash relative path",
            {"path": text},
        )
    for segment in text.split("/"):
        base = segment.split(".", 1)[0].rstrip(" .")
        if (
            not segment
            or segment in {".", ".."}
            or segment != segment.rstrip(" .")
            or _WINDOWS_RESERVED.fullmatch(base) is not None
        ):
            _fail(
                Denial.PATH_ESCAPE.value,
                f"{label} contains an unsafe component",
                {"path": text, "segment": segment},
            )
    return text


def _egress_origin(url: str) -> str:
    match = re.fullmatch(r"(https?)://([^/?#\\@\s]+)(/[^?#\s]*)?(\?[^#\s]*)?", url)
    if match is None:
        _fail(
            Denial.EGRESS_DENIED.value,
            "egress requires an absolute credential-free HTTP(S) URL",
            {"url": url},
        )
    scheme, authority = match.group(1), match.group(2)  # type: ignore[union-attr]
    if "@" in authority or not authority:
        _fail(
            Denial.EGRESS_DENIED.value,
            "egress URL credentials are denied",
            {"url": url},
        )
    return f"{scheme}://{authority.lower()}"


def _validate_lease(
    repository_root: str | Path,
    lease: Mapping[str, Any],
    now: str,
    policy_hash: str,
) -> dict[str, Any]:
    value = _mapping(lease, "CapabilityLease")
    _exact_fields(
        value,
        capability_lease_fields(repository_root),
        "CapabilityLease",
    )
    schema = _schema(repository_root, LEASE_SCHEMA_PATH)
    properties = _mapping(schema.get("properties", {}), "CapabilityLease properties")

    def property_schema(field: str) -> dict[str, Any]:
        return _mapping(properties.get(field), f"CapabilityLease.{field} schema")

    def bounded_identifier(field: str) -> str:
        node = property_schema(field)
        minimum = node.get("minLength")
        maximum = node.get("maxLength")
        if (
            not isinstance(minimum, int)
            or isinstance(minimum, bool)
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
        ):
            _fail("SCHEMA_UNREADABLE", f"CapabilityLease.{field} lacks length bounds")
        return _bounded_text(
            value[field],
            field,
            minimum=minimum,
            maximum=maximum,
            code=Denial.LEASE_INVALID.value,
        )

    def string_array(field: str) -> tuple[str, ...]:
        node = property_schema(field)
        entries = _string_tuple(value[field], field)
        minimum = node.get("minItems", 0)
        if not isinstance(minimum, int) or isinstance(minimum, bool):
            _fail("SCHEMA_UNREADABLE", f"CapabilityLease.{field} has invalid minItems")
        if len(entries) < minimum:
            _fail(
                Denial.LEASE_INVALID.value,
                f"{field} must contain at least {minimum} entries",
            )
        if node.get("uniqueItems") is not True:
            _fail("SCHEMA_UNREADABLE", f"CapabilityLease.{field} must require uniqueness")
        item = _mapping(node.get("items", {}), f"CapabilityLease.{field}.items")
        item_minimum = item.get("minLength", 1)
        item_maximum = item.get("maxLength")
        if not isinstance(item_minimum, int) or isinstance(item_minimum, bool):
            _fail("SCHEMA_UNREADABLE", f"CapabilityLease.{field} item bound is invalid")
        if item_maximum is not None and (
            not isinstance(item_maximum, int) or isinstance(item_maximum, bool)
        ):
            _fail("SCHEMA_UNREADABLE", f"CapabilityLease.{field} item bound is invalid")
        return tuple(
            _bounded_text(
                entry,
                f"{field}[{index}]",
                minimum=item_minimum,
                maximum=item_maximum,
                code=Denial.LEASE_INVALID.value,
            )
            for index, entry in enumerate(entries)
        )

    lease_id = bounded_identifier("lease_id")
    principal_id = bounded_identifier("principal_id")
    principal_type = _scalar_text(
        value["principal_type"],
        "principal_type",
        code=Denial.LEASE_INVALID.value,
    )
    if principal_type not in lease_principal_types(repository_root):
        _fail(
            Denial.LEASE_INVALID.value,
            "principal_type is not canonical",
            {"principal_type": principal_type},
        )
    capabilities = _utf16_sorted(string_array("capabilities"), "capabilities")
    resource_scopes = _utf16_sorted(string_array("resource_scopes"), "resource_scopes")
    approval_ids = _utf16_sorted(string_array("approval_ids"), "approval_ids")
    issued_at = _timestamp(value["issued_at"], "issued_at")
    expires_at = _timestamp(value["expires_at"], "expires_at")
    try:
        issued_instant = _instant(issued_at)
        expires_instant = _instant(expires_at)
        now_instant = _instant(now)
    except ValueError:
        _fail(Denial.LEASE_INVALID.value, "lease timestamps must be real instants")
        raise  # pragma: no cover - _fail always raises
    if issued_instant >= expires_instant:
        _fail(
            Denial.LEASE_INVALID.value,
            "a capability lease must expire strictly after issuance",
        )

    fencing_schema = property_schema("fencing_token")
    fencing_minimum = fencing_schema.get("minimum")
    fencing_token = value["fencing_token"]
    if (
        not isinstance(fencing_minimum, int)
        or isinstance(fencing_minimum, bool)
        or not isinstance(fencing_token, int)
        or isinstance(fencing_token, bool)
        or fencing_token < fencing_minimum
        or fencing_token > 9_007_199_254_740_991
    ):
        _fail(
            Denial.LEASE_INVALID.value,
            "fencing_token must be a positive safe integer",
        )

    policy_pattern = _pattern(
        repository_root,
        LEASE_SCHEMA_PATH,
        "properties",
        "policy_hash",
        "pattern",
    )
    lease_pattern = _pattern(
        repository_root,
        LEASE_SCHEMA_PATH,
        "properties",
        "lease_hash",
        "pattern",
    )
    lease_policy_hash = _scalar_text(
        value["policy_hash"],
        "policy_hash",
        code=Denial.LEASE_INVALID.value,
    )
    if policy_pattern.fullmatch(lease_policy_hash) is None:
        _fail(Denial.LEASE_INVALID.value, "policy_hash is not canonical")

    revoked = _boolean(value["revoked"], "revoked")
    revocation_reason = value["revocation_reason"]
    if revocation_reason is not None:
        revocation_reason = _scalar_text(
            revocation_reason,
            "revocation_reason",
            code=Denial.LEASE_INVALID.value,
        )
    if (revoked and revocation_reason is None) or (
        not revoked and revocation_reason is not None
    ):
        _fail(
            Denial.LEASE_INVALID.value,
            "revocation_reason must exist exactly when revoked is true",
        )
    lease_hash = _scalar_text(
        value["lease_hash"],
        "lease_hash",
        code=Denial.LEASE_INVALID.value,
    )
    if lease_pattern.fullmatch(lease_hash) is None:
        _fail(Denial.LEASE_INVALID.value, "lease_hash is not canonical")
    normalized_lease = {
        "approval_ids": list(approval_ids),
        "capabilities": list(capabilities),
        "expires_at": expires_at,
        "fencing_token": fencing_token,
        "issued_at": issued_at,
        "lease_id": lease_id,
        "policy_hash": lease_policy_hash,
        "principal_id": principal_id,
        "principal_type": principal_type,
        "resource_scopes": list(resource_scopes),
        "revocation_reason": revocation_reason,
        "revoked": revoked,
    }
    expected_lease_hash = _digest(normalized_lease)
    if lease_hash != expected_lease_hash:
        _fail(
            Denial.LEASE_UNSEALED.value,
            "lease_hash does not match the canonical lease fields",
            {"actual": lease_hash, "expected": expected_lease_hash},
        )
    expected_policy_hash = _text(policy_hash, "policy_hash")
    if policy_pattern.fullmatch(expected_policy_hash) is None:
        _fail("INPUT_INVALID", "the current policy_hash is not canonical")
    if lease_policy_hash != expected_policy_hash:
        _fail(
            Denial.POLICY_UNPINNED.value,
            "the lease was issued under a different policy",
            {
                "current_policy_hash": expected_policy_hash,
                "lease_policy_hash": lease_policy_hash,
            },
        )
    if revoked:
        _fail(
            Denial.LEASE_REVOKED.value, f"{lease_id} is revoked", {"lease_id": lease_id}
        )
    if now_instant < issued_instant:
        _fail(
            Denial.LEASE_NOT_YET_VALID.value,
            f"{lease_id} is not yet valid",
            {"issued_at": issued_at, "now": now},
        )
    if now_instant >= expires_instant:
        _fail(
            Denial.LEASE_EXPIRED.value,
            f"{lease_id} expired before the invocation",
            {"expires_at": expires_at, "now": now},
        )
    return {
        "approval_ids": approval_ids,
        "capabilities": capabilities,
        "expires_at": expires_at,
        "fencing_token": fencing_token,
        "issued_at": issued_at,
        "lease_hash": lease_hash,
        "lease_id": lease_id,
        "policy_hash": lease_policy_hash,
        "principal_id": principal_id,
        "principal_type": principal_type,
        "resource_scopes": resource_scopes,
    }


def authorize_invocation(
    repository_root: str | Path,
    *,
    adapter: object,
    lease: Mapping[str, Any],
    holdout: Mapping[str, Any],
    request: Mapping[str, Any],
    now: str,
    policy_hash: str,
    scope_fencing_heads: Mapping[str, Any],
) -> SandboxDecision:
    """Admit one invocation against an injected current policy/fence snapshot.

    T04 validates and binds that snapshot; it does not issue policy or lease
    authority.  The effect owner must source these values from E03 and repeat
    the authoritative lease/fence check at the atomic effect boundary.
    """

    manifest = _sealed_payload(
        adapter, "tool_adapter", "adapter_hash", Denial.ADAPTER_UNSEALED.value
    )
    verified = verify_isolation(repository_root, holdout)
    protected = _protected_handles(holdout)
    granted = _validate_lease(
        repository_root,
        lease,
        _timestamp(now, "now"),
        policy_hash,
    )
    supplied_heads = _mapping(scope_fencing_heads, "scope_fencing_heads")

    value = _mapping(request, "InvocationRequest")
    _exact_fields(value, _REQUEST_FIELDS, "InvocationRequest")
    principal_id = _text(value["principal_id"], "principal_id")
    principal_type = _text(value["principal_type"], "principal_type")
    if (
        principal_id != granted["principal_id"]
        or principal_type != granted["principal_type"]
    ):
        _fail(
            Denial.LEASE_SCOPE_DENIED.value,
            "the request principal is not the one the lease was issued to",
            {
                "lease_principal": granted["principal_id"],
                "request_principal": principal_id,
            },
        )

    required = tuple(manifest["capability_requirements"])
    missing_from_lease = sorted(set(required) - set(granted["capabilities"]))
    if missing_from_lease:
        _fail(
            Denial.LEASE_INSUFFICIENT.value,
            "the lease does not grant every capability the adapter requires",
            {"missing": missing_from_lease},
        )
    requested = _string_tuple(value["capabilities"], "capabilities")
    if not requested:
        _fail(
            Denial.CAPABILITY_UNDECLARED.value,
            "an invocation must name the capabilities it uses",
        )
    undeclared = sorted(set(requested) - set(required))
    if undeclared:
        _fail(
            Denial.CAPABILITY_UNDECLARED.value,
            "the request asks for a capability the adapter never declared",
            {"undeclared": undeclared},
        )

    data_class = _text(value["data_class"], "data_class")
    if data_class not in manifest["allowed_data_classes"]:
        _fail(
            Denial.DATA_CLASS_DENIED.value,
            "the adapter is not allowed to touch this data class",
            {"allowed": manifest["allowed_data_classes"], "data_class": data_class},
        )

    approvals = _string_tuple(value["approval_record_ids"], "approval_record_ids")
    unleased = sorted(set(approvals) - set(granted["approval_ids"]))
    if unleased:
        _fail(
            Denial.APPROVAL_UNLEASED.value,
            "an approval the lease does not carry cannot authorize this invocation",
            {"unleased": unleased},
        )
    gated = APPROVAL_RULE[str(manifest["approval_policy"])]
    if manifest["safety_class"] in gated and not approvals:
        _fail(
            Denial.APPROVAL_MISSING.value,
            "this safety class requires an approval record",
            {
                "approval_policy": manifest["approval_policy"],
                "safety_class": manifest["safety_class"],
            },
        )

    roots: list[str] = []
    for index, entry in enumerate(_sequence(value["paths"], "paths")):
        item = _mapping(entry, f"paths[{index}]")
        _exact_fields(item, _PATH_FIELDS, f"paths[{index}]")
        root_id = _text(item["root_id"], "root_id")
        _text(item["operation"], "operation")
        _validate_relative_path(item["relative_path"], f"paths[{index}].relative_path")
        if root_id in protected:
            if principal_type in SANDBOXED_PRINCIPAL_TYPES:
                _fail(
                    Denial.ISOLATION_BREACH.value,
                    "a sandboxed principal cannot reach an evaluator or holdout partition",
                    {"principal_type": principal_type, "root_id": root_id},
                )
            if unblinding_requires_approval(repository_root) and not approvals:
                _fail(
                    Denial.APPROVAL_MISSING.value,
                    "unblinding a holdout partition requires an approval record",
                    {"root_id": root_id},
                )
        if root_id not in granted["resource_scopes"]:
            _fail(
                Denial.LEASE_SCOPE_DENIED.value,
                "the lease does not scope this resource root",
                {"root_id": root_id},
            )
        roots.append(root_id)

    touched_roots = tuple(sorted(set(roots)))
    missing_heads = sorted(set(touched_roots) - set(supplied_heads))
    unknown_heads = sorted(set(supplied_heads) - set(touched_roots))
    if missing_heads or unknown_heads:
        _fail(
            Denial.STALE_FENCING_TOKEN.value,
            "the fencing-head snapshot must exactly cover every touched root",
            {"missing": missing_heads, "unknown": unknown_heads},
        )
    checked_heads: list[tuple[str, int]] = []
    for root_id in touched_roots:
        head = supplied_heads[root_id]
        if (
            not isinstance(head, int)
            or isinstance(head, bool)
            or head < 1
            or head > 9_007_199_254_740_991
        ):
            _fail(
                "INPUT_INVALID",
                f"scope_fencing_heads.{root_id} must be a positive safe integer",
            )
        if head != granted["fencing_token"]:
            _fail(
                Denial.STALE_FENCING_TOKEN.value,
                "the lease no longer owns the touched root",
                {
                    "fencing_head": head,
                    "lease_fencing_token": granted["fencing_token"],
                    "root_id": root_id,
                },
            )
        checked_heads.append((root_id, head))
    scope_fencing_heads_hash = _digest(dict(checked_heads))

    network_policy = str(manifest["network_policy"])
    rule = NETWORK_POLICY_RULE[network_policy]
    url = value["network_url"]
    origin: str | None = None
    if url is not None:
        origin = _egress_origin(_text(url, "network_url"))
        if rule == "NO_EGRESS":
            _fail(
                Denial.EGRESS_DENIED.value,
                "the adapter declares no network access",
                {"network_policy": network_policy},
            )
        if rule == "APPROVAL_REQUIRED" and not approvals:
            _fail(
                Denial.APPROVAL_MISSING.value,
                "unrestricted egress requires an approval record",
                {"network_policy": network_policy},
            )
        if origin in protected or _egress_host(origin) in protected:
            _fail(
                Denial.ISOLATION_BREACH.value,
                "egress may not reach an evaluator or holdout destination",
                {"origin": origin},
            )

    return SandboxDecision(
        adapter_id=str(manifest["adapter_id"]),
        sandbox_profile=str(manifest["sandbox_profile"]),
        network_policy=network_policy,
        safety_class=str(manifest["safety_class"]),
        data_class=data_class,
        granted_capabilities=tuple(sorted(requested)),
        granted_roots=touched_roots,
        egress_origin=origin,
        isolation_verified=verified,
        lease_id=str(granted["lease_id"]),
        lease_hash=str(granted["lease_hash"]),
        lease_policy_hash=str(granted["policy_hash"]),
        lease_fencing_token=int(granted["fencing_token"]),
        scope_fencing_heads=tuple(checked_heads),
        scope_fencing_heads_hash=scope_fencing_heads_hash,
    )


def _egress_host(origin: str) -> str:
    return origin.split("://", 1)[1]


def open_ledger(
    repository_root: str | Path, *, adapter: object, budget: object
) -> QuotaLedger:
    """Open a bounded ledger, refusing anything the exit criterion cannot bound."""

    manifest = _sealed_payload(
        adapter, "tool_adapter", "adapter_hash", Denial.ADAPTER_UNSEALED.value
    )
    envelope = _sealed_payload(
        budget, "quota_envelope", "quota_hash", "ENVELOPE_UNSEALED"
    )
    dimensions = quota_dimensions(repository_root)

    enforcement = str(envelope["enforcement"])
    _assert_table(
        ENFORCEMENT_STRENGTH, enforcement_modes(repository_root), "enforcement strength"
    )
    _assert_table(
        SAFETY_CLASS_METERING, safety_classes(repository_root), "safety class metering"
    )
    required_mode = SAFETY_CLASS_METERING[str(manifest["safety_class"])]
    if ENFORCEMENT_STRENGTH[enforcement] < ENFORCEMENT_STRENGTH[required_mode]:
        _fail(
            Denial.QUOTA_UNBOUNDED.value,
            "the envelope meters more weakly than this safety class allows",
            {
                "declared": enforcement,
                "required": required_mode,
                "safety_class": manifest["safety_class"],
            },
        )

    limits = {key: envelope["hard_limits"][key] for key in dimensions}
    mandatory = list(REQUIRED_BOUNDED_DIMENSIONS)
    if NETWORK_POLICY_RULE[str(manifest["network_policy"])] != "NO_EGRESS":
        mandatory.extend(EGRESS_BOUNDED_DIMENSIONS)
    unbounded = sorted(name for name in mandatory if limits[name] is None)
    if unbounded:
        _fail(
            Denial.QUOTA_UNBOUNDED.value,
            "an invocation must run under a call and wall-clock ceiling",
            {"unbounded": unbounded},
        )

    return QuotaLedger(
        budget_id=str(envelope["budget_id"]),
        enforcement=enforcement,
        breach_policy=str(envelope["breach_policy"]),
        limits=dict(limits),
        consumed=dict.fromkeys(dimensions, 0),
    )


def consume(
    repository_root: str | Path, ledger: QuotaLedger, dimension: str, amount: int
) -> QuotaOutcome:
    """Charge one dimension; a breach resolves through the envelope's policy."""

    dimensions = quota_dimensions(repository_root)
    _assert_table(BREACH_ACTION, breach_policies(repository_root), "breach action")
    if dimension not in dimensions:
        _fail(
            "DIMENSION_UNKNOWN",
            "a quota dimension must be one the budget schema declares",
            {"allowed": list(dimensions), "dimension": dimension},
        )
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        _fail("INPUT_INVALID", "a consumption amount must be a non-negative integer")

    limit = ledger.limits[dimension]
    requested = ledger.consumed[dimension] + amount
    action = BREACH_ACTION[ledger.breach_policy]
    if limit is None or requested <= limit:
        consumed = dict(ledger.consumed)
        consumed[dimension] = requested
        return QuotaOutcome(
            QuotaLedger(
                ledger.budget_id,
                ledger.enforcement,
                ledger.breach_policy,
                ledger.limits,
                consumed,
            ),
            None,
        )

    breach = {
        "action": action,
        "code": Denial.QUOTA_EXHAUSTED.value,
        "dimension": dimension,
        "limit": limit,
        "policy": ledger.breach_policy,
        "requested": requested,
    }
    consumed = dict(ledger.consumed)
    consumed[dimension] = ledger.consumed[dimension] if action == "DENIED" else limit
    return QuotaOutcome(
        QuotaLedger(
            ledger.budget_id,
            ledger.enforcement,
            ledger.breach_policy,
            ledger.limits,
            consumed,
        ),
        breach,
    )


def remaining(ledger: QuotaLedger, dimension: str) -> int | None:
    limit = ledger.limits.get(dimension)
    if limit is None:
        return None
    return max(0, limit - ledger.consumed[dimension])


def evaluate_deadline(ledger: QuotaLedger, elapsed_seconds: int) -> dict[str, Any]:
    """A wall-clock ceiling is mandatory, so this always has a verdict."""

    if not isinstance(elapsed_seconds, int) or isinstance(elapsed_seconds, bool):
        _fail("INPUT_INVALID", "elapsed_seconds must be an integer")
    if elapsed_seconds < 0:
        _fail("INPUT_INVALID", "elapsed_seconds must not be negative")
    limit = ledger.limits["wall_seconds"]
    if limit is None:  # pragma: no cover - open_ledger refuses an unbounded deadline
        _fail(Denial.QUOTA_UNBOUNDED.value, "the ledger carries no wall-clock ceiling")
    exceeded = elapsed_seconds > int(limit)  # type: ignore[arg-type]
    return {
        "code": Denial.DEADLINE_EXCEEDED.value if exceeded else None,
        "elapsed_seconds": elapsed_seconds,
        "exceeded": exceeded,
        "wall_seconds": limit,
    }


def seal_tool_output(
    repository_root: str | Path,
    *,
    receipt_id: str,
    artifact_id: str,
    intent_id: str | None,
    actor_id: str,
    actor_type: str,
    media_type: str,
    payload: bytes,
    truncated: bool,
    locator: str,
    created_at: str,
) -> dict[str, Any]:
    """Content-address exactly the bytes that were captured.

    Truncation is a validation result, not a separate field: the receipt keeps
    the ArtifactReceipt shape, and a partial capture is hashed as what was
    actually captured with its completeness check recorded FAIL.
    """

    if not isinstance(payload, (bytes, bytearray)):
        _fail("OUTPUT_UNHASHED", "a tool output must be captured as bytes")
    statuses = artifact_check_statuses(repository_root)
    for required in ("PASS", "FAIL"):
        if required not in statuses:
            _fail(
                "VOCABULARY_DRIFT",
                f"the artifact receipt schema declares no {required} status",
            )
    captured = bytes(payload)
    complete = not _boolean(truncated, "truncated")
    receipt = {
        "action_intent_id": None
        if intent_id is None
        else _text(intent_id, "intent_id"),
        "artifact_id": _text(artifact_id, "artifact_id"),
        "byte_size": len(captured),
        "content_hash": "sha256:" + hashlib.sha256(captured).hexdigest(),
        "created_at": _timestamp(created_at, "created_at"),
        "created_by": {
            "actor_id": _text(actor_id, "actor_id"),
            "actor_type": _text(actor_type, "actor_type"),
        },
        "locator": _text(locator, "locator"),
        "media_type": _text(media_type, "media_type"),
        "receipt_id": _text(receipt_id, "receipt_id"),
        "schema_ref": None,
        "validation_results": [
            {
                "check": "content_hash",
                "details": "hashed the captured bytes",
                "status": "PASS",
            },
            {
                "check": "capture_completeness",
                "details": (
                    "the adapter returned the whole output"
                    if complete
                    else "the capture was truncated; the hash covers the captured bytes"
                ),
                "status": "PASS" if complete else "FAIL",
            },
        ],
    }
    receipt["receipt_hash"] = _digest(receipt)
    return receipt


def verify_tool_output(receipt: Mapping[str, Any], payload: bytes) -> dict[str, Any]:
    """Re-derive the hash from the bytes; a declared digest proves nothing."""

    value = _mapping(receipt, "ArtifactReceipt")
    receipt_hash = _text(value.get("receipt_hash"), "receipt_hash")
    if _hash_excluding(value, "receipt_hash") != receipt_hash:
        _fail(
            "RECEIPT_HASH_MISMATCH", "the output receipt does not match its own content"
        )
    captured = bytes(payload)
    expected = "sha256:" + hashlib.sha256(captured).hexdigest()
    if value["content_hash"] != expected:
        _fail(
            "OUTPUT_HASH_MISMATCH",
            "the declared content hash is not the hash of these bytes",
            {"declared": value["content_hash"], "derived": expected},
        )
    if value["byte_size"] != len(captured):
        _fail(
            "OUTPUT_SIZE_MISMATCH",
            "the declared byte size is not the size of these bytes",
            {"declared": value["byte_size"], "derived": len(captured)},
        )
    return dict(value)


def reconcile_invocation(
    repository_root: str | Path,
    *,
    observation: str,
    stop_reason: str | None,
) -> dict[str, Any]:
    """Map what was observed onto the canonical effect status."""

    declared = effect_statuses(repository_root)
    mapped = {status for status, _ in OBSERVATION_STATUS.values()}
    drift = sorted(set(declared) ^ mapped)
    if drift:
        _fail(
            "VOCABULARY_DRIFT",
            "the observation table no longer covers the effect status vocabulary",
            {"unmatched": drift},
        )
    if observation not in OBSERVATION_STATUS:
        _fail(
            "OBSERVATION_INVALID",
            "an outcome must be an observation this gate can make",
            {"allowed": list(OBSERVATIONS), "observation": observation},
        )
    if stop_reason is not None and stop_reason not in DENIALS:
        _fail(
            "STOP_REASON_INVALID",
            "a stop reason must be a typed denial",
            {"allowed": list(DENIALS), "stop_reason": stop_reason},
        )
    if stop_reason is not None and observation == Observation.COMPLETED.value:
        _fail(
            "OBSERVATION_INCONSISTENT",
            "a stopped invocation cannot also have completed",
            {"stop_reason": stop_reason},
        )
    status, reconciliation_required = OBSERVATION_STATUS[observation]
    return {
        "observation": observation,
        "reconciliation_required": reconciliation_required,
        "status": status,
        "stop_reason": stop_reason,
    }


def build_effect_receipt(
    repository_root: str | Path,
    *,
    receipt_id: str,
    intent_id: str,
    run_id: str,
    idempotency_key: str,
    external_operation_id: str | None,
    outcome: Mapping[str, Any],
    output_receipts: Sequence[Mapping[str, Any]],
    error_artifact_ids: Sequence[str],
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    """Emit the receipt an invocation owes, whatever happened to it.

    The receipt keeps the canonical EffectReceipt shape.  The observation and
    the stop reason that produced its status stay in the outcome the caller
    already holds, so nothing this gate infers is smuggled onto the wire.
    """

    resolved = _mapping(outcome, "outcome")
    _exact_fields(
        resolved,
        frozenset({"observation", "reconciliation_required", "status", "stop_reason"}),
        "outcome",
    )
    status = _text(resolved["status"], "status")
    if status not in effect_statuses(repository_root):
        _fail(
            "STATUS_INVALID", "an effect status must be canonical", {"status": status}
        )

    results: list[str] = []
    for index, entry in enumerate(_sequence(output_receipts, "output_receipts")):
        item = _mapping(entry, f"output_receipts[{index}]")
        content_hash = _text(item.get("content_hash"), "content_hash")
        if SHA256_PATTERN.fullmatch(content_hash) is None:
            _fail(
                "OUTPUT_UNHASHED",
                "an output must carry a sha256 content hash to become evidence",
                {"artifact_id": item.get("artifact_id")},
            )
        receipt_hash = _text(item.get("receipt_hash"), "receipt_hash")
        if _hash_excluding(item, "receipt_hash") != receipt_hash:
            _fail(
                "RECEIPT_HASH_MISMATCH",
                "an output receipt does not match its own content",
                {"artifact_id": item.get("artifact_id")},
            )
        results.append(_text(item.get("artifact_id"), "artifact_id"))
    if len(set(results)) != len(results):
        _fail("INPUT_INVALID", "output receipts must not repeat an artifact id")

    errors = _string_tuple(error_artifact_ids, "error_artifact_ids")
    if status == "SUCCEEDED" and not results:
        _fail(
            "RESULT_UNRECORDED",
            "a successful invocation must record at least one hashed output",
        )
    if status == "FAILED" and not errors:
        _fail("ERROR_UNRECORDED", "a failed invocation must record why it failed")
    if status == "NOT_EXECUTED" and (
        results or errors or external_operation_id is not None
    ):
        _fail(
            "OBSERVATION_INCONSISTENT",
            "an invocation that never started has no external effect to record",
        )
    if status == "UNKNOWN" and not resolved["reconciliation_required"]:
        _fail(
            "RECONCILIATION_MISSING",
            "an interrupted invocation must be reconciled, not assumed",
        )

    receipt = {
        "error_artifact_ids": sorted(errors),
        "external_operation_id": (
            None
            if external_operation_id is None
            else _text(external_operation_id, "external_operation_id")
        ),
        "finished_at": _timestamp(finished_at, "finished_at"),
        "idempotency_key": _text(idempotency_key, "idempotency_key"),
        "intent_id": _text(intent_id, "intent_id"),
        "observed_state_hash": None if not results else _digest(sorted(results)),
        "receipt_id": _text(receipt_id, "receipt_id"),
        "reconciliation_required": _boolean(
            resolved["reconciliation_required"], "reconciliation_required"
        ),
        "result_artifact_ids": sorted(results),
        "run_id": _text(run_id, "run_id"),
        "started_at": _timestamp(started_at, "started_at"),
        "status": status,
    }
    if _instant(receipt["finished_at"]) < _instant(receipt["started_at"]):
        _fail("INPUT_INVALID", "an invocation cannot finish before it started")
    receipt["receipt_hash"] = _hash_excluding(receipt, "receipt_hash")
    return receipt


def evaluate_tool_gate(
    repository_root: str | Path,
    *,
    decision: SandboxDecision,
    ledger: QuotaLedger,
    deadline: Mapping[str, Any],
    output_receipts: Sequence[Mapping[str, Any]],
    effect_receipt: Mapping[str, Any],
    declared_status: str,
) -> dict[str, Any]:
    """Derive the T-phase verdict; a declared status above it is an overclaim."""

    if not isinstance(decision, SandboxDecision):
        _fail("INPUT_INVALID", "the gate requires an issued sandbox decision")
    if not isinstance(ledger, QuotaLedger):
        _fail("INPUT_INVALID", "the gate requires an opened quota ledger")
    if declared_status not in GATE_LADDER:
        _fail(
            "INPUT_INVALID",
            "a declared gate status must be canonical",
            {"allowed": list(GATE_LADDER), "declared": declared_status},
        )

    receipt = _mapping(effect_receipt, "EffectReceipt")
    receipt_hash = _text(receipt.get("receipt_hash"), "receipt_hash")
    if _hash_excluding(receipt, "receipt_hash") != receipt_hash:
        _fail(
            "RECEIPT_HASH_MISMATCH", "the effect receipt does not match its own content"
        )

    outputs = [
        _mapping(entry, "output receipt")
        for entry in _sequence(output_receipts, "output_receipts")
    ]
    hashed = all(
        isinstance(entry.get("content_hash"), str)
        and SHA256_PATTERN.fullmatch(str(entry["content_hash"])) is not None
        and _hash_excluding(entry, "receipt_hash") == entry.get("receipt_hash")
        for entry in outputs
    )
    recorded = set(receipt["result_artifact_ids"])
    if recorded != {str(entry.get("artifact_id")) for entry in outputs}:
        hashed = False

    verdict = _mapping(deadline, "deadline")
    _exact_fields(
        verdict,
        frozenset({"code", "elapsed_seconds", "exceeded", "wall_seconds"}),
        "deadline",
    )
    status = str(receipt["status"])
    reconciliation_required = _boolean(
        receipt["reconciliation_required"], "reconciliation_required"
    )
    reconciled = status != "UNKNOWN" and not reconciliation_required
    if verdict["exceeded"] and status == "SUCCEEDED":
        reconciled = False

    checks = {
        "capabilities_declared": bool(decision.granted_capabilities),
        "deadline_enforced": ledger.limits["wall_seconds"] is not None
        and not verdict["exceeded"],
        "effects_reconciled": reconciled,
        "isolation_verified": bool(decision.isolation_verified),
        "lease_bound": SHA256_PATTERN.fullmatch(decision.lease_hash) is not None
        and SHA256_PATTERN.fullmatch(decision.lease_policy_hash) is not None
        and decision.lease_fencing_token > 0
        and decision.scope_fencing_heads_hash
        == _digest(dict(decision.scope_fencing_heads)),
        "outputs_hashed": hashed,
        "quotas_bounded": all(
            ledger.limits[name] is not None for name in REQUIRED_BOUNDED_DIMENSIONS
        ),
    }
    missing = sorted(set(GATE_CRITERIA) - set(checks))
    if missing:  # pragma: no cover - construction invariant
        _fail(
            "GATE_INCOMPLETE",
            "a gate criterion was not evaluated",
            {"missing": missing},
        )

    failed = sorted(name for name, passed in checks.items() if not passed)
    if not failed:
        derived = GateStatus.PASS.value
    elif failed == ["deadline_enforced"] and reconciled:
        derived = GateStatus.CONDITIONAL.value
    else:
        derived = GateStatus.FAIL.value
    if GATE_LADDER.index(declared_status) > GATE_LADDER.index(derived):
        _fail(
            "GATE_OVERCLAIM",
            "the declared gate status is stronger than the checks support",
            {"declared": declared_status, "derived": derived, "failed": failed},
        )

    report = {
        "adapter_id": decision.adapter_id,
        "budget_id": ledger.budget_id,
        "checks": {name: checks[name] for name in sorted(checks)},
        "declared_status": declared_status,
        "effect_status": status,
        "failed_criteria": failed,
        "fencing_token": decision.lease_fencing_token,
        "isolation_verified": list(decision.isolation_verified),
        "lease_hash": decision.lease_hash,
        "lease_id": decision.lease_id,
        "policy_hash": decision.lease_policy_hash,
        "sandbox_profile": decision.sandbox_profile,
        "scope_fencing_heads": dict(decision.scope_fencing_heads),
        "scope_fencing_heads_hash": decision.scope_fencing_heads_hash,
        "status": derived,
    }
    report["report_hash"] = _digest(report)
    return report
