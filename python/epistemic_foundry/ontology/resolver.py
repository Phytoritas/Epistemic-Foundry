"""Deterministic I03 ontology and measurement-identity resolution.

An upstream model may propose terms, candidates, or explanations, but it does
not own a mapping.  This component only resolves an exact normalized label
against a pinned ontology/DomainPack catalog when the structural context makes
one entry uniquely viable.  It never uses string similarity, never collapses
distinct construct identifiers, and abstains when the authority or context is
insufficient.

The immutable types in this module are component-local execution contracts.
They do not add a canonical JSON Schema, issue a HumanDecision, or claim that a
review queue item is an approval.  Human approval remains an external,
versioned authority action.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final, Mapping


ONTOLOGY_RESOLVER_VERSION: Final = "4.0.0-i03.1"

_SHA256_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEMVER_PATTERN: Final = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$"
)


class OntologyContractError(ValueError):
    """Typed fail-closed error at the I03 component boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = MappingProxyType(dict(details)) if details is not None else None


def _fail(
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> None:
    raise OntologyContractError(code, message, details)


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or "\x00" in value:
        _fail("ONTOLOGY_INPUT_INVALID", f"{label} must be a non-empty NUL-free string")
    normalized = " ".join(value.strip().split())
    try:
        normalized.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise OntologyContractError(
            "ONTOLOGY_INPUT_INVALID",
            f"{label} must contain Unicode scalar values",
        ) from error
    return normalized


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _label_key(value: object, label: str) -> str:
    # Compatibility normalization only: no edit distance, stemming, synonym
    # expansion, embedding, or other similarity authority is introduced.
    return unicodedata.normalize("NFKC", _text(value, label)).casefold()


def _exact_enum(value: object, enum_type: type[Enum], label: str) -> None:
    if type(value) is not enum_type:
        _fail(
            "ONTOLOGY_INPUT_INVALID",
            f"{label} must use the closed {enum_type.__name__} vocabulary",
        )


def _text_tuple(
    value: object,
    label: str,
    *,
    minimum: int = 0,
    label_semantics: bool = False,
) -> tuple[str, ...]:
    if type(value) is not tuple or len(value) < minimum:
        _fail(
            "ONTOLOGY_INPUT_INVALID",
            f"{label} must be an immutable tuple with at least {minimum} item(s)",
        )
    normalized = tuple(_text(item, f"{label}[{index}]") for index, item in enumerate(value))
    keys = (
        tuple(_label_key(item, f"{label}[{index}]") for index, item in enumerate(normalized))
        if label_semantics
        else normalized
    )
    if len(set(keys)) != len(keys):
        _fail("ONTOLOGY_INPUT_DUPLICATE", f"{label} contains duplicate values")
    return normalized


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


class OntologyEntityKind(str, Enum):
    CONCEPT = "CONCEPT"
    LATENT_CONSTRUCT = "LATENT_CONSTRUCT"
    VARIABLE = "VARIABLE"
    OPERATIONAL_MEASURE = "OPERATIONAL_MEASURE"
    METHOD = "METHOD"
    UNIT = "UNIT"
    PROXY_RELATION = "PROXY_RELATION"


class MappingImpact(str, Enum):
    ROUTINE = "ROUTINE"
    HIGH_IMPACT = "HIGH_IMPACT"


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class CompatibilityStatus(str, Enum):
    DIRECTLY_COMPARABLE = "DIRECTLY_COMPARABLE"
    CONVERTIBLE = "CONVERTIBLE"
    WITHIN_METHOD_ONLY = "WITHIN_METHOD_ONLY"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    UNKNOWN = "UNKNOWN"


class ConstructEquivalence(str, Enum):
    SAME = "SAME"
    PARTIAL = "PARTIAL"
    DIFFERENT = "DIFFERENT"
    UNKNOWN = "UNKNOWN"


class PromotionCeiling(str, Enum):
    NO_RESTRICTION = "NO_RESTRICTION"
    CONDITIONAL_ONLY = "CONDITIONAL_ONLY"
    METHOD_BOUNDARY_ONLY = "METHOD_BOUNDARY_ONLY"
    BLOCK_AGGREGATION = "BLOCK_AGGREGATION"


@dataclass(frozen=True, slots=True)
class ContextConstraints:
    """Exact structural conditions under which one ontology entry is viable."""

    method_ids: tuple[str, ...] = ()
    units: tuple[str, ...] = ()
    population_or_entities: tuple[str, ...] = ()
    units_of_analysis: tuple[str, ...] = ()
    sections: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in (
            "method_ids",
            "units",
            "population_or_entities",
            "units_of_analysis",
            "sections",
        ):
            values = _text_tuple(getattr(self, field), f"ContextConstraints.{field}")
            object.__setattr__(self, field, tuple(sorted(values)))


@dataclass(frozen=True, slots=True)
class OntologyEntry:
    construct_id: str
    entity_kind: OntologyEntityKind
    canonical_label: str
    aliases: tuple[str, ...]
    definition: str
    ontology_version: str
    domain_pack_id: str
    domain_pack_version: str
    authority_ref: str
    constraints: ContextConstraints = ContextConstraints()

    def __post_init__(self) -> None:
        object.__setattr__(self, "construct_id", _text(self.construct_id, "construct_id"))
        _exact_enum(self.entity_kind, OntologyEntityKind, "entity_kind")
        canonical = _text(self.canonical_label, "canonical_label")
        aliases = _text_tuple(self.aliases, "aliases", label_semantics=True)
        if _label_key(canonical, "canonical_label") in {
            _label_key(alias, "alias") for alias in aliases
        }:
            _fail(
                "ONTOLOGY_INPUT_DUPLICATE",
                "canonical_label must not be repeated in aliases",
                {"construct_id": self.construct_id},
            )
        object.__setattr__(self, "canonical_label", canonical)
        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "definition", _text(self.definition, "definition"))
        object.__setattr__(
            self,
            "ontology_version",
            _text(self.ontology_version, "ontology_version"),
        )
        object.__setattr__(self, "domain_pack_id", _text(self.domain_pack_id, "domain_pack_id"))
        version = _text(self.domain_pack_version, "domain_pack_version")
        if _SEMVER_PATTERN.fullmatch(version) is None:
            _fail("ONTOLOGY_INPUT_INVALID", "domain_pack_version must be an exact semantic version")
        object.__setattr__(self, "domain_pack_version", version)
        object.__setattr__(self, "authority_ref", _text(self.authority_ref, "authority_ref"))
        if type(self.constraints) is not ContextConstraints:
            _fail("ONTOLOGY_INPUT_INVALID", "constraints must be exactly ContextConstraints")

    @property
    def normalized_labels(self) -> frozenset[str]:
        return frozenset(
            _label_key(label, "label") for label in (self.canonical_label, *self.aliases)
        )


