"""Q01 gold-corpus validation and inter-annotator agreement.

A benchmark that contains only clear positives measures nothing useful: it
cannot tell a system that recognises insight from one that says yes.  So the
corpus must carry true insights, false insights, and boundary cases, and each
boundary case must state the condition that makes it a boundary rather than
merely being hard.

Agreement is measured, not asserted.  Every case is annotated independently by
at least two annotators; where they disagree, an adjudicator who is neither of
them must resolve it with a typed reason, and the gold label must be the one
that survived adjudication.  Fleiss' kappa is computed over the raw annotations
and compared against a declared floor, so "the annotators agreed" is a number a
reader can check rather than a claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final

RFC3339_PATTERN: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
#: The corpus file this validator governs.
CORPUS_RELATIVE_PATH: Final = "evals/gold/insight_gold_cases.json"
#: The protocol the corpus must cite.
MANUAL_RELATIVE_PATH: Final = "docs/annotation_manual.md"


class CaseClass(str, Enum):
    """What a gold case is there to discriminate."""

    TRUE_INSIGHT = "TRUE_INSIGHT"
    FALSE_INSIGHT = "FALSE_INSIGHT"
    BOUNDARY = "BOUNDARY"


class Resolution(str, Enum):
    """How an adjudicator resolved a disagreement."""

    ANNOTATOR_A_CORRECT = "ANNOTATOR_A_CORRECT"
    ANNOTATOR_B_CORRECT = "ANNOTATOR_B_CORRECT"
    NEITHER_CORRECT = "NEITHER_CORRECT"
    GUIDANCE_AMBIGUOUS = "GUIDANCE_AMBIGUOUS"


CASE_CLASSES: Final = tuple(entry.value for entry in CaseClass)
RESOLUTIONS: Final = tuple(entry.value for entry in Resolution)
#: Fewer independent annotators than this cannot show agreement at all.
MINIMUM_ANNOTATORS: Final = 2
#: Fewer cases of a class than this cannot discriminate anything.
MINIMUM_CASES_PER_CLASS: Final = 3
#: Below this, the label is not reproducible enough to be a benchmark.
KAPPA_FLOOR: Final = 0.60

CORPUS_FIELDS: Final = frozenset(
    {"corpus_id", "corpus_version", "annotation_manual", "kappa_floor", "cases"}
)
CASE_FIELDS: Final = frozenset(
    {
        "case_id",
        "case_class",
        "statement",
        "source_spans",
        "boundary_condition",
        "annotations",
        "adjudication",
        "gold_label",
    }
)
_ANNOTATION_FIELDS: Final = frozenset({"annotator_id", "label", "rationale_ref"})
_ADJUDICATION_FIELDS: Final = frozenset(
    {"adjudicator_id", "resolution", "reason", "decided_at"}
)


class GoldCorpusError(ValueError):
    """Typed fail-closed Q01 contract error."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context) if context is not None else {}


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> Any:
    raise GoldCorpusError(code, message, context)


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


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


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


