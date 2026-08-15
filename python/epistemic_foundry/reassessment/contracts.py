"""W03 evidence-update, staleness, and reassessment contracts.

A correction or retraction is applied only when it reaches every dependent
artifact transitively (EF4-I38): retracting a document must not leave a
Passport still asserting a conclusion whose foundation is gone.  The component
computes the transitive blast radius from a declared provenance graph, seals a
hash-bound reassessment plan, and marks every dependent Passport with an
explicit staleness state.  Retraction is stronger than correction: it
INVALIDATES dependents rather than merely marking them stale.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

RFC3339_PATTERN: Final = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})[Tt]"
    r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.[0-9]+)?(?P<zone>[Zz]|(?P<offset_sign>[+-])"
    r"(?P<offset_hour>[0-9]{2}):(?P<offset_minute>[0-9]{2}))$"
)
SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")

#: Canonical trigger vocabulary (schemas/update-impact-report.schema.json).
TRIGGER_TYPES: Final = (
    "new_document",
    "document_correction",
    "document_retraction",
    "claim_correction",
    "ontology_update",
    "domain_pack_update",
    "policy_update",
    "schema_migration",
)
#: Triggers that void dependents rather than merely prompting reassessment.
INVALIDATING_TRIGGERS: Final = frozenset(
    {
        "document_correction",
        "document_retraction",
        "claim_correction",
        "ontology_update",
        "policy_update",
        "schema_migration",
    }
)
#: The subset whose dependents are void, not merely questionable.
VOIDING_TRIGGERS: Final = frozenset({"document_retraction"})

REQUIRED_ACTIONS: Final = (
    "reparse",
    "reextract",
    "reretrieve",
    "redeliberate",
    "revalidate",
    "human_review",
    "no_action",
)
NO_ACTION: Final = "no_action"
PRIORITIES: Final = ("P0", "P1", "P2", "P3")

#: Artifact classes the reassessment graph distinguishes.
ARTIFACT_CLASSES: Final = (
    "document",
    "evidence",
    "claim",
    "pack",
    "passport",
    "span",
    "decision",
)

#: Passport staleness states.  FRESH is never assigned by this component: a
#: Passport reached by an update is either stale or invalidated.
PASSPORT_STATES: Final = ("FRESH", "STALE", "INVALIDATED")

_DEFAULT_ACTIONS: Final = MappingProxyType(
    {
        "new_document": ("reretrieve",),
        "document_correction": ("reparse", "reextract", "reretrieve", "redeliberate"),
        "document_retraction": ("reretrieve", "redeliberate", "human_review"),
        "claim_correction": ("reextract", "redeliberate"),
        "ontology_update": ("reextract", "redeliberate"),
        "domain_pack_update": ("redeliberate",),
        "policy_update": ("redeliberate", "human_review"),
        "schema_migration": ("reparse", "revalidate"),
    }
)
_DEFAULT_PRIORITY: Final = MappingProxyType(
    {
        "new_document": "P2",
        "document_correction": "P1",
        "document_retraction": "P0",
        "claim_correction": "P1",
        "ontology_update": "P1",
        "domain_pack_update": "P2",
        "policy_update": "P1",
        "schema_migration": "P1",
    }
)

_NODE_FIELDS: Final = frozenset({"artifact_id", "artifact_class", "depends_on"})
_PLAN_FIELDS: Final = frozenset(
    {
        "plan_id",
        "run_id",
        "trigger_event_id",
        "trigger_type",
        "trigger_artifact_ids",
        "affected_claim_ids",
        "affected_evidence_ids",
        "affected_pack_ids",
        "affected_passport_ids",
        "invalidated_artifact_ids",
        "passport_states",
        "required_actions",
        "priority",
        "created_at",
        "plan_hash",
    }
)


class ReassessmentError(ValueError):
    """Typed fail-closed W03 reassessment error."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.run_status = "FAIL"
        self.details = MappingProxyType(dict(details)) if details is not None else None