@dataclass(frozen=True, slots=True)
class MappingContext:
    raw_term: str
    sentence_context: str
    method_id: str | None
    unit: str | None
    population_or_entity: str | None
    unit_of_analysis: str | None
    section: str | None
    ontology_version: str
    domain_pack_id: str
    domain_pack_version: str
    occurrence_count: int
    impact: MappingImpact

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_term", _text(self.raw_term, "raw_term"))
        object.__setattr__(
            self,
            "sentence_context",
            _text(self.sentence_context, "sentence_context"),
        )
        for field in (
            "method_id",
            "unit",
            "population_or_entity",
            "unit_of_analysis",
            "section",
        ):
            object.__setattr__(
                self,
                field,
                _optional_text(getattr(self, field), f"MappingContext.{field}"),
            )
        object.__setattr__(
            self,
            "ontology_version",
            _text(self.ontology_version, "ontology_version"),
        )
        object.__setattr__(self, "domain_pack_id", _text(self.domain_pack_id, "domain_pack_id"))
        version = _text(self.domain_pack_version, "domain_pack_version")
        if _SEMVER_PATTERN.fullmatch(version) is None:
            _fail("ONTOLOGY_INPUT_INVALID", "domain_pack_version must be an exact semantic version")
        object.__setattr__(self, "domain_pack_version", version)
        if type(self.occurrence_count) is not int or self.occurrence_count < 1:
            _fail("ONTOLOGY_INPUT_INVALID", "occurrence_count must be a positive integer")
        _exact_enum(self.impact, MappingImpact, "impact")

    @property
    def mapping_key_hash(self) -> str:
        return _hash(
            {
                "domain_pack_id": self.domain_pack_id,
                "domain_pack_version": self.domain_pack_version,
                "method_id": self.method_id,
                "ontology_version": self.ontology_version,
                "population_or_entity": self.population_or_entity,
                "raw_term": self.raw_term,
                "section": self.section,
                "sentence_context": self.sentence_context,
                "unit": self.unit,
                "unit_of_analysis": self.unit_of_analysis,
            }
        )


