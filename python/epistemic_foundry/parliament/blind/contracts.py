"""P01 blind brief assembly and asymmetric dispatch contracts.

Two properties make an Evidence Parliament worth convening, and both are
enforced structurally here rather than trusted.

Roles cannot see forbidden evidence.  Each role's Evidence ACL is read from
``manifests/role_registry.yaml`` — the declaring source — and the context
assembled for that role carries only the evidence classes the ACL permits.
What was withheld is recorded by id so the role knows something exists without
seeing it, and a brief citing evidence its own context never contained is
refused.

First-round isolation is measured, not asserted.  Round one is blind by
contract: every brief must declare ``blind``, and the isolation report examines
every pair of first-round briefs and reports the ratio that stayed independent.
A single cross-reference drops the measured ratio below one and fails the seal,
so "the panel was independent" is a computed fact rather than a claim.

Dispatch is asymmetric on purpose.  A panel where every role saw the same
evidence is one opinion repeated, so an assembly whose contexts are all
identical is refused rather than recorded as unanimous.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml

SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
#: The registry is the declaring source of every role's Evidence ACL.
ROLE_REGISTRY_PATH: Final = "manifests/role_registry.yaml"
#: The ACL token that grants every class the run makes available.
ACL_WILDCARD: Final = "all_permitted"
#: Round one is blind; later rounds may cross-examine.
BLIND_ROUND: Final = 1


class Verdict(str, Enum):
    """Canonical brief verdicts (schemas/council-brief.schema.json)."""

    ENTAILED = "ENTAILED"
    SUPPORTED = "SUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    MIXED = "MIXED"
    CONTRADICTED = "CONTRADICTED"
    UNDERDETERMINED = "UNDERDETERMINED"
    UNTESTABLE = "UNTESTABLE"


class BriefRole(str, Enum):
    """Roles the CouncilBrief schema admits."""

    DEFENDER = "defender"
    PROSECUTOR = "prosecutor"
    METHOD_AUDITOR = "method_auditor"
    SCOPE_AUDITOR = "scope_auditor"
    INDUCTIVIST = "inductivist"
    DEDUCTIVIST = "deductivist"
    CAUSAL_AUDITOR = "causal_auditor"
    NOVELTY_EXAMINER = "novelty_examiner"
    ABDUCTIVE_MEDIATOR = "abductive_mediator"
    BIAS_AUDITOR = "bias_auditor"
    OTHER = "other"


VERDICTS: Final = tuple(entry.value for entry in Verdict)
BRIEF_ROLES: Final = tuple(entry.value for entry in BriefRole)
#: Fewer independent roles than this is a conversation, not a parliament.
MINIMUM_DISPATCHED_ROLES: Final = 2

EVIDENCE_UNIT_FIELDS: Final = frozenset(
    {"evidence_id", "evidence_class", "summary", "provenance_ref"}
)
CONTEXT_FIELDS: Final = frozenset(
    {
        "context_manifest_id",
        "run_id",
        "round",
        "role",
        "permitted_classes",
        "included_evidence_ids",
        "withheld_evidence_ids",
        "withheld_class_counts",
        "created_at",
        "manifest_hash",
    }
)
BRIEF_FIELDS: Final = frozenset(
    {
        "brief_id",
        "run_id",
        "round",
        "role",
        "blind",
        "context_manifest_id",
        "verdict_candidate",
        "assertions",
        "strongest_counterargument",
        "conditions_that_change_verdict",
        "missing_evidence",
        "schema_version",
        "brief_hash",
        "created_at",
    }
)
_ASSERTION_FIELDS: Final = frozenset(
    {
        "assertion_id",
        "text",
        "evidence_ids",
        "argument_node_ids",
        "scope_limitations",
        "confidence",
    }
)
DISPATCH_FIELDS: Final = frozenset(
    {
        "dispatch_id",
        "run_id",
        "round",
        "created_at",
        "context_manifest_ids",
        "role_class_matrix",
        "asymmetry",
        "isolation",
        "brief_ids",
        "dispatch_hash",
    }
)


class ParliamentBlindError(ValueError):
    """Typed fail-closed P01 contract error."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context) if context is not None else {}


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise ParliamentBlindError(code, message, context)


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


