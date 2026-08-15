"""Q03 retrieval, verdict and calibration evaluation.

Counter and null recall are measured on their own, because they are exactly
what a retrieval system optimised for agreement will miss.  A run that returns
every supporting document and no refuting one can score well on undifferentiated
recall while being useless for adjudication, so recall is reported per evidence
polarity — supporting, counter, null — with the numerator, denominator and the
missed relevant ids beside each figure.

Calibration is computed, not claimed.  The Brier score and the expected
calibration error are derived from the same confidence/outcome pairs and
reported with the reliability bins they came from, so a reader can re-add the
bins and get the ECE back.  ``calibration_status`` follows the canonical
CalibrationReport vocabulary, and a sample too small to say anything is
``INSUFFICIENT_DATA`` rather than a flattering number.

Every vocabulary is read from its declaring schema: calibration targets and
statuses from ``schemas/calibration-report.schema.json``, and the emitted
report is validated against that schema so what this evaluator produces is a
CalibrationReport rather than something shaped like one.
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import jsonschema

#: The corpus file this evaluator governs.
CORPUS_RELATIVE_PATH: Final = "evals/retrieval_verdict/retrieval_verdict_cases.json"
CALIBRATION_SCHEMA_PATH: Final = "schemas/calibration-report.schema.json"
#: Evidence polarities recall is reported over.  Counter and null are separate
#: because an agreement-seeking retriever loses exactly those.
EVIDENCE_POLARITIES: Final = ("supporting", "counter", "null")
#: Polarities whose recall must be reported even when they are empty.
ADVERSARIAL_POLARITIES: Final = ("counter", "null")
#: Fewer graded predictions than this cannot support a calibration claim.
MINIMUM_CALIBRATION_SAMPLE: Final = 10
#: Ten equal-width bins over [0, 1]; the boundary count is the contract.
RELIABILITY_BIN_COUNT: Final = 10
#: Verdicts a case may carry.  A retrieval benchmark that cannot express
#: "the evidence does not decide" would force a verdict that is not there.
VERDICTS: Final = ("SUPPORTED", "REFUTED", "UNDETERMINED")

_CORPUS_FIELDS: Final = frozenset(
    {"corpus_id", "queries", "retriever_under_test", "verdict_cases", "version"}
)
_QUERY_FIELDS: Final = frozenset({"query_id", "relevant", "retrieved", "insight_id"})
_RELEVANT_FIELDS: Final = frozenset({"document_id", "polarity"})
_VERDICT_FIELDS: Final = frozenset(
    {"case_id", "confidence", "gold_verdict", "predicted_verdict", "query_id"}
)
_RETRIEVER_FIELDS: Final = frozenset({"name", "synthetic", "version"})


class RetrievalEvalError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    raise RetrievalEvalError(code, message, context)


@dataclass(frozen=True)
class SealedReport:
    """Immutable canonical JSON snapshot with a fresh projection on access."""

    _canonical_bytes: bytes

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self._canonical_bytes.decode("utf-8"))
        if type(value) is not dict:  # pragma: no cover - construction invariant
            raise AssertionError("sealed report is not an object")
        return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


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


def _probability(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("INPUT_INVALID", f"{label} must be a number")
    number = float(value)  # type: ignore[arg-type]
    if not 0.0 <= number <= 1.0:
        _fail("CONFIDENCE_OUT_OF_RANGE", f"{label} must lie in [0, 1]")
    return number


def _calibration_schema(repository_root: str | Path) -> dict[str, Any]:
    path = Path(repository_root) / CALIBRATION_SCHEMA_PATH
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail("SCHEMA_UNREADABLE", f"the calibration schema is unreadable: {error}")
        raise  # pragma: no cover - _fail always raises
    return _mapping(loaded, CALIBRATION_SCHEMA_PATH)


def calibration_targets(repository_root: str | Path) -> tuple[str, ...]:
    declared = (
        _calibration_schema(repository_root)
        .get("properties", {})
        .get("target", {})
        .get("enum")
    )
    if not isinstance(declared, list) or not declared:
        _fail("SCHEMA_UNREADABLE", "the calibration schema declares no target enum")
    return tuple(str(entry) for entry in declared)  # type: ignore[union-attr]


def calibration_statuses(repository_root: str | Path) -> tuple[str, ...]:
    declared = (
        _calibration_schema(repository_root)
        .get("properties", {})
        .get("calibration_status", {})
        .get("enum")
    )
    if not isinstance(declared, list) or not declared:
        _fail("SCHEMA_UNREADABLE", "the calibration schema declares no status enum")
    return tuple(str(entry) for entry in declared)  # type: ignore[union-attr]


def load_corpus(repository_root: str | Path) -> dict[str, Any]:
    path = Path(repository_root) / CORPUS_RELATIVE_PATH
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail("CORPUS_UNREADABLE", f"the corpus could not be read: {error}")
        raise  # pragma: no cover - _fail always raises
    return _mapping(loaded, "corpus")


def _validate_queries(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    queries: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(_sequence(payload["queries"], "queries")):
        query = _mapping(entry, f"queries[{index}]")
        _exact_fields(query, _QUERY_FIELDS, f"queries[{index}]")
        query_id = _text(query["query_id"], "query_id")
        if query_id in queries:
            _fail("DUPLICATE_QUERY", "query ids must be unique", {"query_id": query_id})
        relevant: dict[str, str] = {}
        for position, relevant_entry in enumerate(
            _sequence(query["relevant"], f"{query_id}.relevant")
        ):
            record = _mapping(relevant_entry, f"{query_id}.relevant[{position}]")
            _exact_fields(record, _RELEVANT_FIELDS, f"{query_id}.relevant[{position}]")
            document_id = _text(record["document_id"], "document_id")
            polarity = _text(record["polarity"], "polarity")
            if polarity not in EVIDENCE_POLARITIES:
                _fail(
                    "POLARITY_INVALID",
                    "a relevant document must carry a canonical polarity",
                    {"allowed": list(EVIDENCE_POLARITIES), "polarity": polarity},
                )
            if document_id in relevant:
                _fail(
                    "DUPLICATE_RELEVANT",
                    "a document may be relevant to a query only once",
                    {"document_id": document_id, "query_id": query_id},
                )
            relevant[document_id] = polarity
        if not relevant:
            _fail(
                "QUERY_UNGRADED",
                "a query with no relevant document measures nothing",
                {"query_id": query_id},
            )
        retrieved = [
            _text(value, "retrieved")
            for value in _sequence(query["retrieved"], f"{query_id}.retrieved")
        ]
        if len(set(retrieved)) != len(retrieved):
            _fail(
                "DUPLICATE_RETRIEVED",
                "a retrieval run must not return one document twice",
                {"query_id": query_id},
            )
        queries[query_id] = {
            "insight_id": _text(query["insight_id"], "insight_id"),
            "query_id": query_id,
            "relevant": relevant,
            "retrieved": retrieved,
        }
    if not queries:
        _fail("INPUT_INVALID", "the corpus carries no queries")
    return queries


def _recall_by_polarity(
    queries: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    found: dict[str, int] = dict.fromkeys(EVIDENCE_POLARITIES, 0)
    total: dict[str, int] = dict.fromkeys(EVIDENCE_POLARITIES, 0)
    missed: dict[str, list[str]] = {polarity: [] for polarity in EVIDENCE_POLARITIES}
    for query in queries.values():
        retrieved = set(query["retrieved"])
        for document_id, polarity in query["relevant"].items():
            total[polarity] += 1
            if document_id in retrieved:
                found[polarity] += 1
            else:
                missed[polarity].append(f"{query['query_id']}/{document_id}")
    empty = sorted(
        polarity for polarity in ADVERSARIAL_POLARITIES if total[polarity] == 0
    )
    if empty:
        _fail(
            "POLARITY_UNMEASURED",
            "counter and null recall cannot be measured on a corpus that "
            "carries none of that evidence",
            {"polarities": empty},
        )
    return {
        polarity: {
            "found": found[polarity],
            "missed_ids": sorted(missed[polarity]),
            "recall": (
                None if total[polarity] == 0 else found[polarity] / total[polarity]
            ),
            "relevant": total[polarity],
        }
        for polarity in EVIDENCE_POLARITIES
    }


def _validate_verdicts(
    payload: Mapping[str, Any], queries: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(_sequence(payload["verdict_cases"], "verdict_cases")):
        case = _mapping(entry, f"verdict_cases[{index}]")
        _exact_fields(case, _VERDICT_FIELDS, f"verdict_cases[{index}]")
        case_id = _text(case["case_id"], "case_id")
        if case_id in seen:
            _fail("DUPLICATE_CASE", "case ids must be unique", {"case_id": case_id})
        seen.add(case_id)
        query_id = _text(case["query_id"], "query_id")
        if query_id not in queries:
            _fail(
                "CASE_UNGROUNDED",
                "a verdict case must reference a query the corpus carries",
                {"case_id": case_id, "query_id": query_id},
            )
        for field in ("gold_verdict", "predicted_verdict"):
            if case[field] not in VERDICTS:
                _fail(
                    "VERDICT_INVALID",
                    f"{field} must be a canonical verdict",
                    {"allowed": list(VERDICTS), "case_id": case_id},
                )
        cases.append(
            {
                "case_id": case_id,
                "confidence": _probability(case["confidence"], "confidence"),
                "gold_verdict": str(case["gold_verdict"]),
                "predicted_verdict": str(case["predicted_verdict"]),
                "query_id": query_id,
            }
        )
    if not cases:
        _fail("INPUT_INVALID", "verdict_cases must not be empty")
    return cases


def reliability_bins(
    pairs: Sequence[tuple[float, bool]], bin_count: int = RELIABILITY_BIN_COUNT
) -> list[dict[str, Any]]:
    """Equal-width bins over [0, 1]; the top bin closes on 1.0."""

    boundaries = [index / bin_count for index in range(1, bin_count)]
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bin_count)]
    for confidence, correct in pairs:
        if 0.0 <= confidence <= 1.0:
            bucket_index = bisect_right(boundaries, confidence)
            buckets[bucket_index].append((confidence, correct))

    bins: list[dict[str, Any]] = []
    for index in range(bin_count):
        lower = index / bin_count
        upper = 1.0 if index == bin_count - 1 else (index + 1) / bin_count
        members = buckets[index]
        count = len(members)
        bins.append(
            {
                "count": count,
                "empirical_accuracy": (
                    None
                    if count == 0
                    else sum(1 for _, correct in members if correct) / count
                ),
                "lower": lower,
                "mean_confidence": (
                    None
                    if count == 0
                    else sum(confidence for confidence, _ in members) / count
                ),
                "upper": upper,
            }
        )
    return bins


def brier_score(pairs: Sequence[tuple[float, bool]]) -> float | None:
    if not pairs:
        return None
    return sum(
        (confidence - (1.0 if correct else 0.0)) ** 2 for confidence, correct in pairs
    ) / len(pairs)


def expected_calibration_error(
    pairs: Sequence[tuple[float, bool]], bins: Sequence[Mapping[str, Any]]
) -> float | None:
    if not pairs:
        return None
    total = len(pairs)
    return sum(
        (entry["count"] / total)
        * abs(float(entry["empirical_accuracy"]) - float(entry["mean_confidence"]))
        for entry in bins
        if entry["count"] > 0
    )


def evaluate_corpus(repository_root: str | Path) -> SealedReport:
    return evaluate(load_corpus(repository_root), repository_root)


def evaluate(payload: Mapping[str, Any], repository_root: str | Path) -> SealedReport:
    corpus = _mapping(payload, "corpus")
    _exact_fields(corpus, _CORPUS_FIELDS, "corpus")
    corpus_id = _text(corpus["corpus_id"], "corpus_id")
    version = _text(corpus["version"], "version")
    retriever = _mapping(corpus["retriever_under_test"], "retriever_under_test")
    _exact_fields(retriever, _RETRIEVER_FIELDS, "retriever_under_test")
    if retriever["synthetic"] is not True:
        _fail(
            "RETRIEVER_OVERCLAIM",
            "v1 retrieval results are a synthetic fixture; a corpus claiming a "
            "real retriever requires recorded runs",
        )

    queries = _validate_queries(corpus)
    recall = _recall_by_polarity(queries)
    cases = _validate_verdicts(corpus, queries)

    pairs = [
        (case["confidence"], case["predicted_verdict"] == case["gold_verdict"])
        for case in cases
    ]
    bins = reliability_bins(pairs)
    statuses = calibration_statuses(repository_root)
    targets = calibration_targets(repository_root)
    if "verdict" not in targets:
        _fail(
            "SCHEMA_UNREADABLE",
            "the calibration schema no longer declares the verdict target",
        )
    insufficient = len(pairs) < MINIMUM_CALIBRATION_SAMPLE
    for required in ("INSUFFICIENT_DATA", "PASS", "WARN"):
        if required not in statuses:
            _fail(
                "SCHEMA_UNREADABLE",
                f"the calibration schema declares no {required} status",
                {"required": required},
            )
    score = None if insufficient else brier_score(pairs)
    error = None if insufficient else expected_calibration_error(pairs, bins)
    if insufficient:
        status = "INSUFFICIENT_DATA"
    elif float(error or 0.0) <= 0.10:
        status = "PASS"
    else:
        status = "WARN"

    calibration: dict[str, Any] = {
        "abstention_curve_artifact_id": None,
        "brier_score": score,
        "calibration_report_id": f"CAL-{corpus_id}-verdict",
        "calibration_status": status,
        "created_at": "2026-08-01T00:00:00Z",
        "evaluation_id": corpus_id,
        "expected_calibration_error": error,
        "reliability_bins": bins,
        "sample_count": len(pairs),
        "target": "verdict",
    }
    calibration["report_hash"] = _hash_excluding(calibration, "report_hash")
    errors = sorted(
        jsonschema.Draft202012Validator(
            _calibration_schema(repository_root)
        ).iter_errors(calibration),
        key=lambda err: err.path,
    )
    if errors:
        _fail(
            "CALIBRATION_SCHEMA_INVALID",
            "the emitted calibration report does not satisfy its own schema",
            {"error": errors[0].message},
        )

    correct = sum(1 for _, is_correct in pairs if is_correct)
    report: dict[str, Any] = {
        "calibration": calibration,
        "corpus_id": corpus_id,
        "counts": {
            "queries": len(queries),
            "relevant_documents": sum(entry["relevant"] for entry in recall.values()),
            "verdict_cases": len(cases),
        },
        "recall_by_polarity": recall,
        "retriever_under_test": {
            "name": _text(retriever["name"], "name"),
            "synthetic": True,
            "version": _text(retriever["version"], "version"),
        },
        "status": "PASS",
        "verdict_accuracy": {
            "correct": correct,
            "rate": correct / len(cases),
            "total": len(cases),
        },
        "version": version,
    }
    report["report_hash"] = _hash_excluding(report, "report_hash")
    return SealedReport(_canonical_json(report))


def audit_calibration(repository_root: str | Path) -> dict[str, Any]:
    """The calibration slice of the full evaluation, for the named check."""

    return evaluate_corpus(repository_root).payload["calibration"]
