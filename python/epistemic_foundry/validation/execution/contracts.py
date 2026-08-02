"""V03 deterministic capability-controlled validation execution and receipts.

A validation run is the one moment where this system stops reasoning about a
hypothesis and does something.  That moment is the whole risk, so V03 owns the
narrow band around it: what has to be true *before* the first byte of a target
runs, what has to be recorded *while* it runs, and what the run is allowed to
claim *after* it stops.  Nothing here decides whether the run's result supports
a hypothesis; that is V04's question and it is deliberately not answerable from
this module.

The boundary against T04 matters and is drawn on purpose.  T04's sandbox gate
adjudicates whether an adapter *may* be admitted at all — network policy, data
classes, egress origins, evaluator and holdout isolation, quota envelopes.  V03
does not re-adjudicate any of that and cannot overturn it.  V03 requires
*proof* that such a decision was reached and then checks the three things that
are only knowable at execution time and would still be true even if the static
gate were perfect: that the intent about to run is byte-for-byte the intent
that was approved, that the lease authorizing it is still live and still the
current holder of every scope it will write, and that what actually happened
was captured completely enough for someone else to re-derive it.

Three refusals carry the exit criteria.

*Nothing runs unverified.*  An ``ActionIntent`` publishes an ``intent_hash``
over exactly its other fields and an ``arguments_hash`` over the argument
document it names.  Both are recomputed here before authorization, so an intent
edited after approval — a different target, a wider capability, a changed seed
— fails to match and the run is denied rather than started.  The derivation is
the canonical one E02 already uses, so a receipt this module emits and a
receipt the kernel emits hash the same way.

*Nothing runs unfenced.*  A lease is checked against the run's own start
instant, not against a wall clock this module does not have: expired at start,
not yet valid at start, revoked, edited after issue, missing a capability the
intent requires, missing a scope the run will write, or superseded for some
scope by a newer fencing token all deny execution.  A human principal is
refused outright,
because a lease held by a person cannot be fenced by a token and a validation
run has to be attributable to something a fencing counter can supersede.

*Nothing is recorded partially.*  The reproducibility contract the target
declares is read from the same canonical schema V01 constructs it under, and it
is enforced as an obligation on the run record: a target whose contract sets
``seed_control`` must record every seed as a named integer stream, one that
sets ``container_digest_required`` must pin the image by canonical digest, and
one that sets ``environment_capture`` must carry a non-empty capture.  All four
capture channels — stdout, stderr, exit status and resource usage — must be
present and content-addressed, with resource usage covering every dimension the
canonical budget envelope meters, so "we didn't record that" is not reachable.

Effect status is derived from what was observed, never asserted.  A run the
runner reports as succeeded must carry exit code zero; one reported as failed
must not; one that never started must carry no exit code at all.  A cancelled,
timed-out or interrupted run resolves to ``UNKNOWN`` and carries
``reconciliation_required``, because an interrupted external effect is not the
same as an effect that never happened.  Expected and observed effects reconcile
by exact set arithmetic — matched plus missing equals expected, matched plus
unexpected equals observed — and any unexpected effect raises an incident that
a green exit code cannot suppress.

No clock and no randomness.  Every id, timestamp, seed and token is supplied by
the caller, inputs are never mutated, every derived list is sorted, and every
record re-derives its own hash from exactly the fields it publishes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator

#: The exact-hash authorization a validation invocation runs under.
ACTION_INTENT_SCHEMA_PATH: Final = "schemas/action-intent.schema.json"
#: The fenced grant that says this principal may run it right now.
LEASE_SCHEMA_PATH: Final = "schemas/capability-lease.schema.json"
#: The immutable record of what the run actually did.
EFFECT_SCHEMA_PATH: Final = "schemas/effect-receipt.schema.json"
#: The content-addressed shape every captured stream is sealed into.
ARTIFACT_SCHEMA_PATH: Final = "schemas/artifact-receipt.schema.json"
#: Where the reproducibility contract and network policy vocabularies live.
TARGET_SCHEMA_PATH: Final = "schemas/validation-target-manifest.schema.json"
#: The metered dimensions a run has to report usage for.
BUDGET_SCHEMA_PATH: Final = "schemas/budget-envelope.schema.json"

#: RFC3339 instants.  ``format`` is annotation-only under Draft 2020-12, so the
#: shape a run's ordering arithmetic depends on is checked here explicitly.
RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
#: A lease scope ending in this suffix covers everything beneath its prefix.
SCOPE_WILDCARD: Final = "/**"

#: Every way this module refuses an input outright, and why that refusal is
#: not something a caller could reasonably be asked to work around.
FINDING_CODES: dict[str, str] = {
    "ARTIFACTS_UNPINNED": (
        "the run records no artifact hash for the target it executed, so the "
        "code that actually ran cannot be tied to any reviewed version"
    ),
    "CANONICALIZATION_FAILED": (
        "a value cannot be encoded as canonical JSON, so no stable digest of "
        "it exists and nothing derived from it could be replayed"
    ),
    "CAPTURE_INCOMPLETE": (
        "a run capture omits a channel this contract requires, so some part of "
        "what the run did was never recorded and cannot be reviewed later"
    ),
    "CONTAINER_UNPINNED": (
        "the target's reproducibility contract requires a pinned image but the "
        "run records no canonical container digest, so the environment it ran "
        "in cannot be reconstructed"
    ),
    "EFFECT_ID_DUPLICATED": (
        "an effect id appears more than once in one set, so the reconciliation "
        "counts could not attribute an outcome to one effect unambiguously"
    ),
    "ENVIRONMENT_UNCAPTURED": (
        "the target's reproducibility contract requires environment capture "
        "but the run records none, so no later run could be shown comparable"
    ),
    "FIELD_SET_INVALID": (
        "a record carries a field set the declaring schema does not allow, so "
        "some field is missing or some field would be silently ignored"
    ),
    "IDEMPOTENCY_KEY_MISMATCH": (
        "the receipt claims a different idempotency key than the intent it "
        "reports on, so a retry could not be recognised as the same effect"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this contract accepts, so continuing would "
        "mean guessing what the caller meant instead of refusing plainly"
    ),
    "INTENT_SCHEMA_INVALID": (
        "the assembled ActionIntent does not validate against its canonical "
        "schema, so this builder would be emitting a document nothing accepts"
    ),
    "RECEIPT_HASH_MISMATCH": (
        "a receipt does not re-derive the hash it publishes, so it was edited "
        "after sealing and nothing downstream may rest on it"
    ),
    "RECEIPT_SCHEMA_INVALID": (
        "the assembled receipt does not validate against its canonical schema, "
        "so this builder would be emitting a document nothing accepts"
    ),
    "RESOURCE_USAGE_INCOMPLETE": (
        "the run reports no usage for a dimension the canonical budget "
        "envelope meters, so a quota breach could not be reconstructed"
    ),
    "SCHEMA_UNREADABLE": (
        "a canonical schema this module reads its vocabulary from cannot be "
        "read or does not declare what is expected, so nothing may be sealed"
    ),
    "SEEDS_UNRECORDED": (
        "the target's reproducibility contract requires seed control but the "
        "run records no named integer seed, so its draw cannot be repeated"
    ),
    "STATUS_UNOBSERVED": (
        "the reported observation contradicts the exit status actually seen, "
        "so the receipt would claim an outcome nothing in the run supports"
    ),
    "TIMESTAMP_DISORDERED": (
        "a run finishes before it starts, so no duration, ordering or lease "
        "validity question about it could be answered"
    ),
    "VOCABULARY_DRIFT": (
        "a local decision table no longer matches the canonical schema that "
        "declares its keys, so some sealed value has no governing rule"
    ),
}

#: Every way authorization is refused.  These are *reported*, not raised: a
#: caller repairing a denied run needs the whole ledger, not the first stop.
DENIAL_CODES: dict[str, str] = {
    "APPROVAL_MISSING": (
        "the intent's risk class requires an approval record and it names "
        "none, so a consequential effect would run with no human decision "
        "anywhere in front of it"
    ),
    "APPROVAL_UNLEASED": (
        "the intent names an approval the lease does not carry, so the grant "
        "actually authorizing the run is not the one that was approved"
    ),
    "ARGUMENTS_HASH_MISMATCH": (
        "the argument document does not hash to what the intent declares, so "
        "the run would execute against inputs nobody approved"
    ),
    "CAPABILITY_UNLEASED": (
        "the intent requires a capability the lease does not grant, so the run "
        "would reach past what its principal was actually given"
    ),
    "ENVIRONMENT_UNBOUND": (
        "the run environment does not re-derive its hash or belongs to another "
        "run, so what was recorded is not what would execute"
    ),
    "INTENT_HASH_MISMATCH": (
        "the intent does not re-derive the hash it publishes, so it was edited "
        "after approval and is no longer the action that was authorized"
    ),
    "LEASE_EXPIRED": (
        "the lease has passed its expiry at the run's own start instant, so "
        "the attempt is orphaned and requires reconciliation, not execution"
    ),
    "LEASE_NOT_YET_VALID": (
        "the lease has not reached its issued_at boundary at the run's start "
        "instant, so nothing has been granted yet"
    ),
    "LEASE_REVOKED": (
        "the lease was revoked, so the grant it represents no longer exists "
        "however recently it was issued"
    ),
    "LEASE_UNSEALED": (
        "the lease does not re-derive the hash it publishes, so it was edited "
        "after issue and is no longer the grant that was actually made"
    ),
    "POLICY_UNPINNED": (
        "the lease was issued under a different policy bundle than the run "
        "declares, so the rules it was granted under are not the rules in "
        "force"
    ),
    "PRINCIPAL_UNFENCEABLE": (
        "the lease is held by a human principal, which no fencing counter can "
        "supersede, so a stale run could not be cut off"
    ),
    "SCOPE_UNLEASED": (
        "the run would write a scope the lease does not cover, so an effect "
        "would land somewhere the grant never reached"
    ),
    "STALE_FENCING_TOKEN": (
        "a newer fencing token was issued for a scope this run writes, so this "
        "lease is no longer the current holder and a split-brain write is live"
    ),
}

#: What a runner reports having observed, and the canonical effect status each
#: observation resolves to.  Values are asserted to cover the schema's status
#: enum exactly, so no status is unreachable and none is invented here.
OBSERVATION_STATUS: Final = {
    "cancelled": "UNKNOWN",
    "failed": "FAILED",
    "interrupted": "UNKNOWN",
    "not_started": "NOT_EXECUTED",
    "rolled_back": "ROLLED_BACK",
    "succeeded": "SUCCEEDED",
    "timed_out": "UNKNOWN",
}
#: What the exit status must look like for each observation to be believable.
#: ``any`` is only for the observations that stopped the run from outside, where
#: an exit code may or may not have been produced before the interruption.
EXIT_CODE_RULE: Final = {
    "cancelled": "any",
    "failed": "nonzero",
    "interrupted": "any",
    "not_started": "absent",
    "rolled_back": "any",
    "succeeded": "zero",
    "timed_out": "any",
}
#: The one status that leaves the effect unresolved.  Everything else is a
#: settled outcome; ``UNKNOWN`` always drags reconciliation behind it.
UNRESOLVED_STATUS: Final = "UNKNOWN"

#: Every channel a run has to capture before its receipt may be sealed.
CAPTURE_CHANNELS: Final = ("exit_status", "resource_usage", "stderr", "stdout")
#: Which side of the receipt each channel lands on.  ``stderr`` is the
#: diagnostic channel and is filed as an error artifact whatever the exit code
#: says, so a green run that wrote warnings still surfaces them.
CHANNEL_CLASS: Final = {
    "exit_status": "result",
    "resource_usage": "result",
    "stderr": "error",
    "stdout": "result",
}
#: The two artifact partitions an EffectReceipt publishes.
ARTIFACT_CLASSES: Final = ("error", "result")

#: Risk classes that may not run without a named approval.  This is the
#: ``all_effects`` coverage row V01 and T04 already read from the same
#: approval-policy vocabulary, restated against the intent's own risk enum.
APPROVAL_REQUIRED_RISK_CLASSES: Final = ("controlled_effect", "high_risk")
#: Principal types a fencing counter can supersede.
FENCEABLE_PRINCIPAL_TYPES: Final = ("agent", "service", "tool")

#: The authorization questions, in the order a reader should ask them.
AUTHORIZATION_CRITERIA: Final = (
    "intent_verified",
    "arguments_verified",
    "lease_current",
    "capabilities_leased",
    "scopes_leased",
    "fencing_current",
    "approval_present",
    "principal_fenceable",
    "policy_pinned",
    "environment_bound",
)
#: The denials each authorization criterion can report.
CRITERION_DENIALS: Final = {
    "intent_verified": ("INTENT_HASH_MISMATCH",),
    "arguments_verified": ("ARGUMENTS_HASH_MISMATCH",),
    "lease_current": (
        "LEASE_EXPIRED",
        "LEASE_NOT_YET_VALID",
        "LEASE_REVOKED",
        "LEASE_UNSEALED",
    ),
    "capabilities_leased": ("CAPABILITY_UNLEASED",),
    "scopes_leased": ("SCOPE_UNLEASED",),
    "fencing_current": ("STALE_FENCING_TOKEN",),
    "approval_present": ("APPROVAL_MISSING", "APPROVAL_UNLEASED"),
    "principal_fenceable": ("PRINCIPAL_UNFENCEABLE",),
    "policy_pinned": ("POLICY_UNPINNED",),
    "environment_bound": ("ENVIRONMENT_UNBOUND",),
}

#: The execution questions a sealed record answers, in reading order.
EXECUTION_CRITERIA: Final = (
    "authorized",
    "environment_recorded",
    "capture_complete",
    "receipt_derivable",
    "effects_reconciled",
)
#: Gate outcomes, least to most severe.  ``FAILED_RUN`` is deliberately its own
#: rung: a validation target that runs correctly and returns a failure is
#: evidence, not a gate breach, and collapsing the two would let a real
#: negative result read as a broken pipeline.
EXECUTION_GATE_LADDER: Final = ("PASS", "FAILED_RUN", "INCIDENT", "DENIED")


class ValidationExecutionError(ValueError):
    """A run, capture or receipt that could not describe a real execution."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise ValidationExecutionError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ValidationExecutionError(code, message, context)


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