@dataclass(frozen=True, slots=True)
class ResolutionPolicy:
    policy_version: str
    high_frequency_threshold: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_version", _text(self.policy_version, "policy_version"))
        if type(self.high_frequency_threshold) is not int or self.high_frequency_threshold < 1:
            _fail(
                "ONTOLOGY_INPUT_INVALID",
                "high_frequency_threshold must be a positive integer",
            )


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    construct_id: str
    entity_kind: OntologyEntityKind
    canonical_label: str
    authority_ref: str
    viable: bool
    matched_dimensions: tuple[str, ...]
    missing_dimensions: tuple[str, ...]
    conflicting_dimensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MappingReviewItem:
    review_item_id: str
    mapping_key_hash: str
    candidate_construct_ids: tuple[str, ...]
    proposed_construct_id: str | None
    reasons: tuple[str, ...]
    policy_version: str
    required_authority_artifact: str = "HumanDecision"


@dataclass(frozen=True, slots=True)
class OntologyResolution:
    resolver_version: str
    mapping_key_hash: str
    status: ResolutionStatus
    selected_construct_id: str | None
    proposed_construct_id: str | None
    candidates: tuple[CandidateAssessment, ...]
    abstention_reasons: tuple[str, ...]
    review_queue_items: tuple[MappingReviewItem, ...]


_CONSTRAINT_FIELDS: Final = (
    ("method_ids", "method_id"),
    ("units", "unit"),
    ("population_or_entities", "population_or_entity"),
    ("units_of_analysis", "unit_of_analysis"),
    ("sections", "section"),
)


def _assess(entry: OntologyEntry, context: MappingContext) -> CandidateAssessment:
    matched: list[str] = []
    missing: list[str] = []
    conflicting: list[str] = []
    for constraint_field, context_field in _CONSTRAINT_FIELDS:
        allowed = getattr(entry.constraints, constraint_field)
        if not allowed:
            continue
        actual = getattr(context, context_field)
        if actual is None:
            missing.append(context_field)
        elif actual in allowed:
            matched.append(context_field)
        else:
            conflicting.append(context_field)
    return CandidateAssessment(
        construct_id=entry.construct_id,
        entity_kind=entry.entity_kind,
        canonical_label=entry.canonical_label,
        authority_ref=entry.authority_ref,
        viable=not conflicting,
        matched_dimensions=tuple(sorted(matched)),
        missing_dimensions=tuple(sorted(missing)),
        conflicting_dimensions=tuple(sorted(conflicting)),
    )


def _review_item(
    *,
    context: MappingContext,
    policy: ResolutionPolicy,
    candidates: tuple[CandidateAssessment, ...],
    proposed_construct_id: str | None,
    semantic_reasons: tuple[str, ...],
) -> MappingReviewItem:
    reasons = list(semantic_reasons)
    if context.impact is MappingImpact.HIGH_IMPACT:
        reasons.append("HIGH_IMPACT")
    if context.occurrence_count >= policy.high_frequency_threshold:
        reasons.append("HIGH_FREQUENCY")
    ordered_reasons = tuple(sorted(set(reasons)))
    candidate_ids = tuple(sorted(candidate.construct_id for candidate in candidates))
    preimage = {
        "candidate_construct_ids": list(candidate_ids),
        "mapping_key_hash": context.mapping_key_hash,
        "policy_version": policy.policy_version,
        "proposed_construct_id": proposed_construct_id,
        "reasons": list(ordered_reasons),
        "resolver_version": ONTOLOGY_RESOLVER_VERSION,
    }
    return MappingReviewItem(
        review_item_id="ORQ-" + _hash(preimage).removeprefix("sha256:"),
        mapping_key_hash=context.mapping_key_hash,
        candidate_construct_ids=candidate_ids,
        proposed_construct_id=proposed_construct_id,
        reasons=ordered_reasons,
        policy_version=policy.policy_version,
    )