def _fail(
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> None:
    raise ReassessmentError(code, message, details)


@dataclass(frozen=True, slots=True)
class SealedArtifact:
    """Immutable canonical JSON snapshot with a fresh projection on access."""

    artifact_type: str
    _canonical_bytes: bytes

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def payload(self) -> dict[str, object]:
        value = json.loads(self._canonical_bytes.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("sealed artifact is not an object")
        return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ReassessmentError(
            "CANONICAL_JSON_INVALID", "value must be finite canonical UTF-8 JSON"
        ) from error


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _hash_excluding(payload: Mapping[str, object], field: str) -> str:
    return _digest({key: value for key, value in payload.items() if key != field})


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or "\x00" in value:
        _fail("INPUT_INVALID", f"{label} must be a non-empty NUL-free string")
    return value.strip()


def _month_length(year: int, month: int) -> int:
    leap_year = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return (
        31,
        29 if leap_year else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    )[month - 1]


def _shift_calendar_day(
    year: int, month: int, day: int, day_delta: int
) -> tuple[int, int, int]:
    while day_delta > 0:
        day += 1
        if day > _month_length(year, month):
            day = 1
            month += 1
            if month > 12:
                month = 1
                year += 1
        day_delta -= 1
    while day_delta < 0:
        day -= 1
        if day < 1:
            month -= 1
            if month < 1:
                month = 12
                year -= 1
            day = _month_length(year, month)
        day_delta += 1
    return year, month, day


def _timestamp(value: object, label: str) -> str:
    if type(value) is not str:
        _fail("TIMESTAMP_INVALID", f"{label} must be RFC 3339 with an explicit offset")
    match = RFC3339_PATTERN.fullmatch(value)
    if match is None:
        _fail("TIMESTAMP_INVALID", f"{label} must be RFC 3339 with an explicit offset")
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))
    if (
        month < 1
        or month > 12
        or day < 1
        or day > _month_length(year, month)
        or hour > 23
        or minute > 59
        or second > 60
    ):
        _fail("TIMESTAMP_INVALID", f"{label} is not a real timestamp")
    offset_minutes = 0
    if match.group("zone") not in {"Z", "z"}:
        offset_hour = int(match.group("offset_hour"))
        offset_minute = int(match.group("offset_minute"))
        if offset_hour > 23 or offset_minute > 59:
            _fail("TIMESTAMP_INVALID", f"{label} is not a real timestamp")
        offset_minutes = offset_hour * 60 + offset_minute
        if match.group("offset_sign") == "-":
            offset_minutes = -offset_minutes
    if second == 60:
        utc_day_delta, utc_minute = divmod(
            hour * 60 + minute - offset_minutes,
            1440,
        )
        utc_year, utc_month, utc_day = _shift_calendar_day(
            year,
            month,
            day,
            utc_day_delta,
        )
        if utc_minute != 1439 or utc_day != _month_length(utc_year, utc_month):
            _fail(
                "TIMESTAMP_INVALID",
                f"{label} leap second must be at a UTC month end",
            )
    return value