def digest(value: object) -> str:
    """The canonical sha256 of any JSON-encodable value."""

    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def digest_bytes(payload: bytes) -> str:
    """The canonical sha256 of exactly the bytes that were captured."""

    if not isinstance(payload, (bytes, bytearray)):
        _fail("INPUT_INVALID", "a captured payload must be bytes")
    return "sha256:" + hashlib.sha256(bytes(payload)).hexdigest()


def hash_excluding(payload: Mapping[str, Any], field: str) -> str:
    """The digest a self-hashing record publishes in ``field``.

    This is the derivation the Foundry Kernel already uses for ActionIntent,
    CapabilityLease and EffectReceipt hashes — every declared field except the
    hash field itself — so a document sealed here and one sealed there agree.
    """

    return digest({key: value for key, value in payload.items() if key != field})


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    result: dict[str, Any] = {}
    for key, entry in value.items():  # type: ignore[union-attr]
        if not isinstance(key, str):
            _fail("INPUT_INVALID", f"{label} keys must be strings", {"label": label})
        result[key] = entry
    return result


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("INPUT_INVALID", f"{label} must be an array", {"label": label})
    return list(value)  # type: ignore[arg-type]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        _fail("INPUT_INVALID", f"{label} must be a boolean", {"label": label})
    return bool(value)