def resolve_construct(
    *,
    context: MappingContext,
    catalog: tuple[OntologyEntry, ...],
    policy: ResolutionPolicy,
) -> OntologyResolution:
    """Resolve one term or abstain without turning similarity into authority."""

    if type(context) is not MappingContext or type(policy) is not ResolutionPolicy:
        _fail("ONTOLOGY_INPUT_INVALID", "context and policy must use exact I03 types")
    if type(catalog) is not tuple or any(type(entry) is not OntologyEntry for entry in catalog):
        _fail("ONTOLOGY_INPUT_INVALID", "catalog must be an immutable tuple of OntologyEntry")
    identifiers = [entry.construct_id for entry in catalog]
    if len(set(identifiers)) != len(identifiers):
        _fail("ONTOLOGY_CATALOG_DUPLICATE_ID", "catalog contains duplicate construct IDs")

    authority_entries = tuple(
        entry
        for entry in catalog
        if entry.ontology_version == context.ontology_version
        and entry.domain_pack_id == context.domain_pack_id
        and entry.domain_pack_version == context.domain_pack_version
    )
    if not authority_entries:
        _fail(
            "ONTOLOGY_AUTHORITY_UNAVAILABLE",
            "the pinned ontology and DomainPack have no catalog entries",
            {
                "ontology_version": context.ontology_version,
                "domain_pack_id": context.domain_pack_id,
                "domain_pack_version": context.domain_pack_version,
            },
        )

    raw_key = _label_key(context.raw_term, "raw_term")
    label_matches = tuple(
        sorted(
            (entry for entry in authority_entries if raw_key in entry.normalized_labels),
            key=lambda entry: entry.construct_id,
        )
    )
    assessments = tuple(_assess(entry, context) for entry in label_matches)
    viable = tuple(candidate for candidate in assessments if candidate.viable)
    complete = tuple(candidate for candidate in viable if not candidate.missing_dimensions)
    high_review = (
        context.impact is MappingImpact.HIGH_IMPACT
        or context.occurrence_count >= policy.high_frequency_threshold
    )

    selected: str | None = None
    proposed: str | None = None
    review: tuple[MappingReviewItem, ...] = ()
    reasons: tuple[str, ...]

    if not label_matches:
        status = ResolutionStatus.UNKNOWN
        reasons = ("NO_EXACT_LABEL_MATCH",)
        if high_review:
            review = (
                _review_item(
                    context=context,
                    policy=policy,
                    candidates=(),
                    proposed_construct_id=None,
                    semantic_reasons=("UNKNOWN_TERM",),
                ),
            )
    elif not viable:
        status = ResolutionStatus.UNKNOWN
        reasons = ("ALL_LABEL_MATCHES_CONFLICT_WITH_CONTEXT",)
        if high_review:
            review = (
                _review_item(
                    context=context,
                    policy=policy,
                    candidates=assessments,
                    proposed_construct_id=None,
                    semantic_reasons=("CONTEXT_CONFLICT",),
                ),
            )
    elif len(viable) != 1 or len(complete) != 1:
        status = ResolutionStatus.AMBIGUOUS
        semantic = ["MULTIPLE_VIABLE_CONSTRUCTS"] if len(viable) > 1 else []
        if any(candidate.missing_dimensions for candidate in viable):
            semantic.append("INSUFFICIENT_CONTEXT")
        reasons = tuple(sorted(semantic)) or ("AMBIGUOUS_MAPPING",)
        if high_review:
            review = (
                _review_item(
                    context=context,
                    policy=policy,
                    candidates=viable,
                    proposed_construct_id=None,
                    semantic_reasons=reasons,
                ),
            )
    else:
        proposed = complete[0].construct_id
        if high_review:
            status = ResolutionStatus.PENDING_APPROVAL
            reasons = ("HUMAN_APPROVAL_REQUIRED",)
            review = (
                _review_item(
                    context=context,
                    policy=policy,
                    candidates=complete,
                    proposed_construct_id=proposed,
                    semantic_reasons=("MAPPING_REVIEW",),
                ),
            )
        else:
            status = ResolutionStatus.RESOLVED
            selected = proposed
            reasons = ()

    return OntologyResolution(
        resolver_version=ONTOLOGY_RESOLVER_VERSION,
        mapping_key_hash=context.mapping_key_hash,
        status=status,
        selected_construct_id=selected,
        proposed_construct_id=proposed,
        candidates=assessments,
        abstention_reasons=reasons,
        review_queue_items=review,
    )