def _strings(value: object, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("INPUT_INVALID", f"{label} must be an array")
    result = [_text(entry, f"{label}[]") for entry in value]
    if not allow_empty and not result:
        _fail("INPUT_INVALID", f"{label} must not be empty")
    if len(result) != len(set(result)):
        _fail("DUPLICATE_VALUE", f"{label} must not contain duplicates")
    return result


def _trigger_type(value: object) -> str:
    if value not in TRIGGER_TYPES:
        _fail("TRIGGER_TYPE_UNKNOWN", f"{value!r} is not a canonical trigger type")
    return str(value)


def validate_graph(nodes: Sequence[Mapping[str, object]]) -> dict[str, dict[str, Any]]:
    """Validate the declared provenance graph and index it by artifact id."""

    if not isinstance(nodes, Sequence) or isinstance(nodes, (str, bytes, bytearray)):
        _fail("INPUT_INVALID", "graph must be an array of nodes")
    indexed: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(nodes):
        if not isinstance(candidate, Mapping):
            _fail("INPUT_INVALID", f"graph[{index}] must be an object")
        node = dict(candidate)
        if any(type(key) is not str for key in node):
            _fail(
                "FIELD_SET_INVALID",
                f"graph[{index}] field names must be strings",
            )
        missing = sorted(_NODE_FIELDS - set(node))
        unknown = sorted(set(node) - _NODE_FIELDS)
        if missing or unknown:
            _fail(
                "FIELD_SET_INVALID",
                f"graph[{index}] field set is not canonical",
                {"missing": missing, "unknown": unknown},
            )
        artifact_id = _text(node["artifact_id"], "artifact_id")
        artifact_class = node["artifact_class"]
        if artifact_class not in ARTIFACT_CLASSES:
            _fail(
                "ARTIFACT_CLASS_UNKNOWN",
                f"{artifact_class!r} is not a canonical artifact class",
            )
        depends_on = _strings(node["depends_on"], f"graph[{index}].depends_on")
        if artifact_id in depends_on:
            _fail("GRAPH_SELF_DEPENDENCY", f"{artifact_id} cannot depend on itself")
        if artifact_id in indexed:
            _fail("GRAPH_DUPLICATE_ARTIFACT", f"duplicate artifact_id {artifact_id}")
        indexed[artifact_id] = {
            "artifact_class": str(artifact_class),
            "artifact_id": artifact_id,
            "depends_on": depends_on,
        }
    for artifact_id, node in indexed.items():
        for dependency in node["depends_on"]:
            if dependency not in indexed:
                _fail(
                    "GRAPH_DEPENDENCY_UNKNOWN",
                    f"{artifact_id} depends on unknown artifact {dependency}",
                )
    return indexed


def dependent_closure(
    seeds: Sequence[str],
    graph: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Every artifact transitively depending on ``seeds`` (cycle tolerant)."""

    if not isinstance(seeds, Sequence) or isinstance(seeds, (str, bytes, bytearray)):
        _fail("INPUT_INVALID", "seeds must be an array")
    if not isinstance(graph, Mapping):
        _fail("INPUT_INVALID", "graph must be an indexed object")
    items = list(graph.items())
    indexed = validate_graph([node for _, node in items])
    normalized_keys = [
        _text(key, f"graph key[{index}]")
        for index, (key, _) in enumerate(items)
    ]
    if [key for key, _ in items] != normalized_keys or normalized_keys != list(
        indexed
    ):
        _fail(
            "GRAPH_INDEX_MISMATCH",
            "graph keys must be canonical and equal node artifact_id",
        )
    dependents: dict[str, list[str]] = {artifact_id: [] for artifact_id in indexed}
    for artifact_id, node in indexed.items():
        for dependency in node["depends_on"]:
            dependents[dependency].append(artifact_id)
    seed_ids = [_text(seed, "seed") for seed in seeds]
    for seed in seed_ids:
        if seed not in indexed:
            _fail(
                "TRIGGER_ARTIFACT_UNKNOWN",
                f"trigger artifact {seed} is not in the graph",
            )
    seen: set[str] = set()
    frontier = list(seed_ids)
    while frontier:
        current = frontier.pop()
        for child in dependents.get(current, ()):
            if child not in seen:
                seen.add(child)
                frontier.append(child)
    return sorted(seen - set(seed_ids))


def assess_update(
    *,
    graph: Sequence[Mapping[str, object]],
    trigger_event_id: str,
    trigger_type: str,
    trigger_artifact_ids: Sequence[str],
    run_id: str,
    created_at: str,
    required_actions: Sequence[str] | None = None,
    priority: str | None = None,
) -> SealedArtifact:
    """Seal the transitive reassessment plan for one update trigger."""

    indexed = validate_graph(graph)
    trigger_event_id = _text(trigger_event_id, "trigger_event_id")
    trigger_type = _trigger_type(trigger_type)
    run_id = _text(run_id, "run_id")
    created_at = _timestamp(created_at, "created_at")
    seeds = _strings(trigger_artifact_ids, "trigger_artifact_ids", allow_empty=False)

    affected = dependent_closure(seeds, indexed)
    by_class: dict[str, list[str]] = {name: [] for name in ARTIFACT_CLASSES}
    for artifact_id in affected:
        by_class[indexed[artifact_id]["artifact_class"]].append(artifact_id)

    invalidating = trigger_type in INVALIDATING_TRIGGERS
    voiding = trigger_type in VOIDING_TRIGGERS
    invalidated = sorted(affected) if invalidating else []

    actions = (
        list(_DEFAULT_ACTIONS[trigger_type])
        if required_actions is None
        else _strings(required_actions, "required_actions", allow_empty=False)
    )
    for action in actions:
        if action not in REQUIRED_ACTIONS:
            _fail("REQUIRED_ACTION_UNKNOWN", f"{action!r} is not a canonical action")
    if invalidating and set(actions) == {NO_ACTION}:
        _fail(
            "INVALIDATION_WITHOUT_REMEDIATION",
            f"trigger {trigger_type} invalidates dependents but requires only {NO_ACTION}",
        )
    resolved_priority = (
        priority if priority is not None else _DEFAULT_PRIORITY[trigger_type]
    )
    if resolved_priority not in PRIORITIES:
        _fail("PRIORITY_UNKNOWN", f"{resolved_priority!r} is not a canonical priority")

    # A retraction voids its dependents; every other trigger that reaches a
    # Passport leaves it questionable rather than void.  No reached Passport
    # may stay FRESH.
    passport_state = "INVALIDATED" if voiding else "STALE"
    passport_states = {
        passport_id: passport_state for passport_id in sorted(by_class["passport"])
    }

    plan: dict[str, Any] = {
        "affected_claim_ids": sorted(by_class["claim"]),
        "affected_evidence_ids": sorted(by_class["evidence"]),
        "affected_pack_ids": sorted(by_class["pack"]),
        "affected_passport_ids": sorted(by_class["passport"]),
        "created_at": created_at,
        "invalidated_artifact_ids": invalidated,
        "passport_states": passport_states,
        "priority": resolved_priority,
        "required_actions": actions,
        "run_id": run_id,
        "trigger_artifact_ids": sorted(seeds),
        "trigger_event_id": trigger_event_id,
        "trigger_type": trigger_type,
    }
    plan["plan_id"] = (
        "RSP-"
        + hashlib.sha256(
            _canonical_json(
                {
                    "run_id": run_id,
                    "trigger_artifact_ids": sorted(seeds),
                    "trigger_event_id": trigger_event_id,
                    "trigger_type": trigger_type,
                }
            )
        ).hexdigest()
    )
    plan["plan_hash"] = _hash_excluding(plan, "plan_hash")
    return _validate_plan_shape(plan)


def _validate_plan_shape(payload: Mapping[str, object]) -> SealedArtifact:
    if not isinstance(payload, Mapping):
        _fail("INPUT_INVALID", "plan must be an object")
    value = dict(payload)
    missing = sorted(_PLAN_FIELDS - set(value))
    unknown = sorted(set(value) - _PLAN_FIELDS)
    if missing or unknown:
        _fail(
            "FIELD_SET_INVALID",
            "ReassessmentPlan field set is not canonical",
            {"missing": missing, "unknown": unknown},
        )
    _text(value["plan_id"], "plan_id")
    _text(value["run_id"], "run_id")
    _text(value["trigger_event_id"], "trigger_event_id")
    _trigger_type(value["trigger_type"])
    for field in (
        "trigger_artifact_ids",
        "affected_claim_ids",
        "affected_evidence_ids",
        "affected_pack_ids",
        "affected_passport_ids",
        "invalidated_artifact_ids",
    ):
        ids = _strings(value[field], field)
        if ids != sorted(ids):
            _fail("ORDER_INVALID", f"{field} must be sorted ascending")
    actions = _strings(value["required_actions"], "required_actions", allow_empty=False)
    for action in actions:
        if action not in REQUIRED_ACTIONS:
            _fail("REQUIRED_ACTION_UNKNOWN", f"{action!r} is not a canonical action")
    if value["priority"] not in PRIORITIES:
        _fail("PRIORITY_UNKNOWN", "priority is not canonical")
    states = value["passport_states"]
    if not isinstance(states, Mapping):
        _fail("INPUT_INVALID", "passport_states must be an object")
    declared = set(value["affected_passport_ids"])  # type: ignore[arg-type]
    if set(states) != declared:
        _fail(
            "PASSPORT_STATE_INCOMPLETE",
            "every affected Passport must carry an explicit state",
            {
                "missing": sorted(declared - set(states)),
                "unknown": sorted(set(states) - declared),
            },
        )
    for passport_id, state in states.items():
        if state not in PASSPORT_STATES:
            _fail(
                "PASSPORT_STATE_UNKNOWN", f"{state!r} is not a canonical passport state"
            )
        if state == "FRESH":
            _fail(
                "PASSPORT_STALENESS_NOT_APPLIED",
                f"passport {passport_id} was reached by an update but stayed FRESH",
            )
    _timestamp(value["created_at"], "created_at")
    asserted = value["plan_hash"]
    if type(asserted) is not str or SHA256_PATTERN.fullmatch(asserted) is None:
        _fail("HASH_FORMAT_INVALID", "plan_hash must be sha256:<64 lowercase hex>")
    if asserted != _hash_excluding(value, "plan_hash"):
        _fail("PLAN_HASH_MISMATCH", "plan_hash does not match canonical content")
    return SealedArtifact("ReassessmentPlan", _canonical_json(value))


def validate_plan(
    plan: Mapping[str, Any],
    *,
    graph: Sequence[Mapping[str, object]],
) -> SealedArtifact:
    """Recompute the plan from its bound graph and require exact identity."""

    asserted = _validate_plan_shape(plan)
    payload = asserted.payload
    rebuilt = assess_update(
        graph=graph,
        trigger_event_id=str(payload["trigger_event_id"]),
        trigger_type=str(payload["trigger_type"]),
        trigger_artifact_ids=list(payload["trigger_artifact_ids"]),  # type: ignore[arg-type]
        run_id=str(payload["run_id"]),
        created_at=str(payload["created_at"]),
        required_actions=list(payload["required_actions"]),  # type: ignore[arg-type]
        priority=str(payload["priority"]),
    )
    if rebuilt.canonical_bytes != asserted.canonical_bytes:
        _fail(
            "PLAN_RECONSTRUCTION_MISMATCH",
            "the plan is not the deterministic reassessment of its bound graph",
        )
    return rebuilt


def apply_passport_states(
    passports: Sequence[Mapping[str, object]],
    plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Project the plan onto Passport revisions.

    A Passport reached by the update receives a new revision carrying the
    plan-derived state and its binding; an untouched Passport is returned
    unchanged.  Marking is never silent: an affected Passport missing from the
    supplied set fails closed.
    """

    sealed = _validate_plan_shape(plan).payload
    if not isinstance(passports, Sequence) or isinstance(
        passports, (str, bytes, bytearray)
    ):
        _fail("INPUT_INVALID", "passports must be an array")
    supplied: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(passports):
        if not isinstance(candidate, Mapping):
            _fail("INPUT_INVALID", f"passports[{index}] must be an object")
        record = dict(candidate)
        passport_id = _text(
            record.get("passport_id"), f"passports[{index}].passport_id"
        )
        revision = record.get("revision")
        if type(revision) is not int or revision < 1:
            _fail(
                "INPUT_INVALID", f"passports[{index}].revision must be an integer >= 1"
            )
        if passport_id in supplied:
            _fail("DUPLICATE_VALUE", f"duplicate passport {passport_id}")
        supplied[passport_id] = record
    affected = set(sealed["affected_passport_ids"])  # type: ignore[arg-type]
    absent = sorted(affected - set(supplied))
    if absent:
        _fail(
            "PASSPORT_NOT_SUPPLIED",
            "an affected Passport was not supplied for marking",
            {"passport_ids": absent},
        )

    result: list[dict[str, Any]] = []
    for passport_id in sorted(supplied):
        record = dict(supplied[passport_id])
        if passport_id in affected:
            record["revision"] = int(record["revision"]) + 1
            record["staleness_state"] = sealed["passport_states"][passport_id]  # type: ignore[index]
            record["staleness_plan_id"] = sealed["plan_id"]
            record["staleness_plan_hash"] = sealed["plan_hash"]
            record["staleness_trigger_event_id"] = sealed["trigger_event_id"]
        result.append(record)
    return result