def load_corpus(repository_root: Path) -> dict[str, Any]:
    """Read the gold corpus from its canonical location."""

    path = Path(repository_root) / CORPUS_RELATIVE_PATH
    if not path.is_file():
        _fail("CORPUS_MISSING", f"no gold corpus at {CORPUS_RELATIVE_PATH}")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_case(value: object, index: int) -> dict[str, Any]:
    case = _mapping(value, f"cases[{index}]")
    _exact_fields(case, CASE_FIELDS, f"cases[{index}]")
    case_id = _text(case["case_id"], "case_id")
    case_class = _text(case["case_class"], "case_class")
    if case_class not in CASE_CLASSES:
        _fail(
            "CASE_CLASS_INVALID",
            "a gold case must declare a canonical class",
            {"case_id": case_id, "value": case_class},
        )
    spans = _sequence(case["source_spans"], "source_spans")
    if not spans:
        _fail(
            "CASE_UNGROUNDED",
            "a gold case must cite at least one source span",
            {"case_id": case_id},
        )
    boundary = case["boundary_condition"]
    if case_class == CaseClass.BOUNDARY.value:
        boundary = _text(boundary, "boundary_condition")
    elif boundary is not None:
        _fail(
            "BOUNDARY_CONDITION_UNEXPECTED",
            "only a boundary case states the condition that makes it one",
            {"case_id": case_id},
        )

    annotations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, entry in enumerate(_sequence(case["annotations"], "annotations")):
        annotation = _mapping(entry, f"{case_id}.annotations[{position}]")
        _exact_fields(annotation, _ANNOTATION_FIELDS, "annotation")
        annotator = _text(annotation["annotator_id"], "annotator_id")
        if annotator in seen:
            _fail(
                "ANNOTATOR_DUPLICATED",
                "one annotator may label a case only once",
                {"annotator_id": annotator, "case_id": case_id},
            )
        seen.add(annotator)
        label = _text(annotation["label"], "label")
        if label not in CASE_CLASSES:
            _fail(
                "LABEL_INVALID",
                "an annotation label must be a canonical case class",
                {"case_id": case_id, "value": label},
            )
        annotations.append(
            {
                "annotator_id": annotator,
                "label": label,
                "rationale_ref": _text(annotation["rationale_ref"], "rationale_ref"),
            }
        )
    if len(annotations) < MINIMUM_ANNOTATORS:
        _fail(
            "INSUFFICIENT_ANNOTATORS",
            "a gold case needs at least two independent annotations",
            {"annotator_count": len(annotations), "case_id": case_id},
        )
    annotations.sort(key=lambda entry: entry["annotator_id"])

    labels = {entry["label"] for entry in annotations}
    adjudication = case["adjudication"]
    if len(labels) > 1:
        if adjudication is None:
            _fail(
                "DISAGREEMENT_UNADJUDICATED",
                "annotators disagreed and nobody adjudicated",
                {"case_id": case_id, "labels": sorted(labels)},
            )
        record = _mapping(adjudication, "adjudication")
        _exact_fields(record, _ADJUDICATION_FIELDS, "adjudication")
        adjudicator = _text(record["adjudicator_id"], "adjudicator_id")
        if adjudicator in seen:
            _fail(
                "ADJUDICATOR_NOT_INDEPENDENT",
                "an annotator may not adjudicate its own disagreement",
                {"adjudicator_id": adjudicator, "case_id": case_id},
            )
        resolution = _text(record["resolution"], "resolution")
        if resolution not in RESOLUTIONS:
            _fail(
                "RESOLUTION_INVALID",
                "an adjudication must use a canonical resolution",
                {"case_id": case_id, "value": resolution},
            )
        adjudication = {
            "adjudicator_id": adjudicator,
            "decided_at": _timestamp(record["decided_at"], "decided_at"),
            "reason": _text(record["reason"], "reason"),
            "resolution": resolution,
        }
    elif adjudication is not None:
        _fail(
            "ADJUDICATION_UNEXPECTED",
            "an unanimous case has nothing to adjudicate",
            {"case_id": case_id},
        )

    gold = _text(case["gold_label"], "gold_label")
    if gold not in CASE_CLASSES:
        _fail(
            "LABEL_INVALID",
            "the gold label must be a canonical case class",
            {"case_id": case_id, "value": gold},
        )
    if gold != case_class:
        _fail(
            "GOLD_LABEL_INCONSISTENT",
            "the gold label must equal the class the case is filed under",
            {"case_class": case_class, "case_id": case_id, "gold_label": gold},
        )
    if len(labels) == 1 and gold not in labels:
        _fail(
            "GOLD_LABEL_UNSUPPORTED",
            "a unanimous case must take the label its annotators gave",
            {"case_id": case_id, "gold_label": gold},
        )
    return {
        "adjudication": adjudication,
        "annotations": annotations,
        "boundary_condition": boundary,
        "case_class": case_class,
        "case_id": case_id,
        "gold_label": gold,
        "source_spans": [_text(entry, "source_span") for entry in spans],
        "statement": _text(case["statement"], "statement"),
    }