@dataclass(frozen=True, slots=True)
class MeasurementIdentity:
    """Method- and scope-conditioned identity of an operational measurement."""

    measurement_id: str
    construct_id: str
    method_id: str
    protocol_version: str | None
    unit: str | None
    timing: str | None
    calibration_ref: str | None
    population_or_entity: str | None
    unit_of_analysis: str | None
    ontology_version: str
    domain_pack_id: str | None
    domain_pack_version: str | None
    proxy_for_construct_id: str | None = None

    def __post_init__(self) -> None:
        for field in ("measurement_id", "construct_id", "method_id", "ontology_version"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        for field in (
            "protocol_version",
            "unit",
            "timing",
            "calibration_ref",
            "population_or_entity",
            "unit_of_analysis",
            "domain_pack_id",
            "domain_pack_version",
            "proxy_for_construct_id",
        ):
            object.__setattr__(self, field, _optional_text(getattr(self, field), field))
        if (self.domain_pack_id is None) != (self.domain_pack_version is None):
            _fail(
                "MEASUREMENT_IDENTITY_INVALID",
                "domain_pack_id and domain_pack_version must both be present or both be null",
            )
        if self.domain_pack_version is not None and _SEMVER_PATTERN.fullmatch(
            self.domain_pack_version
        ) is None:
            _fail(
                "MEASUREMENT_IDENTITY_INVALID",
                "domain_pack_version must be an exact semantic version",
            )

    @property
    def semantic_identity_hash(self) -> str:
        return _hash(
            {
                "calibration_ref": self.calibration_ref,
                "construct_id": self.construct_id,
                "domain_pack_id": self.domain_pack_id,
                "domain_pack_version": self.domain_pack_version,
                "method_id": self.method_id,
                "ontology_version": self.ontology_version,
                "population_or_entity": self.population_or_entity,
                "protocol_version": self.protocol_version,
                "proxy_for_construct_id": self.proxy_for_construct_id,
                "timing": self.timing,
                "unit": self.unit,
                "unit_of_analysis": self.unit_of_analysis,
            }
        )


@dataclass(frozen=True, slots=True)
class MeasurementBridge:
    """An explicit, direction-bound compatibility assertion from external authority."""

    bridge_id: str
    left_identity_hash: str
    right_identity_hash: str
    compatibility_status: CompatibilityStatus
    construct_equivalence: ConstructEquivalence
    required_transformations: tuple[str, ...]
    method_threats: tuple[str, ...]
    promotion_ceiling: PromotionCeiling
    authority_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "bridge_id", _text(self.bridge_id, "bridge_id"))
        object.__setattr__(self, "authority_ref", _text(self.authority_ref, "authority_ref"))
        for field in ("left_identity_hash", "right_identity_hash"):
            value = _text(getattr(self, field), field)
            if _SHA256_PATTERN.fullmatch(value) is None:
                _fail("MEASUREMENT_BRIDGE_INVALID", f"{field} must be a canonical SHA-256")
            object.__setattr__(self, field, value)
        _exact_enum(self.compatibility_status, CompatibilityStatus, "compatibility_status")
        _exact_enum(self.construct_equivalence, ConstructEquivalence, "construct_equivalence")
        _exact_enum(self.promotion_ceiling, PromotionCeiling, "promotion_ceiling")
        transformations = _text_tuple(
            self.required_transformations,
            "required_transformations",
        )
        threats = _text_tuple(self.method_threats, "method_threats")
        object.__setattr__(self, "required_transformations", tuple(sorted(transformations)))
        object.__setattr__(self, "method_threats", tuple(sorted(threats)))
        if self.compatibility_status is CompatibilityStatus.UNKNOWN:
            _fail("MEASUREMENT_BRIDGE_INVALID", "an explicit bridge cannot assert UNKNOWN")
        if self.compatibility_status is CompatibilityStatus.CONVERTIBLE and not transformations:
            _fail(
                "MEASUREMENT_BRIDGE_INVALID",
                "CONVERTIBLE requires at least one explicit transformation",
            )
        if self.compatibility_status is CompatibilityStatus.DIRECTLY_COMPARABLE and transformations:
            _fail(
                "MEASUREMENT_BRIDGE_INVALID",
                "DIRECTLY_COMPARABLE cannot require a transformation",
            )
        if self.promotion_ceiling is PromotionCeiling.NO_RESTRICTION and (
            self.construct_equivalence is not ConstructEquivalence.SAME
            or self.compatibility_status is not CompatibilityStatus.DIRECTLY_COMPARABLE
        ):
            _fail(
                "MEASUREMENT_BRIDGE_INVALID",
                "NO_RESTRICTION requires SAME and DIRECTLY_COMPARABLE",
            )
        if self.construct_equivalence in (
            ConstructEquivalence.PARTIAL,
            ConstructEquivalence.DIFFERENT,
            ConstructEquivalence.UNKNOWN,
        ) and self.promotion_ceiling is PromotionCeiling.NO_RESTRICTION:
            _fail(
                "MEASUREMENT_BRIDGE_INVALID",
                "non-identical constructs require a promotion ceiling",
            )