def _integer(value: object, label: str, *, minimum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _fail("INPUT_INVALID", f"{label} must be an integer", {"label": label})
    if minimum is not None and int(value) < minimum:  # type: ignore[arg-type]
        _fail(
            "INPUT_INVALID",
            f"{label} must be at least {minimum}",
            {"label": label, "value": value},
        )
    return int(value)  # type: ignore[arg-type]


def _timestamp(value: object, label: str) -> str:
    text = _text(value, label)
    if RFC3339_PATTERN.fullmatch(text) is None:
        _fail(
            "INPUT_INVALID",
            f"{label} must be an RFC3339 instant",
            {"label": label, "value": text},
        )
    return text


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    entries = [
        _text(entry, f"{label}[{index}]")
        for index, entry in enumerate(_sequence(value, label))
    ]
    if len(set(entries)) != len(entries):
        _fail("INPUT_INVALID", f"{label} must not repeat an entry", {"label": label})
    return tuple(entries)


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            f"{label} field set is invalid",
            {"label": label, "missing": missing, "unknown": unknown},
        )


def _schema(repository_root: str | Path, relative: str) -> dict[str, Any]:
    path = Path(repository_root) / relative
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail("SCHEMA_UNREADABLE", f"{relative} could not be read: {error}")
        raise  # pragma: no cover - _fail always raises
    return _mapping(loaded, relative)


def _node(document: Mapping[str, Any], relative: str, *path: str) -> Any:
    node: Any = document
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            _fail(
                "SCHEMA_UNREADABLE",
                f"{relative} does not declare {'.'.join(path)}",
                {"schema": relative},
            )
        node = node[key]
    return node


def _enum(repository_root: str | Path, relative: str, *path: str) -> tuple[str, ...]:
    node = _node(_schema(repository_root, relative), relative, *path)
    if not isinstance(node, list) or not node:
        _fail(
            "SCHEMA_UNREADABLE",
            f"{relative} declares an empty {'.'.join(path)}",
            {"schema": relative},
        )
    return tuple(str(entry) for entry in node)  # type: ignore[union-attr]


def _required(repository_root: str | Path, relative: str, *path: str) -> frozenset[str]:
    document = _schema(repository_root, relative)
    node = _node(document, relative, *path) if path else document
    required = node.get("required") if isinstance(node, Mapping) else None
    if not isinstance(required, list) or not required:
        _fail(
            "SCHEMA_UNREADABLE",
            f"{relative} declares no required set at {'.'.join(path) or 'root'}",
            {"schema": relative},
        )
    return frozenset(str(entry) for entry in required)  # type: ignore[union-attr]


def _pattern(repository_root: str | Path, relative: str, *path: str) -> re.Pattern[str]:
    node = _node(_schema(repository_root, relative), relative, *path)
    if not isinstance(node, str) or not node:
        _fail(
            "SCHEMA_UNREADABLE",
            f"{relative} declares no pattern at {'.'.join(path)}",
            {"schema": relative},
        )
    return re.compile(str(node))


def _assert_table(
    table: Mapping[str, Any], declared: Sequence[str], label: str
) -> None:
    """A local decision table must cover the declaring vocabulary exactly."""

    missing = sorted(set(declared) - set(table))
    unknown = sorted(set(table) - set(declared))
    if missing or unknown:
        _fail(
            "VOCABULARY_DRIFT",
            f"the {label} table no longer matches the vocabulary that declares it",
            {"label": label, "missing": missing, "unknown": unknown},
        )


def _assert_subset(values: Sequence[str], declared: Sequence[str], label: str) -> None:
    unknown = sorted(set(values) - set(declared))
    if unknown:
        _fail(
            "VOCABULARY_DRIFT",
            f"the {label} set names a value the schema does not declare",
            {"label": label, "unknown": unknown},
        )


def intent_fields(repository_root: str | Path) -> frozenset[str]:
    """The exact field set an ActionIntent must carry."""

    return _required(repository_root, ACTION_INTENT_SCHEMA_PATH)


def lease_fields(repository_root: str | Path) -> frozenset[str]:
    return _required(repository_root, LEASE_SCHEMA_PATH)


def effect_receipt_fields(repository_root: str | Path) -> frozenset[str]:
    return _required(repository_root, EFFECT_SCHEMA_PATH)


def artifact_receipt_fields(repository_root: str | Path) -> frozenset[str]:
    return _required(repository_root, ARTIFACT_SCHEMA_PATH)


def risk_classes(repository_root: str | Path) -> tuple[str, ...]:
    """Intent risk classes as the schema declares them, weakest first."""

    return _enum(
        repository_root, ACTION_INTENT_SCHEMA_PATH, "properties", "risk_class", "enum"
    )


def principal_types(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, LEASE_SCHEMA_PATH, "properties", "principal_type", "enum"
    )