def _hex_digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _digest(value: object) -> str:
    return "sha256:" + _hex_digest(value)


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


def _round(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        _fail("INPUT_INVALID", f"{label} must be an integer >= 1")
    return int(value)  # type: ignore[arg-type]


@lru_cache(maxsize=4)
def _registry_document(repository_root: str) -> str:
    return (Path(repository_root) / ROLE_REGISTRY_PATH).read_text(encoding="utf-8")


def evidence_acl(repository_root: Path, role: str) -> tuple[str, ...]:
    """One role's Evidence ACL, read from the declaring registry.

    The ACL is never restated here: a role the registry does not describe has no
    ACL, and dispatching to it fails closed rather than defaulting to open.
    """

    document = yaml.safe_load(_registry_document(str(repository_root)))
    roles = document["roles"] if isinstance(document, Mapping) else document
    for entry in roles:
        if isinstance(entry, Mapping) and str(entry.get("role_id")) == role:
            acl = entry.get("evidence_acl")
            if (
                not isinstance(acl, Sequence)
                or isinstance(acl, (str, bytes))
                or not acl
            ):
                _fail(
                    "ACL_UNDECLARED",
                    "a dispatched role must declare a non-empty Evidence ACL",
                    {"role": role},
                )
            return tuple(sorted({str(item) for item in acl}))  # type: ignore[union-attr]
    _fail(
        "ROLE_UNKNOWN",
        "a dispatched role must exist in the role registry",
        {"role": role},
    )
    raise AssertionError  # pragma: no cover - _fail always raises


def _validate_unit(value: object, index: int) -> dict[str, Any]:
    unit = _mapping(value, f"evidence[{index}]")
    _exact_fields(unit, EVIDENCE_UNIT_FIELDS, f"evidence[{index}]")
    return {
        "evidence_class": _text(unit["evidence_class"], "evidence_class"),
        "evidence_id": _text(unit["evidence_id"], "evidence_id"),
        "provenance_ref": _text(unit["provenance_ref"], "provenance_ref"),
        "summary": _text(unit["summary"], "summary"),
    }


def assemble_context(
    repository_root: Path,
    role: str,
    evidence: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    round_number: int,
    created_at: str,
) -> SealedArtifact:
    """Seal the context one role may see, and name what it may not.

    Withholding is visible: the manifest lists the withheld ids and the count
    per class, so a role can tell that evidence exists outside its ACL without
    being able to read it.
    """

    role = _text(role, "role")
    run_id = _text(run_id, "run_id")
    round_number = _round(round_number, "round")
    created_at = _timestamp(created_at, "created_at")
    permitted = evidence_acl(repository_root, role)

    units: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(evidence):
        unit = _validate_unit(entry, index)
        if unit["evidence_id"] in units:
            _fail(
                "DUPLICATE_EVIDENCE",
                "evidence ids must be unique within one dispatch",
                {"evidence_id": unit["evidence_id"]},
            )
        units[unit["evidence_id"]] = unit

    wildcard = ACL_WILDCARD in permitted
    included: list[str] = []
    withheld: list[str] = []
    withheld_counts: dict[str, int] = {}
    for evidence_id in sorted(units):
        unit = units[evidence_id]
        if wildcard or unit["evidence_class"] in permitted:
            included.append(evidence_id)
        else:
            withheld.append(evidence_id)
            withheld_counts[unit["evidence_class"]] = (
                withheld_counts.get(unit["evidence_class"], 0) + 1
            )

    payload: dict[str, Any] = {
        "created_at": created_at,
        "included_evidence_ids": included,
        "permitted_classes": list(permitted),
        "role": role,
        "round": round_number,
        "run_id": run_id,
        "withheld_class_counts": withheld_counts,
        "withheld_evidence_ids": withheld,
    }
    payload["context_manifest_id"] = "CM-" + _hex_digest(
        {
            "included_evidence_ids": included,
            "role": role,
            "round": round_number,
            "run_id": run_id,
        }
    )
    payload["manifest_hash"] = _hash_excluding(payload, "manifest_hash")
    return validate_context_manifest(payload)


def validate_context_manifest(payload: Mapping[str, Any]) -> SealedArtifact:
    """Validate one context manifest's shape, disjointness, and self-hash."""

    value = _mapping(payload, "ContextManifest")
    _exact_fields(value, CONTEXT_FIELDS, "ContextManifest")
    _text(value["context_manifest_id"], "context_manifest_id")
    _text(value["run_id"], "run_id")
    _text(value["role"], "role")
    _round(value["round"], "round")
    _timestamp(value["created_at"], "created_at")
    included = [
        _text(entry, "included evidence id")
        for entry in _sequence(value["included_evidence_ids"], "included_evidence_ids")
    ]
    withheld = [
        _text(entry, "withheld evidence id")
        for entry in _sequence(value["withheld_evidence_ids"], "withheld_evidence_ids")
    ]
    for label, ids in (("included", included), ("withheld", withheld)):
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            _fail("INPUT_INVALID", f"{label} evidence ids must be unique and sorted")
    overlap = sorted(set(included) & set(withheld))
    if overlap:
        _fail(
            "CONTEXT_INCOHERENT",
            "evidence cannot be both included and withheld",
            {"evidence_ids": overlap},
        )
    if _hash_excluding(value, "manifest_hash") != value["manifest_hash"]:
        _fail("MANIFEST_HASH_MISMATCH", "manifest_hash does not match its content")
    return SealedArtifact("ContextManifest", _canonical_json(value))


def _validate_brief(value: object, index: int) -> dict[str, Any]:
    brief = _mapping(value, f"briefs[{index}]")
    _exact_fields(brief, BRIEF_FIELDS, f"briefs[{index}]")
    brief_id = _text(brief["brief_id"], "brief_id")
    if brief["role"] not in BRIEF_ROLES:
        _fail("ROLE_UNKNOWN", f"{brief_id} declares a non-canonical brief role")
    if brief["verdict_candidate"] not in VERDICTS:
        _fail("VERDICT_INVALID", f"{brief_id} declares a non-canonical verdict")
    if type(brief["blind"]) is not bool:
        _fail("INPUT_INVALID", f"{brief_id} must declare blind as a boolean")
    assertions = _sequence(brief["assertions"], "assertions")
    if not assertions:
        _fail("INPUT_INVALID", f"{brief_id} must carry at least one assertion")
    normalized: list[dict[str, Any]] = []
    for position, entry in enumerate(assertions):
        assertion = _mapping(entry, f"{brief_id}.assertions[{position}]")
        _exact_fields(assertion, _ASSERTION_FIELDS, "assertion")
        confidence = assertion["confidence"]
        if type(confidence) not in (int, float) or isinstance(confidence, bool):
            _fail("INPUT_INVALID", "assertion confidence must be a number")
        if not 0.0 <= float(confidence) <= 1.0:
            _fail("INPUT_INVALID", "assertion confidence must be within [0, 1]")
        normalized.append(
            {
                "argument_node_ids": sorted(
                    {
                        _text(item, "argument_node_id")
                        for item in _sequence(
                            assertion["argument_node_ids"], "argument_node_ids"
                        )
                    }
                ),
                "assertion_id": _text(assertion["assertion_id"], "assertion_id"),
                "confidence": float(confidence),
                "evidence_ids": sorted(
                    {
                        _text(item, "evidence_id")
                        for item in _sequence(assertion["evidence_ids"], "evidence_ids")
                    }
                ),
                "scope_limitations": sorted(
                    {
                        _text(item, "scope limitation")
                        for item in _sequence(
                            assertion["scope_limitations"], "scope_limitations"
                        )
                    }
                ),
                "text": _text(assertion["text"], "text"),
            }
        )
    if not _sequence(
        brief["conditions_that_change_verdict"], "conditions_that_change_verdict"
    ):
        _fail(
            "BRIEF_UNFALSIFIABLE",
            "a brief must name at least one condition that would change its verdict",
            {"brief_id": brief_id},
        )
    return {
        "assertions": normalized,
        "blind": bool(brief["blind"]),
        "brief_hash": _text(brief["brief_hash"], "brief_hash"),
        "brief_id": brief_id,
        "context_manifest_id": _text(
            brief["context_manifest_id"], "context_manifest_id"
        ),
        "created_at": _timestamp(brief["created_at"], "created_at"),
        "role": str(brief["role"]),
        "round": _round(brief["round"], "round"),
        "run_id": _text(brief["run_id"], "run_id"),
        "verdict_candidate": str(brief["verdict_candidate"]),
    }


def cited_evidence(brief: Mapping[str, Any]) -> set[str]:
    """Every evidence id the brief's assertions actually rest on."""

    cited: set[str] = set()
    for assertion in brief["assertions"]:
        cited.update(assertion["evidence_ids"])
    return cited


def measure_first_round_isolation(
    briefs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Measure, rather than assert, that round one stayed independent.

    Every ordered pair of first-round briefs is examined for a citation of the
    other brief's id.  The ratio is a computed fact: one cross-reference is
    enough to drop it below one.
    """

    first_round = [brief for brief in briefs if brief["round"] == BLIND_ROUND]
    brief_ids = {str(brief["brief_id"]) for brief in first_round}
    cross_references: list[dict[str, str]] = []
    pairs = 0
    for source in first_round:
        cited = cited_evidence(source) | {
            node
            for assertion in source["assertions"]
            for node in assertion["argument_node_ids"]
        }
        for target in first_round:
            if source is target:
                continue
            pairs += 1
            target_id = str(target["brief_id"])
            if target_id in cited or target_id in {str(source["context_manifest_id"])}:
                cross_references.append(
                    {
                        "cited_brief_id": target_id,
                        "source_brief_id": str(source["brief_id"]),
                    }
                )
    non_blind = sorted(
        str(brief["brief_id"]) for brief in first_round if not brief["blind"]
    )
    shared_contexts = sorted(
        {
            str(brief["context_manifest_id"])
            for brief in first_round
            if sum(
                1
                for other in first_round
                if other["context_manifest_id"] == brief["context_manifest_id"]
            )
            > 1
        }
    )
    isolated_pairs = pairs - len(cross_references)
    return {
        "brief_count": len(first_round),
        "cross_references": sorted(
            cross_references,
            key=lambda entry: (entry["source_brief_id"], entry["cited_brief_id"]),
        ),
        "isolation_ratio": round(isolated_pairs / pairs, 10) if pairs else 1.0,
        "measured_brief_ids": sorted(brief_ids),
        "non_blind_brief_ids": non_blind,
        "pairs_examined": pairs,
        "shared_context_manifest_ids": shared_contexts,
    }


def measure_asymmetry(contexts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """How differently the roles were briefed, as a computed matrix.

    A panel whose contexts are all identical is one opinion repeated, so the
    asymmetry is reported and the sealing path refuses a symmetric dispatch.
    """

    matrix = {
        str(context["role"]): list(context["permitted_classes"]) for context in contexts
    }
    signatures = {
        str(context["role"]): _hex_digest(list(context["included_evidence_ids"]))
        for context in contexts
    }
    distinct = sorted(set(signatures.values()))
    return {
        "distinct_context_count": len(distinct),
        "distinct_permitted_class_sets": len(
            {tuple(value) for value in matrix.values()}
        ),
        "role_context_signatures": signatures,
        "role_count": len(matrix),
        "symmetric": len(distinct) <= 1 and len(matrix) > 1,
    }


def seal_dispatch(
    contexts: Sequence[Mapping[str, Any]],
    briefs: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    round_number: int,
    created_at: str,
) -> SealedArtifact:
    """Check ACL compliance and blind isolation, then seal the dispatch."""

    run_id = _text(run_id, "run_id")
    round_number = _round(round_number, "round")
    created_at = _timestamp(created_at, "created_at")

    by_manifest: dict[str, dict[str, Any]] = {}
    for entry in contexts:
        manifest = validate_context_manifest(_mapping(entry, "context")).payload
        if manifest["run_id"] != run_id or manifest["round"] != round_number:
            _fail(
                "DISPATCH_INCOHERENT",
                "every context must belong to this run and round",
                {"context_manifest_id": manifest["context_manifest_id"]},
            )
        by_manifest[str(manifest["context_manifest_id"])] = manifest
    if len(by_manifest) < MINIMUM_DISPATCHED_ROLES:
        _fail(
            "DISPATCH_TOO_NARROW",
            "a parliament needs at least two independently briefed roles",
            {"role_count": len(by_manifest)},
        )

    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(briefs):
        brief = _validate_brief(entry, index)
        if brief["brief_id"] in seen:
            _fail(
                "DUPLICATE_BRIEF",
                "brief ids must be unique within one dispatch",
                {"brief_id": brief["brief_id"]},
            )
        seen.add(brief["brief_id"])
        if brief["run_id"] != run_id or brief["round"] != round_number:
            _fail(
                "DISPATCH_INCOHERENT",
                "every brief must belong to this run and round",
                {"brief_id": brief["brief_id"]},
            )
        manifest = by_manifest.get(brief["context_manifest_id"])
        if manifest is None:
            _fail(
                "CONTEXT_UNRESOLVED",
                "a brief must name a context manifest this dispatch assembled",
                {"brief_id": brief["brief_id"]},
            )
        if manifest["role"] != brief["role"]:
            _fail(
                "CONTEXT_ROLE_MISMATCH",
                "a brief must use the context assembled for its own role",
                {"brief_id": brief["brief_id"], "role": brief["role"]},
            )
        leaked = sorted(cited_evidence(brief) - set(manifest["included_evidence_ids"]))
        if leaked:
            withheld = sorted(set(leaked) & set(manifest["withheld_evidence_ids"]))
            _fail(
                "EVIDENCE_ACL_VIOLATION",
                "a brief cited evidence its own context never contained",
                {
                    "brief_id": brief["brief_id"],
                    "cited_withheld": withheld,
                    "evidence_ids": leaked,
                    "role": brief["role"],
                },
            )
        if round_number == BLIND_ROUND and not brief["blind"]:
            _fail(
                "BLINDNESS_VIOLATION",
                "every first-round brief must be produced blind",
                {"brief_id": brief["brief_id"]},
            )
        validated.append(brief)
    validated.sort(key=lambda brief: brief["brief_id"])

    briefed_roles = {brief["role"] for brief in validated}
    unbriefed = sorted(
        manifest["role"]
        for manifest in by_manifest.values()
        if manifest["role"] not in briefed_roles
    )
    if unbriefed:
        _fail(
            "BRIEF_MISSING",
            "every dispatched role must return a brief",
            {"roles": unbriefed},
        )

    isolation = measure_first_round_isolation(validated)
    if round_number == BLIND_ROUND:
        if isolation["cross_references"]:
            _fail(
                "BLINDNESS_VIOLATION",
                "a first-round brief referenced another first-round brief",
                {"cross_references": isolation["cross_references"]},
            )
        if isolation["shared_context_manifest_ids"]:
            _fail(
                "BLINDNESS_VIOLATION",
                "first-round roles must not share one context manifest",
                {"context_manifest_ids": isolation["shared_context_manifest_ids"]},
            )
    asymmetry = measure_asymmetry(list(by_manifest.values()))
    if asymmetry["symmetric"]:
        _fail(
            "DISPATCH_SYMMETRIC",
            "a panel briefed identically is one opinion repeated, not a parliament",
            {"role_count": asymmetry["role_count"]},
        )

    payload: dict[str, Any] = {
        "asymmetry": asymmetry,
        "brief_ids": sorted(brief["brief_id"] for brief in validated),
        "context_manifest_ids": sorted(by_manifest),
        "created_at": created_at,
        "isolation": isolation,
        "role_class_matrix": {
            manifest["role"]: list(manifest["permitted_classes"])
            for manifest in sorted(
                by_manifest.values(), key=lambda entry: entry["role"]
            )
        },
        "round": round_number,
        "run_id": run_id,
    }
    payload["dispatch_id"] = "PD-" + _hex_digest(
        {
            "brief_ids": payload["brief_ids"],
            "context_manifest_ids": payload["context_manifest_ids"],
            "created_at": created_at,
            "round": round_number,
            "run_id": run_id,
        }
    )
    payload["dispatch_hash"] = _hash_excluding(payload, "dispatch_hash")
    return validate_dispatch(payload)


def validate_dispatch(payload: Mapping[str, Any]) -> SealedArtifact:
    """Validate one dispatch record's shape, measured isolation, and self-hash."""

    value = _mapping(payload, "ParliamentDispatch")
    _exact_fields(value, DISPATCH_FIELDS, "ParliamentDispatch")
    _text(value["dispatch_id"], "dispatch_id")
    _text(value["run_id"], "run_id")
    round_number = _round(value["round"], "round")
    _timestamp(value["created_at"], "created_at")
    matrix = _mapping(value["role_class_matrix"], "role_class_matrix")
    if len(matrix) < MINIMUM_DISPATCHED_ROLES:
        _fail(
            "DISPATCH_TOO_NARROW",
            "a parliament needs at least two independently briefed roles",
            {"role_count": len(matrix)},
        )
    for role, classes in matrix.items():
        if not _sequence(classes, f"role_class_matrix.{role}"):
            _fail(
                "ACL_UNDECLARED",
                "a dispatched role must carry a non-empty permitted class list",
                {"role": role},
            )
    asymmetry = _mapping(value["asymmetry"], "asymmetry")
    if asymmetry["symmetric"]:
        _fail(
            "DISPATCH_SYMMETRIC",
            "a sealed dispatch may not record a symmetric panel",
        )
    isolation = _mapping(value["isolation"], "isolation")
    if round_number == BLIND_ROUND:
        if isolation["non_blind_brief_ids"]:
            _fail(
                "BLINDNESS_VIOLATION",
                "a sealed first round may not contain a non-blind brief",
                {"brief_ids": isolation["non_blind_brief_ids"]},
            )
        if isolation["cross_references"] or float(isolation["isolation_ratio"]) < 1.0:
            _fail(
                "BLINDNESS_VIOLATION",
                "a sealed first round must measure full isolation",
                {"isolation_ratio": isolation["isolation_ratio"]},
            )
        if int(isolation["brief_count"]) != len(
            _sequence(value["brief_ids"], "brief_ids")
        ):
            _fail(
                "ISOLATION_UNMEASURED",
                "the isolation report must cover every first-round brief",
            )
    if _hash_excluding(value, "dispatch_hash") != value["dispatch_hash"]:
        _fail("DISPATCH_HASH_MISMATCH", "dispatch_hash does not match its content")
    return SealedArtifact("ParliamentDispatch", _canonical_json(value))


def seal_brief(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Stamp a CouncilBrief with its canonical content hash."""

    value = _mapping(payload, "CouncilBrief")
    _exact_fields(value, BRIEF_FIELDS, "CouncilBrief")
    value["brief_hash"] = _hash_excluding(value, "brief_hash")
    return value