@dataclass(frozen=True, slots=True)
class MeasurementCompatibility:
    left_measurement_id: str
    right_measurement_id: str
    left_identity_hash: str
    right_identity_hash: str
    compatibility_status: CompatibilityStatus
    construct_equivalence: ConstructEquivalence
    required_transformations: tuple[str, ...]
    method_threats: tuple[str, ...]
    promotion_ceiling: PromotionCeiling
    bridge_id: str | None
    aggregation_allowed: bool


_IDENTITY_CRITICAL_FIELDS: Final = (
    "protocol_version",
    "unit",
    "timing",
    "calibration_ref",
    "population_or_entity",
    "unit_of_analysis",
)


def _compatibility(
    left: MeasurementIdentity,
    right: MeasurementIdentity,
    *,
    status: CompatibilityStatus,
    equivalence: ConstructEquivalence,
    transformations: tuple[str, ...] = (),
    threats: tuple[str, ...] = (),
    ceiling: PromotionCeiling,
    bridge_id: str | None = None,
) -> MeasurementCompatibility:
    return MeasurementCompatibility(
        left_measurement_id=left.measurement_id,
        right_measurement_id=right.measurement_id,
        left_identity_hash=left.semantic_identity_hash,
        right_identity_hash=right.semantic_identity_hash,
        compatibility_status=status,
        construct_equivalence=equivalence,
        required_transformations=tuple(sorted(transformations)),
        method_threats=tuple(sorted(threats)),
        promotion_ceiling=ceiling,
        bridge_id=bridge_id,
        aggregation_allowed=(
            equivalence is ConstructEquivalence.SAME
            and status
            in (
                CompatibilityStatus.DIRECTLY_COMPARABLE,
                CompatibilityStatus.CONVERTIBLE,
            )
            and ceiling
            in (
                PromotionCeiling.NO_RESTRICTION,
                PromotionCeiling.CONDITIONAL_ONLY,
            )
        ),
    )


