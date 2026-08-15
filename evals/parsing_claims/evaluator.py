"""Q02 parser, Claim and grounding evaluation.

Extraction quality is measured, never asserted.  The corpus carries the source
spans a parser emitted — including table cells and figure captions, because a
benchmark of running prose only would excuse exactly the spans parsers get
wrong — plus a gold claim set and a predicted claim set, and the evaluator
computes precision, recall and F1 from an exact match key it exposes, so every
number is recomputable from the counts beside it.

Unsupported promotion is its own measurement.  A claim whose gold evidence
layer is ``unsupported`` and whose prediction declares any stronger layer has
been promoted without evidence; the rate is reported with its numerator,
denominator and the offending claim ids rather than folded into precision.

Grounding is audited, not presumed: every span must satisfy the canonical
SourceSpan schema with its ``text_hash`` recomputed from the verbatim bytes,
every claim must cite at least one existing span whose verbatim text contains
the claim's own, and the corpus must ground at least one gold claim in a table
cell and one in a figure caption.  The claim vocabularies — types, stances,
directions, evidence layers — are read from ``schemas/claim-card.schema.json``,
never restated here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import jsonschema

#: The corpus file this evaluator governs.
CORPUS_RELATIVE_PATH: Final = "evals/parsing_claims/parsing_claims_cases.json"
SPAN_SCHEMA_PATH: Final = "schemas/source-span.schema.json"
CLAIM_SCHEMA_PATH: Final = "schemas/claim-card.schema.json"
#: The evidence layer that must never be silently promoted.
UNSUPPORTED_LAYER: Final = "unsupported"
#: Semantic units the exit criterion requires the corpus to exercise.
REQUIRED_GROUNDING_UNITS: Final = ("figure_caption", "table_cell")
#: The exact-match identity of a claim for scoring.
MATCH_FIELDS: Final = ("subject", "relation", "object", "direction")

_CORPUS_FIELDS: Final = frozenset(
    {
        "corpus_id",
        "documents",
        "extractor_under_test",
        "gold_claims",
        "predicted_claims",
        "version",
    }
)
_DOCUMENT_FIELDS: Final = frozenset({"document_id", "paper_version_id", "spans"})
_CLAIM_FIELDS: Final = frozenset(
    {
        "author_stance",
        "claim_id",
        "claim_type",
        "direction",
        "evidence_layer",
        "object",
        "relation",
        "source_span_ids",
        "subject",
        "verbatim_text",
    }
)
_EXTRACTOR_FIELDS: Final = frozenset({"name", "synthetic", "version"})


class ClaimEvalError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    raise ClaimEvalError(code, message, context)


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


def _schema(repository_root: str | Path, relative: str) -> dict[str, Any]:
    path = Path(repository_root) / relative
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail("SCHEMA_UNREADABLE", f"{relative} could not be read: {error}")
        raise  # pragma: no cover - _fail always raises
    return _mapping(loaded, relative)


def _claim_enum(repository_root: str | Path, field: str) -> tuple[str, ...]:
    schema = _schema(repository_root, CLAIM_SCHEMA_PATH)
    declared = schema.get("properties", {}).get(field, {}).get("enum")
    if not isinstance(declared, list) or not declared:
        _fail("SCHEMA_UNREADABLE", f"claim-card declares no {field} enum")
    return tuple(str(entry) for entry in declared)  # type: ignore[union-attr]


def claim_types(repository_root: str | Path) -> tuple[str, ...]:
    return _claim_enum(repository_root, "claim_type")


def author_stances(repository_root: str | Path) -> tuple[str, ...]:
    return _claim_enum(repository_root, "author_stance")


def directions(repository_root: str | Path) -> tuple[str, ...]:
    return _claim_enum(repository_root, "direction")


def evidence_layers(repository_root: str | Path) -> tuple[str, ...]:
    layers = _claim_enum(repository_root, "evidence_layer")
    if UNSUPPORTED_LAYER not in layers:
        _fail(
            "SCHEMA_UNREADABLE",
            "claim-card no longer declares the unsupported evidence layer",
        )
    return layers


def semantic_units(repository_root: str | Path) -> tuple[str, ...]:
    schema = _schema(repository_root, SPAN_SCHEMA_PATH)
    declared = schema.get("properties", {}).get("semantic_unit", {}).get("enum")
    if not isinstance(declared, list) or not declared:
        _fail("SCHEMA_UNREADABLE", "source-span declares no semantic_unit enum")
    units = tuple(str(entry) for entry in declared)  # type: ignore[union-attr]
    missing = sorted(set(REQUIRED_GROUNDING_UNITS) - set(units))
    if missing:
        _fail(
            "SCHEMA_UNREADABLE",
            "source-span no longer declares a required grounding unit",
            {"missing": missing},
        )
    return units


def load_corpus(repository_root: str | Path) -> dict[str, Any]:
    path = Path(repository_root) / CORPUS_RELATIVE_PATH
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail("CORPUS_UNREADABLE", f"the corpus could not be read: {error}")
        raise  # pragma: no cover - _fail always raises
    return _mapping(loaded, "corpus")


def _validate_spans(
    repository_root: str | Path, payload: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    span_schema = _schema(repository_root, SPAN_SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(span_schema)
    spans: dict[str, dict[str, Any]] = {}
    for document_index, entry in enumerate(
        _sequence(payload["documents"], "documents")
    ):
        document = _mapping(entry, f"documents[{document_index}]")
        _exact_fields(document, _DOCUMENT_FIELDS, f"documents[{document_index}]")
        document_id = _text(document["document_id"], "document_id")
        paper_version_id = _text(document["paper_version_id"], "paper_version_id")
        for span_index, span_entry in enumerate(
            _sequence(document["spans"], f"{document_id}.spans")
        ):
            span = _mapping(span_entry, f"{document_id}.spans[{span_index}]")
            errors = sorted(validator.iter_errors(span), key=lambda err: err.path)
            if errors:
                _fail(
                    "SPAN_SCHEMA_INVALID",
                    "a span does not satisfy the canonical SourceSpan schema",
                    {
                        "error": errors[0].message,
                        "span_id": span.get("span_id"),
                    },
                )
            span_id = str(span["span_id"])
            if span_id in spans:
                _fail(
                    "DUPLICATE_SPAN",
                    "span ids must be unique across the corpus",
                    {"span_id": span_id},
                )
            if span["document_id"] != document_id or (
                span["paper_version_id"] != paper_version_id
            ):
                _fail(
                    "SPAN_DOCUMENT_MISMATCH",
                    "a span must belong to the document that carries it",
                    {"span_id": span_id},
                )
            if int(span["char_end"]) <= int(span["char_start"]):
                _fail(
                    "SPAN_RANGE_INVALID",
                    "char_end must exceed char_start",
                    {"span_id": span_id},
                )
            verbatim = str(span["verbatim_text"])
            derived = "sha256:" + hashlib.sha256(verbatim.encode("utf-8")).hexdigest()
            if span["text_hash"] != derived:
                _fail(
                    "SPAN_HASH_MISMATCH",
                    "text_hash is not the hash of the verbatim text",
                    {"declared": span["text_hash"], "span_id": span_id},
                )
            spans[span_id] = dict(span)
    if not spans:
        _fail("INPUT_INVALID", "the corpus carries no spans")
    return spans


def _validate_claims(
    repository_root: str | Path,
    entries: object,
    label: str,
    spans: Mapping[str, Mapping[str, Any]],
    seen_ids: set[str],
) -> list[dict[str, Any]]:
    types = claim_types(repository_root)
    stances = author_stances(repository_root)
    claim_directions = directions(repository_root)
    layers = evidence_layers(repository_root)

    claims: list[dict[str, Any]] = []
    for index, entry in enumerate(_sequence(entries, label)):
        claim = _mapping(entry, f"{label}[{index}]")
        _exact_fields(claim, _CLAIM_FIELDS, f"{label}[{index}]")
        claim_id = _text(claim["claim_id"], "claim_id")
        if claim_id in seen_ids:
            _fail(
                "DUPLICATE_CLAIM",
                "claim ids must be unique across gold and predicted sets",
                {"claim_id": claim_id},
            )
        seen_ids.add(claim_id)
        for field, allowed in (
            ("claim_type", types),
            ("author_stance", stances),
            ("direction", claim_directions),
            ("evidence_layer", layers),
        ):
            if claim[field] not in allowed:
                _fail(
                    "VOCABULARY_INVALID",
                    f"{field} must be a canonical claim-card value",
                    {"claim_id": claim_id, "field": field, "value": claim[field]},
                )
        span_ids = [
            _text(value, "source_span_ids")
            for value in _sequence(claim["source_span_ids"], "source_span_ids")
        ]
        if len(set(span_ids)) != len(span_ids):
            _fail(
                "DUPLICATE_SPAN_REFERENCE",
                "a claim must not cite the same span twice",
                {"claim_id": claim_id},
            )
        if not span_ids:
            _fail(
                "GROUNDING_MISSING",
                "every claim must cite the span it was extracted from",
                {"claim_id": claim_id},
            )
        verbatim = _text(claim["verbatim_text"], "verbatim_text")
        contained = False
        for span_id in span_ids:
            span = spans.get(span_id)
            if span is None:
                _fail(
                    "CLAIM_UNGROUNDED",
                    "a claim cites a span the corpus does not carry",
                    {"claim_id": claim_id, "span_id": span_id},
                )
            if verbatim in str(span["verbatim_text"]):  # type: ignore[index]
                contained = True
        if not contained:
            _fail(
                "VERBATIM_UNGROUNDED",
                "a claim's verbatim text must appear in a cited span",
                {"claim_id": claim_id},
            )
        claims.append(
            {
                "author_stance": str(claim["author_stance"]),
                "claim_id": claim_id,
                "claim_type": str(claim["claim_type"]),
                "direction": str(claim["direction"]),
                "evidence_layer": str(claim["evidence_layer"]),
                "object": _text(claim["object"], "object"),
                "relation": _text(claim["relation"], "relation"),
                "source_span_ids": span_ids,
                "subject": _text(claim["subject"], "subject"),
                "verbatim_text": verbatim,
            }
        )
    if not claims:
        _fail("INPUT_INVALID", f"{label} must not be empty")
    return claims


def match_key(claim: Mapping[str, Any]) -> tuple[str, ...]:
    """The exact-match identity used for scoring, exposed for recomputation."""

    return tuple(
        str(claim[field]).strip().lower()
        if field != "direction"
        else (str(claim[field]))
        for field in MATCH_FIELDS
    )


def _keyed(claims: Sequence[Mapping[str, Any]], label: str) -> dict[tuple, dict]:
    keyed: dict[tuple, dict] = {}
    for claim in claims:
        key = match_key(claim)
        if key in keyed:
            _fail(
                "DUPLICATE_MATCH_KEY",
                f"two {label} claims share one match identity",
                {"claim_ids": [keyed[key]["claim_id"], claim["claim_id"]]},
            )
        keyed[key] = dict(claim)
    return keyed


def _grounding_summary(
    spans: Mapping[str, Mapping[str, Any]],
    gold: Sequence[Mapping[str, Any]],
    predicted: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_unit: dict[str, int] = {}
    for span in spans.values():
        unit = str(span["semantic_unit"])
        by_unit[unit] = by_unit.get(unit, 0) + 1
    for unit in REQUIRED_GROUNDING_UNITS:
        if by_unit.get(unit, 0) < 1:
            _fail(
                "REQUIRED_UNIT_MISSING",
                f"the corpus carries no {unit} span",
                {"unit": unit},
            )
    gold_units: dict[str, int] = dict.fromkeys(REQUIRED_GROUNDING_UNITS, 0)
    for claim in gold:
        units = {
            str(spans[span_id]["semantic_unit"]) for span_id in claim["source_span_ids"]
        }
        for unit in REQUIRED_GROUNDING_UNITS:
            if unit in units:
                gold_units[unit] += 1
    thin = sorted(unit for unit, count in gold_units.items() if count < 1)
    if thin:
        _fail(
            "REQUIRED_UNIT_UNGROUNDED",
            "no gold claim is grounded in a required span unit",
            {"units": thin},
        )
    return {
        "claims_audited": len(gold) + len(predicted),
        "gold_claims_grounded_in_required_units": gold_units,
        "spans_by_semantic_unit": dict(sorted(by_unit.items())),
        "spans_total": len(spans),
        "status": "PASS",
    }


def evaluate_corpus(repository_root: str | Path) -> SealedReport:
    return evaluate(load_corpus(repository_root), repository_root)


def evaluate(payload: Mapping[str, Any], repository_root: str | Path) -> SealedReport:
    corpus = _mapping(payload, "corpus")
    _exact_fields(corpus, _CORPUS_FIELDS, "corpus")
    corpus_id = _text(corpus["corpus_id"], "corpus_id")
    version = _text(corpus["version"], "version")
    extractor = _mapping(corpus["extractor_under_test"], "extractor_under_test")
    _exact_fields(extractor, _EXTRACTOR_FIELDS, "extractor_under_test")
    if extractor["synthetic"] is not True:
        _fail(
            "EXTRACTOR_OVERCLAIM",
            "v1 predictions are a synthetic fixture; a corpus claiming a real "
            "extractor requires recorded runs",
        )

    spans = _validate_spans(repository_root, corpus)
    seen_ids: set[str] = set()
    gold = _validate_claims(
        repository_root, corpus["gold_claims"], "gold_claims", spans, seen_ids
    )
    predicted = _validate_claims(
        repository_root,
        corpus["predicted_claims"],
        "predicted_claims",
        spans,
        seen_ids,
    )
    grounding = _grounding_summary(spans, gold, predicted)

    gold_keyed = _keyed(gold, "gold")
    predicted_keyed = _keyed(predicted, "predicted")
    matched_keys = sorted(set(gold_keyed) & set(predicted_keyed))
    true_positive = len(matched_keys)
    false_positive = len(predicted_keyed) - true_positive
    false_negative = len(gold_keyed) - true_positive
    precision = true_positive / len(predicted_keyed)
    recall = true_positive / len(gold_keyed)
    f1 = (
        0.0
        if precision + recall == 0
        else 2 * precision * recall / (precision + recall)
    )

    eligible_keys = [
        key
        for key in matched_keys
        if gold_keyed[key]["evidence_layer"] == UNSUPPORTED_LAYER
    ]
    promoted = sorted(
        predicted_keyed[key]["claim_id"]
        for key in eligible_keys
        if predicted_keyed[key]["evidence_layer"] != UNSUPPORTED_LAYER
    )
    promotion_denominator = len(eligible_keys)
    promotion: dict[str, Any] = {
        "claim_ids": promoted,
        "count": len(promoted),
        "denominator": promotion_denominator,
        "rate": (
            None
            if promotion_denominator == 0
            else len(promoted) / promotion_denominator
        ),
    }
    if promotion_denominator == 0:
        promotion["reason"] = (
            "no matched gold-unsupported pair exists, so promotion is undefined "
            "rather than zero"
        )

    report: dict[str, Any] = {
        "corpus_id": corpus_id,
        "counts": {
            "documents": len(corpus["documents"]),
            "gold_claims": len(gold),
            "predicted_claims": len(predicted),
        },
        "extractor_under_test": {
            "name": _text(extractor["name"], "name"),
            "synthetic": True,
            "version": _text(extractor["version"], "version"),
        },
        "grounding": grounding,
        "match_fields": list(MATCH_FIELDS),
        "metrics": {
            "f1": f1,
            "false_negative": false_negative,
            "false_positive": false_positive,
            "precision": precision,
            "recall": recall,
            "true_positive": true_positive,
        },
        "status": "PASS",
        "unsupported_promotion": promotion,
        "version": version,
    }
    report["report_hash"] = _hash_excluding(report, "report_hash")
    return SealedReport(_canonical_json(report))


def audit_grounding(repository_root: str | Path) -> dict[str, Any]:
    """The grounding slice of the full evaluation, for the named check."""

    return evaluate_corpus(repository_root).payload["grounding"]