def fleiss_kappa(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Fleiss' kappa over the raw annotations, with its inputs exposed.

    Reported with the observed and expected agreement it was computed from, so
    a reader can recompute it rather than take the coefficient on trust.  A
    corpus whose annotators all used one label has no variance to measure and is
    reported as undefined rather than as perfect.
    """

    usable = [case for case in cases if len(case["annotations"]) >= MINIMUM_ANNOTATORS]
    if not usable:
        return {
            "case_count": 0,
            "expected_agreement": None,
            "kappa": None,
            "observed_agreement": None,
            "reason": "no case carries enough annotations",
        }
    raters = {len(case["annotations"]) for case in usable}
    if len(raters) != 1:
        return {
            "case_count": len(usable),
            "expected_agreement": None,
            "kappa": None,
            "observed_agreement": None,
            "reason": "Fleiss' kappa needs the same number of raters per case",
        }
    rater_count = raters.pop()
    if rater_count < 2:  # pragma: no cover - guarded by MINIMUM_ANNOTATORS
        return {
            "case_count": len(usable),
            "expected_agreement": None,
            "kappa": None,
            "observed_agreement": None,
            "reason": "at least two raters are required",
        }
    totals = dict.fromkeys(CASE_CLASSES, 0)
    agreements = []
    for case in usable:
        counts = dict.fromkeys(CASE_CLASSES, 0)
        for annotation in case["annotations"]:
            counts[annotation["label"]] += 1
            totals[annotation["label"]] += 1
        agreements.append(
            (sum(count * count for count in counts.values()) - rater_count)
            / (rater_count * (rater_count - 1))
        )
    observed = sum(agreements) / len(agreements)
    denominator = len(usable) * rater_count
    proportions = {label: count / denominator for label, count in totals.items()}
    expected = sum(value * value for value in proportions.values())
    if expected >= 1.0:
        return {
            "case_count": len(usable),
            "expected_agreement": round(expected, 10),
            "kappa": None,
            "observed_agreement": round(observed, 10),
            "reason": "every annotation used one label, so there is no variance",
        }
    return {
        "case_count": len(usable),
        "expected_agreement": round(expected, 10),
        "kappa": round((observed - expected) / (1.0 - expected), 10),
        "label_proportions": {
            label: round(value, 10) for label, value in sorted(proportions.items())
        },
        "observed_agreement": round(observed, 10),
        "rater_count": rater_count,
        "reason": None,
    }


def validate_corpus(payload: Mapping[str, Any]) -> SealedArtifact:
    """Validate the corpus: coverage, annotation, adjudication, and agreement."""

    value = _mapping(payload, "GoldCorpus")
    _exact_fields(value, CORPUS_FIELDS, "GoldCorpus")
    _text(value["corpus_id"], "corpus_id")
    _text(value["corpus_version"], "corpus_version")
    manual = _text(value["annotation_manual"], "annotation_manual")
    if manual != MANUAL_RELATIVE_PATH:
        _fail(
            "MANUAL_UNBOUND",
            "the corpus must cite the annotation manual it was labelled under",
            {"annotation_manual": manual},
        )
    floor = value["kappa_floor"]
    if type(floor) not in (int, float) or isinstance(floor, bool):
        _fail("INPUT_INVALID", "kappa_floor must be a number")
    if float(floor) < KAPPA_FLOOR:
        _fail(
            "KAPPA_FLOOR_TOO_LOW",
            "the declared floor may not be weaker than the contract floor",
            {"contract_floor": KAPPA_FLOOR, "declared": float(floor)},
        )

    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(_sequence(value["cases"], "cases")):
        case = _validate_case(entry, index)
        if case["case_id"] in seen:
            _fail(
                "DUPLICATE_CASE",
                "case ids must be unique",
                {"case_id": case["case_id"]},
            )
        seen.add(case["case_id"])
        cases.append(case)
    cases.sort(key=lambda case: case["case_id"])

    coverage = {
        label: sorted(case["case_id"] for case in cases if case["case_class"] == label)
        for label in CASE_CLASSES
    }
    thin = sorted(
        label for label, ids in coverage.items() if len(ids) < MINIMUM_CASES_PER_CLASS
    )
    if thin:
        _fail(
            "CASE_CLASS_MISSING",
            "true, false, and boundary cases must each be represented",
            {
                "classes": thin,
                "counts": {label: len(ids) for label, ids in coverage.items()},
                "minimum": MINIMUM_CASES_PER_CLASS,
            },
        )

    agreement = fleiss_kappa(cases)
    if agreement["kappa"] is None:
        _fail(
            "AGREEMENT_UNMEASURED",
            "inter-annotator agreement must be computable for this corpus",
            {"reason": agreement["reason"]},
        )
    if agreement["kappa"] < float(floor):
        _fail(
            "AGREEMENT_BELOW_FLOOR",
            "the labels are not reproducible enough to serve as a benchmark",
            {"floor": float(floor), "kappa": agreement["kappa"]},
        )

    adjudicated = sorted(
        case["case_id"] for case in cases if case["adjudication"] is not None
    )
    report = {
        "adjudicated_case_ids": adjudicated,
        "agreement": agreement,
        "annotation_manual": manual,
        "case_count": len(cases),
        "cases": cases,
        "coverage": {label: len(ids) for label, ids in coverage.items()},
        "corpus_id": value["corpus_id"],
        "corpus_version": value["corpus_version"],
        "kappa_floor": float(floor),
    }
    report["corpus_hash"] = _digest(report)
    return SealedArtifact("GoldCorpusReport", _canonical_json(report))


def validate_repository_corpus(repository_root: Path) -> SealedArtifact:
    """Validate the corpus as it is committed."""

    return validate_corpus(load_corpus(repository_root))