def compare_measurements(
    left: MeasurementIdentity,
    right: MeasurementIdentity,
    *,
    bridges: tuple[MeasurementBridge, ...] = (),
) -> MeasurementCompatibility:
    """Compare exact measurement identities without implicit pooling or conversion."""

    if type(left) is not MeasurementIdentity or type(right) is not MeasurementIdentity:
        _fail("MEASUREMENT_INPUT_INVALID", "left and right must be MeasurementIdentity")
    if type(bridges) is not tuple or any(type(bridge) is not MeasurementBridge for bridge in bridges):
        _fail("MEASUREMENT_INPUT_INVALID", "bridges must be an immutable tuple")
    bridge_ids = [bridge.bridge_id for bridge in bridges]
    if len(set(bridge_ids)) != len(bridge_ids):
        _fail("MEASUREMENT_BRIDGE_DUPLICATE_ID", "bridge IDs must be unique")
    if (
        left.measurement_id == right.measurement_id
        and left.semantic_identity_hash != right.semantic_identity_hash
    ):
        _fail(
            "MEASUREMENT_IDENTITY_CONFLICT",
            "one measurement ID cannot name two semantic identities",
            {"measurement_id": left.measurement_id},
        )

    matching_bridges = tuple(
        bridge
        for bridge in bridges
        if bridge.left_identity_hash == left.semantic_identity_hash
        and bridge.right_identity_hash == right.semantic_identity_hash
    )
    if len(matching_bridges) > 1:
        _fail(
            "MEASUREMENT_BRIDGE_AMBIGUOUS",
            "multiple bridges claim authority for the same ordered identity pair",
        )
    if matching_bridges:
        bridge = matching_bridges[0]
        return _compatibility(
            left,
            right,
            status=bridge.compatibility_status,
            equivalence=bridge.construct_equivalence,
            transformations=bridge.required_transformations,
            threats=bridge.method_threats,
            ceiling=bridge.promotion_ceiling,
            bridge_id=bridge.bridge_id,
        )

    left_pack = (left.domain_pack_id, left.domain_pack_version, left.ontology_version)
    right_pack = (right.domain_pack_id, right.domain_pack_version, right.ontology_version)
    if left_pack != right_pack:
        return _compatibility(
            left,
            right,
            status=CompatibilityStatus.UNKNOWN,
            equivalence=ConstructEquivalence.UNKNOWN,
            threats=("ONTOLOGY_OR_DOMAIN_PACK_MISMATCH",),
            ceiling=PromotionCeiling.BLOCK_AGGREGATION,
        )
    if left.construct_id != right.construct_id:
        return _compatibility(
            left,
            right,
            status=CompatibilityStatus.NOT_COMPARABLE,
            equivalence=ConstructEquivalence.DIFFERENT,
            threats=("DISTINCT_CONSTRUCT_IDENTITIES",),
            ceiling=PromotionCeiling.BLOCK_AGGREGATION,
        )
    if left.proxy_for_construct_id != right.proxy_for_construct_id:
        return _compatibility(
            left,
            right,
            status=CompatibilityStatus.NOT_COMPARABLE,
            equivalence=ConstructEquivalence.PARTIAL,
            threats=("PROXY_RELATION_MISMATCH",),
            ceiling=PromotionCeiling.BLOCK_AGGREGATION,
        )

    missing = tuple(
        sorted(
            f"MISSING_{field.upper()}"
            for field in _IDENTITY_CRITICAL_FIELDS
            if getattr(left, field) is None or getattr(right, field) is None
        )
    )
    if missing:
        return _compatibility(
            left,
            right,
            status=CompatibilityStatus.UNKNOWN,
            equivalence=ConstructEquivalence.SAME,
            threats=missing,
            ceiling=PromotionCeiling.BLOCK_AGGREGATION,
        )

    for field, threat in (
        ("population_or_entity", "POPULATION_OR_ENTITY_MISMATCH"),
        ("unit_of_analysis", "UNIT_OF_ANALYSIS_MISMATCH"),
        ("timing", "TEMPORAL_SUPPORT_MISMATCH"),
        ("unit", "UNIT_MISMATCH_WITHOUT_BRIDGE"),
    ):
        if getattr(left, field) != getattr(right, field):
            return _compatibility(
                left,
                right,
                status=CompatibilityStatus.NOT_COMPARABLE,
                equivalence=ConstructEquivalence.SAME,
                threats=(threat,),
                ceiling=PromotionCeiling.BLOCK_AGGREGATION,
            )

    method_differences = tuple(
        threat
        for field, threat in (
            ("method_id", "METHOD_MISMATCH"),
            ("protocol_version", "PROTOCOL_VERSION_MISMATCH"),
            ("calibration_ref", "CALIBRATION_MISMATCH"),
        )
        if getattr(left, field) != getattr(right, field)
    )
    if method_differences:
        return _compatibility(
            left,
            right,
            status=CompatibilityStatus.WITHIN_METHOD_ONLY,
            equivalence=ConstructEquivalence.SAME,
            threats=method_differences,
            ceiling=PromotionCeiling.METHOD_BOUNDARY_ONLY,
        )

    if left.proxy_for_construct_id is not None:
        return _compatibility(
            left,
            right,
            status=CompatibilityStatus.DIRECTLY_COMPARABLE,
            equivalence=ConstructEquivalence.SAME,
            threats=("PROXY_DEFINED_OUTCOME_ONLY",),
            ceiling=PromotionCeiling.CONDITIONAL_ONLY,
        )
    return _compatibility(
        left,
        right,
        status=CompatibilityStatus.DIRECTLY_COMPARABLE,
        equivalence=ConstructEquivalence.SAME,
        ceiling=PromotionCeiling.NO_RESTRICTION,
    )


__all__ = [
    "ONTOLOGY_RESOLVER_VERSION",
    "CandidateAssessment",
    "CompatibilityStatus",
    "ConstructEquivalence",
    "ContextConstraints",
    "MappingContext",
    "MappingImpact",
    "MappingReviewItem",
    "MeasurementBridge",
    "MeasurementCompatibility",
    "MeasurementIdentity",
    "OntologyContractError",
    "OntologyEntry",
    "OntologyEntityKind",
    "OntologyResolution",
    "PromotionCeiling",
    "ResolutionPolicy",
    "ResolutionStatus",
    "compare_measurements",
    "resolve_construct",
]