def effect_statuses(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(repository_root, EFFECT_SCHEMA_PATH, "properties", "status", "enum")


def check_statuses(repository_root: str | Path) -> tuple[str, ...]:
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


def actor_types(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root,
        ARTIFACT_SCHEMA_PATH,
        "properties",
        "created_by",
        "properties",
        "actor_type",
        "enum",
    )


def network_policies(repository_root: str | Path) -> tuple[str, ...]:
    return _enum(
        repository_root, TARGET_SCHEMA_PATH, "properties", "network_policy", "enum"
    )


def reproducibility_fields(repository_root: str | Path) -> frozenset[str]:
    """The reproducibility contract field set V01 seals and V03 must honour."""

    return _required(
        repository_root, TARGET_SCHEMA_PATH, "properties", "reproducibility_contract"
    )


def resource_dimensions(repository_root: str | Path) -> tuple[str, ...]:
    """Every dimension the canonical budget envelope meters, sorted.

    Usage is recorded against the same dimensions a budget bounds, so a breach
    can be reconstructed from the run record without a second vocabulary.
    """

    return tuple(
        sorted(
            _required(repository_root, BUDGET_SCHEMA_PATH, "properties", "hard_limits")
        )
    )


def sha256_pattern(repository_root: str | Path) -> re.Pattern[str]:
    return _pattern(
        repository_root,
        ACTION_INTENT_SCHEMA_PATH,
        "properties",
        "intent_hash",
        "pattern",
    )


def observation_statuses(repository_root: str | Path) -> dict[str, str]:
    """The observation-to-status table, asserted against the canonical enum."""

    declared = effect_statuses(repository_root)
    _assert_table(
        {status: None for status in set(OBSERVATION_STATUS.values())},
        declared,
        "observation status",
    )
    _assert_table(EXIT_CODE_RULE, tuple(OBSERVATION_STATUS), "exit code rule")
    if UNRESOLVED_STATUS not in declared:
        _fail(
            "VOCABULARY_DRIFT",
            "the unresolved status is not one the schema declares",
            {"status": UNRESOLVED_STATUS},
        )
    return dict(OBSERVATION_STATUS)


def approval_required_risk_classes(repository_root: str | Path) -> tuple[str, ...]:
    """Risk classes that may not run unapproved, checked against the enum."""

    _assert_subset(
        APPROVAL_REQUIRED_RISK_CLASSES, risk_classes(repository_root), "approval risk"
    )
    return tuple(sorted(APPROVAL_REQUIRED_RISK_CLASSES))


def fenceable_principal_types(repository_root: str | Path) -> tuple[str, ...]:
    """Principal types a fencing counter can supersede, checked against enum."""

    declared = principal_types(repository_root)
    _assert_subset(FENCEABLE_PRINCIPAL_TYPES, declared, "fenceable principals")
    unfenceable = sorted(set(declared) - set(FENCEABLE_PRINCIPAL_TYPES))
    if not unfenceable:
        _fail(
            "VOCABULARY_DRIFT",
            "every declared principal type is fenceable, so the rule screens "
            "nothing and a person could hold an unsupersedable run",
            {"declared": list(declared)},
        )
    return tuple(sorted(FENCEABLE_PRINCIPAL_TYPES))


def capture_channels(repository_root: str | Path) -> tuple[str, ...]:
    """The required capture channels, with their partition table asserted."""

    _assert_table(CHANNEL_CLASS, CAPTURE_CHANNELS, "capture channel class")
    _assert_subset(
        tuple(CHANNEL_CLASS.values()), ARTIFACT_CLASSES, "capture channel partition"
    )
    return tuple(sorted(CAPTURE_CHANNELS))


def _validator(repository_root: str | Path, relative: str) -> Draft202012Validator:
    return Draft202012Validator(_schema(repository_root, relative))


def schema_errors(
    repository_root: str | Path, relative: str, document: object
) -> list[str]:
    """Every canonical schema error in a candidate document, sorted."""

    return sorted(
        "/".join(str(part) for part in error.absolute_path) + ": " + error.message
        for error in _validator(repository_root, relative).iter_errors(document)
    )


def _require_schema(
    repository_root: str | Path, relative: str, document: object, code: str, label: str
) -> None:
    errors = schema_errors(repository_root, relative, document)
    if errors:
        _fail(code, f"the assembled {label} does not validate", {"errors": errors})


def build_action_intent(
    repository_root: str | Path,
    *,
    intent_id: str,
    run_id: str,
    node_id: str,
    action_type: str,
    target_ref: str,
    arguments_artifact_id: str,
    arguments: Mapping[str, Any],
    idempotency_key: str,
    required_capabilities: Sequence[Any],
    approval_record_ids: Sequence[Any],
    risk_class: str,
    created_at: str,
) -> dict[str, Any]:
    """Assemble one canonical ActionIntent for a validation invocation.

    ``arguments_hash`` is derived from the argument document rather than
    supplied beside it, so the two can never disagree, and ``intent_hash`` is
    derived over exactly the other declared fields.  The caller's ``arguments``
    mapping is not mutated and is not embedded: the intent names the artifact
    that holds it and pins it by digest.
    """

    root = Path(repository_root)
    declared = risk_classes(root)
    resolved = _text(risk_class, "risk_class")
    if resolved not in declared:
        _fail(
            "INPUT_INVALID",
            "risk_class is not a value the canonical schema declares",
            {"value": resolved, "allowed": list(declared)},
        )
    intent: dict[str, Any] = {
        "action_type": _text(action_type, "action_type"),
        "approval_record_ids": sorted(
            _string_tuple(approval_record_ids, "approval_record_ids")
        ),
        "arguments_artifact_id": _text(arguments_artifact_id, "arguments_artifact_id"),
        "arguments_hash": digest(_mapping(arguments, "arguments")),
        "created_at": _timestamp(created_at, "created_at"),
        "idempotency_key": _text(idempotency_key, "idempotency_key"),
        "intent_id": _text(intent_id, "intent_id"),
        "node_id": _text(node_id, "node_id"),
        "required_capabilities": sorted(
            _string_tuple(required_capabilities, "required_capabilities")
        ),
        "risk_class": resolved,
        "run_id": _text(run_id, "run_id"),
        "target_ref": _text(target_ref, "target_ref"),
    }
    intent["intent_hash"] = hash_excluding(intent, "intent_hash")
    _exact_fields(intent, intent_fields(root), "action_intent")
    _require_schema(
        root, ACTION_INTENT_SCHEMA_PATH, intent, "INTENT_SCHEMA_INVALID", "ActionIntent"
    )
    return intent


def verify_action_intent(
    repository_root: str | Path,
    intent: Mapping[str, Any],
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-derive both hashes an intent publishes, without deciding anything.

    Returns a record rather than raising, because a caller that has just been
    handed an edited intent wants to see both derivations side by side; the
    authorization gate is what turns a mismatch into a refusal.
    """

    root = Path(repository_root)
    document = _mapping(intent, "action_intent")
    _exact_fields(document, intent_fields(root), "action_intent")
    expected_intent = hash_excluding(document, "intent_hash")
    expected_arguments = digest(_mapping(arguments, "arguments"))
    record = {
        "arguments_hash_declared": document["arguments_hash"],
        "arguments_hash_derived": expected_arguments,
        "arguments_hash_matches": document["arguments_hash"] == expected_arguments,
        "intent_hash_declared": document["intent_hash"],
        "intent_hash_derived": expected_intent,
        "intent_hash_matches": document["intent_hash"] == expected_intent,
        "intent_id": document["intent_id"],
    }
    record["verification_hash"] = hash_excluding(record, "verification_hash")
    return record


def seal_run_environment(
    repository_root: str | Path,
    *,
    environment_id: str,
    run_id: str,
    target_id: str,
    target_version: str,
    entrypoint: str,
    artifact_hashes: Sequence[Any],
    reproducibility_contract: Mapping[str, Any],
    container_digest: str | None,
    environment_capture: Mapping[str, Any],
    seeds: Mapping[str, Any],
    network_policy: str,
    sandbox_profile: str,
    recorded_at: str,
) -> dict[str, Any]:
    """Seal what a run ran as, under the target's own reproducibility contract.

    The contract is not re-decided here — V01 sealed it into the target
    manifest — it is *enforced* as an obligation on this record.  Each flag it
    sets true becomes something the run must actually carry: a pinned image, a
    non-empty environment capture, a named integer seed per stochastic stream.
    Recording more than the contract demands is always allowed; recording less
    is refused, because a result whose environment was never captured cannot be
    independently re-derived no matter how good the analysis on top of it is.
    """

    root = Path(repository_root)
    pattern = sha256_pattern(root)
    contract = _mapping(reproducibility_contract, "reproducibility_contract")
    _exact_fields(contract, reproducibility_fields(root), "reproducibility_contract")
    resolved_contract = {
        field: _boolean(contract[field], f"reproducibility_contract.{field}")
        for field in sorted(contract)
    }

    hashes = sorted(_string_tuple(artifact_hashes, "artifact_hashes"))
    if not hashes:
        _fail("ARTIFACTS_UNPINNED", "the run records no target artifact hash")
    for value in hashes:
        if pattern.fullmatch(value) is None:
            _fail(
                "ARTIFACTS_UNPINNED",
                "an artifact hash is not in canonical sha256 form",
                {"value": value},
            )

    resolved_seeds = {
        key: _integer(value, f"seeds.{key}")
        for key, value in sorted(_mapping(seeds, "seeds").items())
    }
    if resolved_contract.get("seed_control") and not resolved_seeds:
        _fail(
            "SEEDS_UNRECORDED",
            "the reproducibility contract requires seed control and the run "
            "records no seed",
            {"contract": resolved_contract},
        )

    resolved_capture = {
        key: _text(value, f"environment_capture.{key}")
        for key, value in sorted(_mapping(environment_capture, "capture").items())
    }
    if resolved_contract.get("environment_capture") and not resolved_capture:
        _fail(
            "ENVIRONMENT_UNCAPTURED",
            "the reproducibility contract requires environment capture and the "
            "run records none",
            {"contract": resolved_contract},
        )

    resolved_digest = container_digest
    if resolved_digest is not None:
        resolved_digest = _text(resolved_digest, "container_digest")
        if pattern.fullmatch(resolved_digest) is None:
            _fail(
                "CONTAINER_UNPINNED",
                "the container digest is not in canonical sha256 form",
                {"value": resolved_digest},
            )
    if resolved_contract.get("container_digest_required") and resolved_digest is None:
        _fail(
            "CONTAINER_UNPINNED",
            "the reproducibility contract requires a pinned image and the run "
            "records no container digest",
            {"contract": resolved_contract},
        )

    declared_policies = network_policies(root)
    policy = _text(network_policy, "network_policy")
    if policy not in declared_policies:
        _fail(
            "INPUT_INVALID",
            "network_policy is not a value the canonical schema declares",
            {"value": policy, "allowed": list(declared_policies)},
        )

    environment: dict[str, Any] = {
        "artifact_hashes": hashes,
        "container_digest": resolved_digest,
        "entrypoint": _text(entrypoint, "entrypoint"),
        "environment_capture": resolved_capture,
        "environment_id": _text(environment_id, "environment_id"),
        "network_policy": policy,
        "recorded_at": _timestamp(recorded_at, "recorded_at"),
        "reproducibility_contract": resolved_contract,
        "run_id": _text(run_id, "run_id"),
        "sandbox_profile": _text(sandbox_profile, "sandbox_profile"),
        "seeds": resolved_seeds,
        "target_id": _text(target_id, "target_id"),
        "target_version": _text(target_version, "target_version"),
    }
    environment["environment_hash"] = hash_excluding(environment, "environment_hash")
    return environment


def seal_capture_channel(
    repository_root: str | Path,
    *,
    receipt_id: str,
    artifact_id: str,
    action_intent_id: str | None,
    channel: str,
    payload: bytes,
    media_type: str,
    locator: str,
    actor_id: str,
    actor_type: str,
    created_at: str,
    truncated: bool = False,
) -> dict[str, Any]:
    """Content-address one captured channel into a canonical ArtifactReceipt.

    The hash comes from the bytes that were actually captured, so a truncated
    capture is sealed as exactly what it is rather than as what a complete one
    would have been.  Truncation is recorded as a failing validation result on
    the receipt instead of being hidden, because a caller reading stdout later
    has to know whether it is reading all of it.
    """

    root = Path(repository_root)
    declared_channels = capture_channels(root)
    resolved_channel = _text(channel, "channel")
    if resolved_channel not in declared_channels:
        _fail(
            "INPUT_INVALID",
            "channel is not one this contract captures",
            {"value": resolved_channel, "allowed": list(declared_channels)},
        )
    declared_actors = actor_types(root)
    resolved_actor = _text(actor_type, "actor_type")
    if resolved_actor not in declared_actors:
        _fail(
            "INPUT_INVALID",
            "actor_type is not a value the canonical schema declares",
            {"value": resolved_actor, "allowed": list(declared_actors)},
        )
    statuses = check_statuses(root)
    for required in ("PASS", "FAIL"):
        if required not in statuses:
            _fail(
                "VOCABULARY_DRIFT",
                "the artifact receipt schema no longer declares a status this "
                "capture contract records",
                {"status": required, "declared": list(statuses)},
            )
    content = digest_bytes(payload)
    complete = not _boolean(truncated, "truncated")
    receipt: dict[str, Any] = {
        "action_intent_id": (
            None if action_intent_id is None else _text(action_intent_id, "intent id")
        ),
        "artifact_id": _text(artifact_id, "artifact_id"),
        "byte_size": len(bytes(payload)),
        "content_hash": content,
        "created_at": _timestamp(created_at, "created_at"),
        "created_by": {
            "actor_id": _text(actor_id, "actor_id"),
            "actor_type": resolved_actor,
        },
        "locator": _text(locator, "locator"),
        "media_type": _text(media_type, "media_type"),
        "receipt_id": _text(receipt_id, "receipt_id"),
        "schema_ref": None,
        "validation_results": [
            {
                "check": "content_hash_matches_payload",
                "details": f"{content} over {len(bytes(payload))} captured bytes",
                "status": "PASS",
            },
            {
                "check": "capture_complete",
                "details": (
                    f"the {resolved_channel} channel was captured in full"
                    if complete
                    else f"the {resolved_channel} channel was truncated on capture"
                ),
                "status": "PASS" if complete else "FAIL",
            },
        ],
    }
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    _exact_fields(receipt, artifact_receipt_fields(root), "artifact_receipt")
    _require_schema(
        root,
        ARTIFACT_SCHEMA_PATH,
        receipt,
        "RECEIPT_SCHEMA_INVALID",
        "ArtifactReceipt",
    )
    return receipt


def verify_capture_channel(
    repository_root: str | Path, receipt: Mapping[str, Any], payload: bytes
) -> dict[str, Any]:
    """Re-derive a capture receipt from the bytes it claims to describe."""

    root = Path(repository_root)
    document = _mapping(receipt, "artifact_receipt")
    _exact_fields(document, artifact_receipt_fields(root), "artifact_receipt")
    content = digest_bytes(payload)
    expected = hash_excluding(document, "receipt_hash")
    record = {
        "byte_size_declared": document["byte_size"],
        "byte_size_observed": len(bytes(payload)),
        "content_hash_declared": document["content_hash"],
        "content_hash_derived": content,
        "content_hash_matches": document["content_hash"] == content,
        "receipt_hash_matches": document["receipt_hash"] == expected,
        "receipt_id": document["receipt_id"],
        "size_matches": document["byte_size"] == len(bytes(payload)),
    }
    record["verification_hash"] = hash_excluding(record, "verification_hash")
    return record


def build_run_capture(
    repository_root: str | Path,
    *,
    capture_id: str,
    run_id: str,
    intent_id: str,
    observation: str,
    exit_code: int | None,
    resource_usage: Mapping[str, Any],
    channels: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble the complete record of what a run did while it was running.

    Every channel this contract requires has to be present and each has to
    re-derive the receipt hash it publishes, so a capture assembled from a
    receipt someone edited afterwards is refused rather than sealed.  The
    observation and the exit status have to agree: a run reported as succeeded
    with a non-zero exit, or one reported as never started that nonetheless
    produced an exit code, is a contradiction and not a capture.
    """

    root = Path(repository_root)
    statuses = observation_statuses(root)
    resolved_observation = _text(observation, "observation")
    if resolved_observation not in statuses:
        _fail(
            "INPUT_INVALID",
            "observation is not one this contract recognises",
            {"value": resolved_observation, "allowed": sorted(statuses)},
        )

    rule = EXIT_CODE_RULE[resolved_observation]
    resolved_exit = exit_code
    if resolved_exit is not None:
        resolved_exit = _integer(resolved_exit, "exit_code")
    if rule == "absent" and resolved_exit is not None:
        _fail(
            "STATUS_UNOBSERVED",
            f"a run observed as {resolved_observation} cannot carry an exit code",
            {"observation": resolved_observation, "exit_code": resolved_exit},
        )
    if rule in ("zero", "nonzero") and resolved_exit is None:
        _fail(
            "STATUS_UNOBSERVED",
            f"a run observed as {resolved_observation} must carry an exit code",
            {"observation": resolved_observation},
        )
    if rule == "zero" and resolved_exit != 0:
        _fail(
            "STATUS_UNOBSERVED",
            "a run observed as succeeded exited non-zero",
            {"observation": resolved_observation, "exit_code": resolved_exit},
        )
    if rule == "nonzero" and resolved_exit == 0:
        _fail(
            "STATUS_UNOBSERVED",
            "a run observed as failed exited zero",
            {"observation": resolved_observation, "exit_code": resolved_exit},
        )

    dimensions = resource_dimensions(root)
    usage = _mapping(resource_usage, "resource_usage")
    unmet = sorted(set(dimensions) - set(usage))
    if unmet:
        _fail(
            "RESOURCE_USAGE_INCOMPLETE",
            "the run reports no usage for a metered dimension",
            {"missing": unmet, "metered": list(dimensions)},
        )
    resolved_usage = {
        dimension: _integer(usage[dimension], f"resource_usage.{dimension}", minimum=0)
        for dimension in dimensions
    }

    required_channels = capture_channels(root)
    supplied = _mapping(channels, "channels")
    missing = sorted(set(required_channels) - set(supplied))
    unknown = sorted(set(supplied) - set(required_channels))
    if missing or unknown:
        _fail(
            "CAPTURE_INCOMPLETE",
            "the run capture does not carry exactly the required channels",
            {"missing": missing, "unknown": unknown},
        )

    sealed: dict[str, dict[str, Any]] = {}
    for name in sorted(required_channels):
        receipt = _mapping(supplied[name], f"channels.{name}")
        _exact_fields(receipt, artifact_receipt_fields(root), f"channels.{name}")
        if receipt["receipt_hash"] != hash_excluding(receipt, "receipt_hash"):
            _fail(
                "RECEIPT_HASH_MISMATCH",
                f"the {name} capture receipt does not re-derive its own hash",
                {"channel": name, "receipt_id": receipt.get("receipt_id")},
            )
        sealed[name] = dict(receipt)

    capture: dict[str, Any] = {
        "capture_id": _text(capture_id, "capture_id"),
        "channel_hashes": {
            name: sealed[name]["content_hash"] for name in sorted(sealed)
        },
        "channel_receipt_ids": {
            name: sealed[name]["receipt_id"] for name in sorted(sealed)
        },
        "effect_status": statuses[resolved_observation],
        "exit_code": resolved_exit,
        "intent_id": _text(intent_id, "intent_id"),
        "observation": resolved_observation,
        "resource_usage": resolved_usage,
        "run_id": _text(run_id, "run_id"),
        "truncated_channels": sorted(
            name
            for name in sealed
            if any(
                entry["check"] == "capture_complete" and entry["status"] != "PASS"
                for entry in sealed[name]["validation_results"]
            )
        ),
    }
    capture["capture_hash"] = hash_excluding(capture, "capture_hash")
    return capture


def _covers(scope: str, requested: str) -> bool:
    if scope == requested:
        return True
    if scope.endswith(SCOPE_WILDCARD):
        return requested.startswith(scope[: -len(SCOPE_WILDCARD)])
    return False


@dataclass(frozen=True)
class _Grant:
    """One lease, already field-checked, with its instants parsed once."""

    document: dict[str, Any]
    issued_at: datetime
    expires_at: datetime


def _open_grant(repository_root: str | Path, lease: object) -> _Grant:
    root = Path(repository_root)
    document = _mapping(lease, "capability_lease")
    _exact_fields(document, lease_fields(root), "capability_lease")
    declared = principal_types(root)
    if document["principal_type"] not in declared:
        _fail(
            "INPUT_INVALID",
            "principal_type is not a value the canonical schema declares",
            {"value": document["principal_type"], "allowed": list(declared)},
        )
    issued = _timestamp(document["issued_at"], "lease.issued_at")
    expires = _timestamp(document["expires_at"], "lease.expires_at")
    return _Grant(dict(document), _instant(issued), _instant(expires))


def authorize_execution(
    repository_root: str | Path,
    *,
    decision_id: str,
    intent: Mapping[str, Any],
    arguments: Mapping[str, Any],
    lease: Mapping[str, Any],
    environment: Mapping[str, Any],
    policy_hash: str,
    write_scopes: Sequence[Any],
    scope_fencing_heads: Mapping[str, Any],
    started_at: str,
    decided_at: str,
) -> dict[str, Any]:
    """Decide whether this exact invocation may start, and say why not.

    Every criterion is evaluated rather than short-circuited, so a caller
    repairing a denied run sees the whole gap in one pass instead of fixing one
    thing and rediscovering the next.  Time is taken from ``started_at`` — the
    run's own start instant supplied by the caller — because a lease decision
    has to be reproducible from the record long after any wall clock moved on.

    ``scope_fencing_heads`` is the newest token the caller has seen issued for
    each scope this run will write.  A lease whose token is behind any of them
    has been superseded and must not write, which is the one execution-time
    property no static admission gate can establish.
    """

    root = Path(repository_root)
    document = _mapping(intent, "action_intent")
    _exact_fields(document, intent_fields(root), "action_intent")
    grant = _open_grant(root, lease)
    start_instant = _timestamp(started_at, "started_at")
    start = _instant(start_instant)
    scopes = sorted(_string_tuple(write_scopes, "write_scopes"))
    if not scopes:
        _fail("INPUT_INVALID", "write_scopes must name at least one scope")
    heads = {
        key: _integer(value, f"scope_fencing_heads.{key}", minimum=0)
        for key, value in sorted(_mapping(scope_fencing_heads, "heads").items())
    }
    environment_document = _mapping(environment, "run_environment")

    denials: list[str] = []
    satisfied: list[str] = []
    detail: dict[str, Any] = {}

    verification = verify_action_intent(root, document, arguments)
    if verification["intent_hash_matches"]:
        satisfied.append("intent_verified")
    else:
        denials.append("INTENT_HASH_MISMATCH")
        detail["intent_hash_derived"] = verification["intent_hash_derived"]
    if verification["arguments_hash_matches"]:
        satisfied.append("arguments_verified")
    else:
        denials.append("ARGUMENTS_HASH_MISMATCH")
        detail["arguments_hash_derived"] = verification["arguments_hash_derived"]

    lease_denials: list[str] = []
    if grant.document["lease_hash"] != hash_excluding(grant.document, "lease_hash"):
        lease_denials.append("LEASE_UNSEALED")
    if _boolean(grant.document["revoked"], "lease.revoked"):
        lease_denials.append("LEASE_REVOKED")
        detail["revocation_reason"] = grant.document["revocation_reason"]
    if start >= grant.expires_at:
        lease_denials.append("LEASE_EXPIRED")
    if start < grant.issued_at:
        lease_denials.append("LEASE_NOT_YET_VALID")
    if lease_denials:
        denials.extend(lease_denials)
    else:
        satisfied.append("lease_current")

    leased = set(_string_tuple(grant.document["capabilities"], "lease.capabilities"))
    required = set(
        _string_tuple(document["required_capabilities"], "required_capabilities")
    )
    unleased = sorted(required - leased)
    if unleased:
        denials.append("CAPABILITY_UNLEASED")
        detail["unleased_capabilities"] = unleased
    else:
        satisfied.append("capabilities_leased")

    granted_scopes = _string_tuple(
        grant.document["resource_scopes"], "lease.resource_scopes"
    )
    uncovered = sorted(
        scope
        for scope in scopes
        if not any(_covers(granted, scope) for granted in granted_scopes)
    )
    if uncovered:
        denials.append("SCOPE_UNLEASED")
        detail["uncovered_scopes"] = uncovered
    else:
        satisfied.append("scopes_leased")

    token = _integer(grant.document["fencing_token"], "lease.fencing_token", minimum=1)
    superseded = sorted(scope for scope in scopes if heads.get(scope, 0) > token)
    if superseded:
        denials.append("STALE_FENCING_TOKEN")
        detail["superseded_scopes"] = superseded
        detail["fencing_token"] = token
    else:
        satisfied.append("fencing_current")

    approvals = _string_tuple(document["approval_record_ids"], "approval_record_ids")
    leased_approvals = set(
        _string_tuple(grant.document["approval_ids"], "lease.approval_ids")
    )
    approval_denials: list[str] = []
    if document["risk_class"] in approval_required_risk_classes(root):
        if not approvals:
            approval_denials.append("APPROVAL_MISSING")
        else:
            unbacked = sorted(set(approvals) - leased_approvals)
            if unbacked:
                approval_denials.append("APPROVAL_UNLEASED")
                detail["unleased_approvals"] = unbacked
    elif approvals:
        unbacked = sorted(set(approvals) - leased_approvals)
        if unbacked:
            approval_denials.append("APPROVAL_UNLEASED")
            detail["unleased_approvals"] = unbacked
    if approval_denials:
        denials.extend(approval_denials)
    else:
        satisfied.append("approval_present")

    if grant.document["principal_type"] in fenceable_principal_types(root):
        satisfied.append("principal_fenceable")
    else:
        denials.append("PRINCIPAL_UNFENCEABLE")
        detail["principal_type"] = grant.document["principal_type"]

    pinned = _text(policy_hash, "policy_hash")
    if grant.document["policy_hash"] == pinned:
        satisfied.append("policy_pinned")
    else:
        denials.append("POLICY_UNPINNED")
        detail["lease_policy_hash"] = grant.document["policy_hash"]

    environment_bound = (
        "environment_hash" in environment_document
        and environment_document["environment_hash"]
        == hash_excluding(environment_document, "environment_hash")
        and environment_document.get("run_id") == document["run_id"]
    )
    if environment_bound:
        satisfied.append("environment_bound")
    else:
        denials.append("ENVIRONMENT_UNBOUND")
        detail["environment_run_id"] = environment_document.get("run_id")

    codes = sorted(set(denials))
    decision: dict[str, Any] = {
        "allowed": not codes,
        "criteria": list(AUTHORIZATION_CRITERIA),
        "criteria_satisfied": sorted(satisfied),
        "decided_at": _timestamp(decided_at, "decided_at"),
        "decision_id": _text(decision_id, "decision_id"),
        "denial_codes": codes,
        "denials": {code: DENIAL_CODES[code] for code in codes},
        "detail": detail,
        "environment_hash": environment_document.get("environment_hash"),
        "fencing_token": token,
        "intent_hash": document["intent_hash"],
        "intent_id": document["intent_id"],
        "lease_id": grant.document["lease_id"],
        "run_id": document["run_id"],
        "started_at": start_instant,
        "write_scopes": scopes,
    }
    decision["decision_hash"] = hash_excluding(decision, "decision_hash")
    return decision


def reconcile_effects(
    repository_root: str | Path,
    *,
    reconciliation_id: str,
    expected_effects: Sequence[Any],
    observed_effects: Sequence[Any],
    status: str,
) -> dict[str, Any]:
    """Reconcile what a run was expected to do against what it actually did.

    The arithmetic is exact and published: matched plus missing equals expected,
    matched plus unexpected equals observed.  An unexpected effect raises an
    incident regardless of exit status, because an effect nobody planned for is
    exactly the case where a green run is the most dangerous.  ``UNKNOWN`` drags
    reconciliation behind it even on a perfect match, since an interrupted
    effect may still be in flight.
    """

    root = Path(repository_root)
    declared = effect_statuses(root)
    resolved = _text(status, "status")
    if resolved not in declared:
        _fail(
            "INPUT_INVALID",
            "status is not a value the canonical schema declares",
            {"value": resolved, "allowed": list(declared)},
        )
    expected = _string_tuple(expected_effects, "expected_effects")
    observed = _string_tuple(observed_effects, "observed_effects")
    if len(set(expected)) != len(expected):
        _fail("EFFECT_ID_DUPLICATED", "an expected effect id repeats")
    if len(set(observed)) != len(observed):
        _fail("EFFECT_ID_DUPLICATED", "an observed effect id repeats")

    matched = sorted(set(expected) & set(observed))
    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    incident = bool(unexpected)
    required = incident or bool(missing) or resolved == UNRESOLVED_STATUS

    record: dict[str, Any] = {
        "counts": {
            "expected": len(expected),
            "matched": len(matched),
            "missing": len(missing),
            "observed": len(observed),
            "unexpected": len(unexpected),
        },
        "incident_raised": incident,
        "matched_effects": matched,
        "missing_effects": missing,
        "reconciliation_id": _text(reconciliation_id, "reconciliation_id"),
        "reconciliation_required": required,
        "status": resolved,
        "unexpected_effects": unexpected,
    }
    record["reconciliation_hash"] = hash_excluding(record, "reconciliation_hash")
    return record


def build_effect_receipt(
    repository_root: str | Path,
    *,
    receipt_id: str,
    intent: Mapping[str, Any],
    environment: Mapping[str, Any],
    capture: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    result_artifact_ids: Sequence[Any] = (),
    error_artifact_ids: Sequence[Any] = (),
    external_operation_id: str | None,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    """Seal one canonical EffectReceipt for a completed validation run.

    ``status`` is taken from the capture's observation, never from the caller,
    so a receipt cannot claim an outcome the run did not produce.  The
    idempotency key is taken from the intent for the same reason: a receipt that
    invented its own key would let a retry of the same effect look like a new
    one.  ``observed_state_hash`` binds the environment and the capture
    together, and is null exactly when nothing ran and nothing was observed.
    """

    root = Path(repository_root)
    document = _mapping(intent, "action_intent")
    _exact_fields(document, intent_fields(root), "action_intent")
    environment_document = _mapping(environment, "run_environment")
    capture_document = _mapping(capture, "run_capture")
    reconciled = _mapping(reconciliation, "reconciliation")

    for label, record, field in (
        ("run_environment", environment_document, "environment_hash"),
        ("run_capture", capture_document, "capture_hash"),
        ("reconciliation", reconciled, "reconciliation_hash"),
    ):
        if field not in record or record[field] != hash_excluding(record, field):
            _fail(
                "RECEIPT_HASH_MISMATCH",
                f"the {label} does not re-derive the hash it publishes",
                {"record": label},
            )

    status = _text(capture_document["effect_status"], "capture.effect_status")
    if status != reconciled["status"]:
        _fail(
            "STATUS_UNOBSERVED",
            "the reconciliation was computed against a different status than "
            "the capture observed",
            {"capture": status, "reconciliation": reconciled["status"]},
        )

    start = _timestamp(started_at, "started_at")
    finish = _timestamp(finished_at, "finished_at")
    if _instant(finish) < _instant(start):
        _fail(
            "TIMESTAMP_DISORDERED",
            "the run finished before it started",
            {"started_at": start, "finished_at": finish},
        )

    channel_ids = _mapping(
        capture_document["channel_receipt_ids"], "capture.channel_receipt_ids"
    )
    results = set(_string_tuple(result_artifact_ids, "result_artifact_ids"))
    errors = set(_string_tuple(error_artifact_ids, "error_artifact_ids"))
    for name, artifact in sorted(channel_ids.items()):
        target = results if CHANNEL_CLASS[name] == "result" else errors
        target.add(_text(artifact, f"channel_receipt_ids.{name}"))
    overlap = sorted(results & errors)
    if overlap:
        _fail(
            "INPUT_INVALID",
            "an artifact is filed as both a result and an error",
            {"artifact_ids": overlap},
        )

    nothing_observed = (
        status == OBSERVATION_STATUS["not_started"]
        and not reconciled["matched_effects"]
        and not reconciled["unexpected_effects"]
    )
    observed_state = (
        None
        if nothing_observed
        else digest(
            {
                "capture_hash": capture_document["capture_hash"],
                "environment_hash": environment_document["environment_hash"],
                "reconciliation_hash": reconciled["reconciliation_hash"],
            }
        )
    )

    receipt: dict[str, Any] = {
        "error_artifact_ids": sorted(errors),
        "external_operation_id": (
            None
            if external_operation_id is None
            else _text(external_operation_id, "external_operation_id")
        ),
        "finished_at": finish,
        "idempotency_key": document["idempotency_key"],
        "intent_id": document["intent_id"],
        "observed_state_hash": observed_state,
        "receipt_id": _text(receipt_id, "receipt_id"),
        "reconciliation_required": _boolean(
            reconciled["reconciliation_required"], "reconciliation_required"
        ),
        "result_artifact_ids": sorted(results),
        "run_id": document["run_id"],
        "started_at": start,
        "status": status,
    }
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    _exact_fields(receipt, effect_receipt_fields(root), "effect_receipt")
    _require_schema(
        root, EFFECT_SCHEMA_PATH, receipt, "RECEIPT_SCHEMA_INVALID", "EffectReceipt"
    )
    return receipt


def verify_effect_receipt(
    repository_root: str | Path,
    receipt: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-derive a receipt's hash and its binding to the intent it reports on."""

    root = Path(repository_root)
    document = _mapping(receipt, "effect_receipt")
    _exact_fields(document, effect_receipt_fields(root), "effect_receipt")
    origin = _mapping(intent, "action_intent")
    _exact_fields(origin, intent_fields(root), "action_intent")
    if document["idempotency_key"] != origin["idempotency_key"]:
        _fail(
            "IDEMPOTENCY_KEY_MISMATCH",
            "the receipt claims a different idempotency key than its intent",
            {
                "intent": origin["idempotency_key"],
                "receipt": document["idempotency_key"],
            },
        )
    expected = hash_excluding(document, "receipt_hash")
    record = {
        "intent_bound": document["intent_id"] == origin["intent_id"]
        and document["run_id"] == origin["run_id"],
        "receipt_hash_declared": document["receipt_hash"],
        "receipt_hash_derived": expected,
        "receipt_hash_matches": document["receipt_hash"] == expected,
        "receipt_id": document["receipt_id"],
        "resolves": document["status"] != UNRESOLVED_STATUS,
    }
    record["verification_hash"] = hash_excluding(record, "verification_hash")
    return record


def seal_execution_record(
    repository_root: str | Path,
    *,
    record_id: str,
    sealed_at: str,
    authorization: Mapping[str, Any],
    environment: Mapping[str, Any] | None = None,
    capture: Mapping[str, Any] | None = None,
    receipt: Mapping[str, Any] | None = None,
    reconciliation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose one re-derivable record of an authorized-and-executed run.

    A denied authorization seals a complete record too — with no environment,
    capture or receipt, because nothing ran — so a refusal is evidence in the
    same shape as a success rather than an absence someone has to interpret.

    The gate ladder keeps a legitimately failing target apart from a broken
    pipeline: ``FAILED_RUN`` means the run worked and the target returned a
    failure, which is a result; ``INCIDENT`` means the run's effects did not
    reconcile, which is not.
    """

    root = Path(repository_root)
    decision = _mapping(authorization, "authorization")
    if decision.get("decision_hash") != hash_excluding(decision, "decision_hash"):
        _fail(
            "RECEIPT_HASH_MISMATCH",
            "the authorization does not re-derive the hash it publishes",
            {"record": "authorization"},
        )
    allowed = _boolean(decision["allowed"], "authorization.allowed")

    satisfied: list[str] = []
    detail: dict[str, Any] = {}
    parts: dict[str, Any] = {}

    if allowed:
        satisfied.append("authorized")
    else:
        detail["denial_codes"] = list(decision["denial_codes"])

    supplied = {
        "capture": capture,
        "environment": environment,
        "reconciliation": reconciliation,
        "receipt": receipt,
    }
    if not allowed:
        present = sorted(name for name, value in supplied.items() if value is not None)
        if present:
            _fail(
                "INPUT_INVALID",
                "a denied authorization cannot carry execution evidence",
                {"present": present},
            )
    else:
        absent = sorted(name for name, value in supplied.items() if value is None)
        if absent:
            _fail(
                "INPUT_INVALID",
                "an allowed authorization must carry the whole execution record",
                {"missing": absent},
            )

    if allowed:
        for name, field in (
            ("environment", "environment_hash"),
            ("capture", "capture_hash"),
            ("reconciliation", "reconciliation_hash"),
            ("receipt", "receipt_hash"),
        ):
            document = _mapping(supplied[name], name)
            if document.get(field) != hash_excluding(document, field):
                _fail(
                    "RECEIPT_HASH_MISMATCH",
                    f"the {name} does not re-derive the hash it publishes",
                    {"record": name},
                )
            parts[name] = document

        if parts["environment"]["environment_hash"] == decision["environment_hash"]:
            satisfied.append("environment_recorded")
        else:
            detail["environment_hash"] = parts["environment"]["environment_hash"]

        required_channels = capture_channels(root)
        captured = sorted(_mapping(parts["capture"]["channel_hashes"], "channels"))
        if captured == sorted(required_channels):
            satisfied.append("capture_complete")
        else:
            detail["captured_channels"] = captured

        if parts["receipt"]["status"] == parts["capture"]["effect_status"]:
            satisfied.append("receipt_derivable")
        else:
            detail["receipt_status"] = parts["receipt"]["status"]

        if not parts["reconciliation"]["reconciliation_required"]:
            satisfied.append("effects_reconciled")
        else:
            detail["reconciliation"] = {
                "missing": list(parts["reconciliation"]["missing_effects"]),
                "unexpected": list(parts["reconciliation"]["unexpected_effects"]),
            }

    if not allowed:
        gate = "DENIED"
    elif sorted(satisfied) != sorted(EXECUTION_CRITERIA):
        gate = "INCIDENT"
    elif parts["receipt"]["status"] == OBSERVATION_STATUS["failed"]:
        gate = "FAILED_RUN"
    else:
        gate = "PASS"
    if gate not in EXECUTION_GATE_LADDER:  # pragma: no cover - table is closed
        _fail("VOCABULARY_DRIFT", "an undeclared gate outcome was derived")

    record: dict[str, Any] = {
        "authorization_hash": decision["decision_hash"],
        "capture_hash": None if not allowed else parts["capture"]["capture_hash"],
        "criteria": list(EXECUTION_CRITERIA),
        "criteria_satisfied": sorted(satisfied),
        "detail": detail,
        "effect_receipt_hash": None
        if not allowed
        else parts["receipt"]["receipt_hash"],
        "environment_hash": (
            None if not allowed else parts["environment"]["environment_hash"]
        ),
        "gate": gate,
        "intent_id": decision["intent_id"],
        "reconciliation_hash": (
            None if not allowed else parts["reconciliation"]["reconciliation_hash"]
        ),
        "record_id": _text(record_id, "record_id"),
        "run_id": decision["run_id"],
        "sealed_at": _timestamp(sealed_at, "sealed_at"),
    }
    record["record_hash"] = hash_excluding(record, "record_hash")
    return record
