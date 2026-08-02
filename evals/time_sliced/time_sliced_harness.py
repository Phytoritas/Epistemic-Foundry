"""Q04 time-sliced benchmark gate.

A retrospective benchmark that lets an evaluation at time ``T`` see material
published after ``T`` measures nothing: the system is graded on the answer.
So the withholding is not a promise here, it is a check.  Every document
carries a publication timestamp, every slice carries an as-of timestamp, and
every item declares exactly which documents were visible to the system under
test.  The harness compares each visible document's publication date against
the item's as-of date and refuses the whole benchmark — ``FUTURE_EVIDENCE_LEAK``
— the moment one of them is later.  The count of comparisons it performed is
published beside the metrics, so "no leakage" is a number rather than a claim.

Withholding is also proved from the other side.  A slice whose corpus contains
no document dated after its as-of date could not have withheld anything, and a
run over such a slice would look clean for the wrong reason; that slice is
refused with ``SLICE_WITHHOLDS_NOTHING`` and the withheld ids are listed in the
per-slice metrics.

Nothing here invents a corpus.  Item labels are bound to the sealed Q01 gold
corpus by case id, and the label vocabulary is read from that corpus rather
than restated, so a relabelled gold case breaks this benchmark instead of
silently disagreeing with it.  The dataset carries its own content hash, the
report re-derives its own, and both are computed over canonical JSON with the
hash field removed — the same rule the canonical receipt writers use.  No
clock and no randomness live in this module: ``evaluated_at`` and ``report_id``
are supplied by the dataset.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

#: The benchmark dataset this harness governs.
BENCHMARK_RELATIVE_PATH: Final = "evals/time_sliced/time_sliced_cases.json"
#: The machine-readable results artifact this harness re-derives.
RESULTS_RELATIVE_PATH: Final = "evals/time_sliced/time_sliced_results.json"
#: The sealed Q01 corpus every item's label is bound to.
GOLD_CORPUS_RELATIVE_PATH: Final = "evals/gold/insight_gold_cases.json"

_BENCHMARK_FIELDS: Final = frozenset(
    {
        "benchmark_id",
        "dataset_hash",
        "documents",
        "evaluated_at",
        "gold_corpus_ref",
        "items",
        "report_id",
        "slices",
        "system_under_test",
        "version",
    }
)
_GOLD_REF_FIELDS: Final = frozenset({"corpus_id", "corpus_version", "path"})
_SYSTEM_FIELDS: Final = frozenset({"name", "synthetic", "version"})
_DOCUMENT_FIELDS: Final = frozenset({"document_id", "published_at", "title"})
_SLICE_FIELDS: Final = frozenset({"as_of", "description", "slice_id"})
_ITEM_FIELDS: Final = frozenset(
    {
        "as_of",
        "gold_case_id",
        "gold_label",
        "item_id",
        "predicted_label",
        "retrieved_document_ids",
        "slice_id",
        "visible_document_ids",
    }
)

#: Every way this harness refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "BENCHMARK_UNREADABLE": (
        "the committed benchmark dataset could not be read or parsed, so no "
        "time-slice claim can be grounded in the material it names"
    ),
    "DATASET_HASH_MISMATCH": (
        "the dataset content no longer matches the hash it publishes, which "
        "means an item, a date or a label was edited after the seal"
    ),
    "DOCUMENT_UNKNOWN": (
        "an item names a document the benchmark never declares, so its "
        "publication date — and therefore its eligibility at the as-of time "
        "— cannot be checked at all"
    ),
    "DUPLICATE_DOCUMENT": (
        "one document id is declared twice, which lets two different "
        "publication dates answer the same eligibility question"
    ),
    "DUPLICATE_ITEM": (
        "one item id appears twice, so a per-slice metric would count the "
        "same evaluation more than once"
    ),
    "DUPLICATE_SLICE": (
        "one slice id is declared twice, which lets two different as-of times "
        "govern the same group of items"
    ),
    "FIELD_SET_INVALID": (
        "a record carries an unknown or missing field, and a benchmark whose "
        "shape drifts silently stops measuring what it claims to measure"
    ),
    "FUTURE_EVIDENCE_LEAK": (
        "material published after the item's as-of time was visible to the "
        "system under test, which is the exact failure a time-sliced "
        "benchmark exists to detect"
    ),
    "GOLD_CASE_UNKNOWN": (
        "an item cites a gold case id the sealed Q01 corpus does not carry, "
        "so its label traces to nothing an annotator ever adjudicated"
    ),
    "GOLD_CORPUS_UNREADABLE": (
        "the sealed gold corpus could not be read, so neither the label "
        "vocabulary nor the per-case labels can be bound to their source"
    ),
    "GOLD_LABEL_MISMATCH": (
        "an item's gold label disagrees with the label the sealed corpus "
        "carries for that case, which would grade the system against a "
        "private relabelling"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this harness requires, and continuing "
        "would publish metrics over material it never validated"
    ),
    "ITEM_AS_OF_MISMATCH": (
        "an item's as-of time differs from the as-of time of the slice it is "
        "filed under, so the leakage boundary the metrics report is not the "
        "boundary the item was evaluated at"
    ),
    "LABEL_INVALID": (
        "a label lies outside the vocabulary the sealed gold corpus declares, "
        "so accuracy would be computed over a class nobody annotated"
    ),
    "RESULTS_STALE": (
        "the committed results artifact does not equal the report re-derived "
        "from the committed dataset, so the published metrics describe some "
        "other version of the benchmark"
    ),
    "RESULTS_UNREADABLE": (
        "the committed results artifact could not be read or parsed, so the "
        "published metrics cannot be checked against the dataset at all"
    ),
    "RETRIEVAL_UNGROUNDED": (
        "the system returned a document that was never in the visible set for "
        "that item, so the run reached material the slice did not hand it"
    ),
    "SLICE_EMPTY": (
        "a declared slice carries no item, so it contributes an as-of "
        "boundary the benchmark never actually evaluated anything against"
    ),
    "SLICE_ORDER_INVALID": (
        "slice as-of times are not strictly increasing, so the visible corpus "
        "does not grow monotonically and a later slice could see less"
    ),
    "SLICE_UNKNOWN": (
        "an item is filed under a slice the benchmark never declares, so no "
        "as-of boundary governs it"
    ),
    "SLICE_WITHHOLDS_NOTHING": (
        "no declared document postdates this slice's as-of time, so the slice "
        "would report a clean withholding record without ever having had "
        "anything to withhold"
    ),
    "SYSTEM_OVERCLAIM": (
        "the recorded predictions are a committed fixture; a dataset claiming "
        "a live system under test requires recorded runs this repository does "
        "not carry"
    ),
    "TIMESTAMP_INVALID": (
        "a timestamp is not an offset-aware RFC3339 instant, so two dates "
        "cannot be ordered and the leakage boundary is undefined"
    ),
}


class TimeSliceError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise TimeSliceError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise TimeSliceError(code, message, context)


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


def canonical_json(value: object) -> bytes:
    """The one canonical byte form used for every digest in this harness."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: object) -> str:
    """The schema-shaped digest (``sha256:<64 lowercase hex>``)."""

    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def hash_excluding(payload: Mapping[str, Any], field: str) -> str:
    """Digest a record while omitting the field that carries the digest."""

    return digest({key: value for key, value in payload.items() if key != field})


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


def _instant(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        _fail(
            "TIMESTAMP_INVALID", f"{label} is not an RFC3339 instant", {"value": text}
        )
        raise  # pragma: no cover - _fail always raises
    if parsed.tzinfo is None:
        _fail(
            "TIMESTAMP_INVALID",
            f"{label} must carry a UTC offset",
            {"value": text},
        )
    return parsed


def _read_json(path: Path, code: str, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(code, f"{label} could not be read: {error}", {"path": str(path)})
        raise  # pragma: no cover - _fail always raises


def load_gold_corpus(repository_root: str | Path) -> dict[str, Any]:
    """Read the sealed Q01 corpus this benchmark binds its labels to."""

    path = Path(repository_root) / GOLD_CORPUS_RELATIVE_PATH
    loaded = _read_json(path, "GOLD_CORPUS_UNREADABLE", "the sealed gold corpus")
    return _mapping(loaded, "gold corpus")


def gold_case_labels(repository_root: str | Path) -> dict[str, str]:
    """Case id to gold label, read from the sealed corpus rather than restated."""

    corpus = load_gold_corpus(repository_root)
    labels: dict[str, str] = {}
    for index, entry in enumerate(_sequence(corpus.get("cases"), "gold cases")):
        case = _mapping(entry, f"gold cases[{index}]")
        labels[_text(case.get("case_id"), "case_id")] = _text(
            case.get("gold_label"), "gold_label"
        )
    if not labels:
        _fail("GOLD_CORPUS_UNREADABLE", "the sealed gold corpus declares no case")
    return labels


def gold_labels(repository_root: str | Path) -> tuple[str, ...]:
    """The label vocabulary, taken from the sealed corpus that declares it."""

    return tuple(sorted(set(gold_case_labels(repository_root).values())))


def load_benchmark(repository_root: str | Path) -> dict[str, Any]:
    """Read the committed time-sliced dataset."""

    path = Path(repository_root) / BENCHMARK_RELATIVE_PATH
    loaded = _read_json(path, "BENCHMARK_UNREADABLE", "the time-sliced dataset")
    return _mapping(loaded, "benchmark")


def load_results(repository_root: str | Path) -> dict[str, Any]:
    """Read the committed machine-readable results artifact."""

    path = Path(repository_root) / RESULTS_RELATIVE_PATH
    loaded = _read_json(path, "RESULTS_UNREADABLE", "the time-sliced results")
    return _mapping(loaded, "results")


def _validate_documents(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(_sequence(payload["documents"], "documents")):
        record = _mapping(entry, f"documents[{index}]")
        _exact_fields(record, _DOCUMENT_FIELDS, f"documents[{index}]")
        document_id = _text(record["document_id"], "document_id")
        if document_id in documents:
            _fail(
                "DUPLICATE_DOCUMENT",
                "document ids must be unique",
                {"document_id": document_id},
            )
        documents[document_id] = {
            "document_id": document_id,
            "published_at": _instant(
                record["published_at"], f"{document_id}.published_at"
            ),
            "published_at_text": _text(record["published_at"], "published_at"),
            "title": _text(record["title"], "title"),
        }
    if not documents:
        _fail("INPUT_INVALID", "the benchmark declares no document")
    return documents


def _validate_slices(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    slices: dict[str, dict[str, Any]] = {}
    previous: datetime | None = None
    for index, entry in enumerate(_sequence(payload["slices"], "slices")):
        record = _mapping(entry, f"slices[{index}]")
        _exact_fields(record, _SLICE_FIELDS, f"slices[{index}]")
        slice_id = _text(record["slice_id"], "slice_id")
        if slice_id in slices:
            _fail("DUPLICATE_SLICE", "slice ids must be unique", {"slice_id": slice_id})
        as_of = _instant(record["as_of"], f"{slice_id}.as_of")
        if previous is not None and as_of <= previous:
            _fail(
                "SLICE_ORDER_INVALID",
                "slice as-of times must be declared strictly increasing",
                {"previous": previous.isoformat(), "slice_id": slice_id},
            )
        previous = as_of
        slices[slice_id] = {
            "as_of": as_of,
            "as_of_text": _text(record["as_of"], "as_of"),
            "description": _text(record["description"], "description"),
            "slice_id": slice_id,
        }
    if not slices:
        _fail("INPUT_INVALID", "the benchmark declares no slice")
    return slices


def _document_ids(
    value: object,
    label: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    ids: list[str] = []
    for entry in _sequence(value, label):
        document_id = _text(entry, label)
        if document_id not in documents:
            _fail(
                "DOCUMENT_UNKNOWN",
                "an item may only name a declared document",
                {"document_id": document_id, "field": label},
            )
        if document_id in ids:
            _fail(
                "DUPLICATE_DOCUMENT",
                "a document may appear only once in one item field",
                {"document_id": document_id, "field": label},
            )
        ids.append(document_id)
    if not ids:
        _fail("INPUT_INVALID", f"{label} must not be empty")
    return ids


def _validate_items(
    payload: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
    slices: Mapping[str, Mapping[str, Any]],
    case_labels: Mapping[str, str],
    vocabulary: Sequence[str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(_sequence(payload["items"], "items")):
        record = _mapping(entry, f"items[{index}]")
        _exact_fields(record, _ITEM_FIELDS, f"items[{index}]")
        item_id = _text(record["item_id"], "item_id")
        if item_id in seen:
            _fail("DUPLICATE_ITEM", "item ids must be unique", {"item_id": item_id})
        seen.add(item_id)
        slice_id = _text(record["slice_id"], "slice_id")
        if slice_id not in slices:
            _fail(
                "SLICE_UNKNOWN",
                "an item must be filed under a declared slice",
                {"item_id": item_id, "slice_id": slice_id},
            )
        as_of = _instant(record["as_of"], f"{item_id}.as_of")
        if as_of != slices[slice_id]["as_of"]:
            _fail(
                "ITEM_AS_OF_MISMATCH",
                "an item's as-of time must equal its slice's as-of time",
                {
                    "item_as_of": _text(record["as_of"], "as_of"),
                    "item_id": item_id,
                    "slice_as_of": slices[slice_id]["as_of_text"],
                },
            )
        gold_case_id = _text(record["gold_case_id"], "gold_case_id")
        if gold_case_id not in case_labels:
            _fail(
                "GOLD_CASE_UNKNOWN",
                "an item must cite a case the sealed gold corpus carries",
                {"gold_case_id": gold_case_id, "item_id": item_id},
            )
        for field in ("gold_label", "predicted_label"):
            label = _text(record[field], field)
            if label not in vocabulary:
                _fail(
                    "LABEL_INVALID",
                    f"{field} must be a label the sealed gold corpus declares",
                    {"allowed": list(vocabulary), "item_id": item_id, "value": label},
                )
        gold_label = _text(record["gold_label"], "gold_label")
        if gold_label != case_labels[gold_case_id]:
            _fail(
                "GOLD_LABEL_MISMATCH",
                "an item's gold label must equal the sealed corpus label",
                {
                    "corpus_label": case_labels[gold_case_id],
                    "gold_case_id": gold_case_id,
                    "item_id": item_id,
                    "item_label": gold_label,
                },
            )
        visible = _document_ids(
            record["visible_document_ids"], f"{item_id}.visible_document_ids", documents
        )
        retrieved = _document_ids(
            record["retrieved_document_ids"],
            f"{item_id}.retrieved_document_ids",
            documents,
        )
        items.append(
            {
                "as_of": as_of,
                "gold_case_id": gold_case_id,
                "gold_label": gold_label,
                "item_id": item_id,
                "predicted_label": _text(record["predicted_label"], "predicted_label"),
                "retrieved_document_ids": retrieved,
                "slice_id": slice_id,
                "visible_document_ids": visible,
            }
        )
    if not items:
        _fail("INPUT_INVALID", "the benchmark declares no item")
    return items


def _assert_no_future_material(
    items: Sequence[Mapping[str, Any]],
    documents: Mapping[str, Mapping[str, Any]],
) -> int:
    """Compare every visible document against its item's as-of time.

    The returned count is the evidence: it is the number of comparisons the
    gate actually performed, published beside the metrics so a reader can see
    that the withholding claim covers every document the run could reach.
    """

    checks = 0
    for item in items:
        for document_id in item["visible_document_ids"]:
            checks += 1
            published = documents[document_id]["published_at"]
            if published > item["as_of"]:
                _fail(
                    "FUTURE_EVIDENCE_LEAK",
                    "an item saw material published after its as-of time",
                    {
                        "as_of": item["as_of"].isoformat(),
                        "document_id": document_id,
                        "item_id": item["item_id"],
                        "published_at": documents[document_id]["published_at_text"],
                    },
                )
        visible = set(item["visible_document_ids"])
        outside = sorted(set(item["retrieved_document_ids"]) - visible)
        if outside:
            _fail(
                "RETRIEVAL_UNGROUNDED",
                "the system returned a document the slice never made visible",
                {"document_ids": outside, "item_id": item["item_id"]},
            )
    return checks


def _slice_metrics(
    slices: Mapping[str, Mapping[str, Any]],
    items: Sequence[Mapping[str, Any]],
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for slice_id, record in slices.items():
        members = [item for item in items if item["slice_id"] == slice_id]
        if not members:
            _fail(
                "SLICE_EMPTY",
                "a declared slice must carry at least one item",
                {"slice_id": slice_id},
            )
        withheld = sorted(
            document_id
            for document_id, document in documents.items()
            if document["published_at"] > record["as_of"]
        )
        if not withheld:
            _fail(
                "SLICE_WITHHOLDS_NOTHING",
                "a slice with no later-dated document cannot demonstrate that "
                "future material was withheld",
                {"as_of": record["as_of_text"], "slice_id": slice_id},
            )
        eligible = sorted(
            document_id
            for document_id, document in documents.items()
            if document["published_at"] <= record["as_of"]
        )
        correct = sum(
            1 for item in members if item["predicted_label"] == item["gold_label"]
        )
        metrics.append(
            {
                "accuracy": correct / len(members),
                "as_of": record["as_of_text"],
                "correct": correct,
                "date_checks": sum(
                    len(item["visible_document_ids"]) for item in members
                ),
                "eligible_document_count": len(eligible),
                "eligible_document_ids": eligible,
                "item_count": len(members),
                "item_ids": sorted(item["item_id"] for item in members),
                "missed_item_ids": sorted(
                    item["item_id"]
                    for item in members
                    if item["predicted_label"] != item["gold_label"]
                ),
                "slice_id": slice_id,
                "withheld_document_count": len(withheld),
                "withheld_document_ids": withheld,
            }
        )
    return metrics


def evaluate(payload: Mapping[str, Any], repository_root: str | Path) -> SealedReport:
    """Validate the dataset, prove the withholding, and seal the report."""

    benchmark = _mapping(payload, "benchmark")
    _exact_fields(benchmark, _BENCHMARK_FIELDS, "benchmark")
    declared_hash = _text(benchmark["dataset_hash"], "dataset_hash")
    recomputed = hash_excluding(benchmark, "dataset_hash")
    if declared_hash != recomputed:
        _fail(
            "DATASET_HASH_MISMATCH",
            "the dataset content does not match the hash it publishes",
            {"declared": declared_hash, "recomputed": recomputed},
        )

    system = _mapping(benchmark["system_under_test"], "system_under_test")
    _exact_fields(system, _SYSTEM_FIELDS, "system_under_test")
    if system["synthetic"] is not True:
        _fail(
            "SYSTEM_OVERCLAIM",
            "the recorded predictions are a committed fixture, so the dataset "
            "may not claim a live system under test",
        )
    gold_ref = _mapping(benchmark["gold_corpus_ref"], "gold_corpus_ref")
    _exact_fields(gold_ref, _GOLD_REF_FIELDS, "gold_corpus_ref")
    if _text(gold_ref["path"], "path") != GOLD_CORPUS_RELATIVE_PATH:
        _fail(
            "GOLD_CORPUS_UNREADABLE",
            "the dataset must cite the sealed gold corpus it draws cases from",
            {"path": gold_ref["path"]},
        )

    case_labels = gold_case_labels(repository_root)
    vocabulary = tuple(sorted(set(case_labels.values())))
    documents = _validate_documents(benchmark)
    slices = _validate_slices(benchmark)
    items = _validate_items(benchmark, documents, slices, case_labels, vocabulary)

    date_checks = _assert_no_future_material(items, documents)
    per_slice = _slice_metrics(slices, items, documents)
    correct = sum(1 for item in items if item["predicted_label"] == item["gold_label"])

    report: dict[str, Any] = {
        "benchmark_id": _text(benchmark["benchmark_id"], "benchmark_id"),
        "counts": {
            "documents": len(documents),
            "items": len(items),
            "slices": len(slices),
        },
        "dataset_hash": declared_hash,
        "evaluated_at": _text(benchmark["evaluated_at"], "evaluated_at"),
        "gold_corpus_ref": {
            "corpus_id": _text(gold_ref["corpus_id"], "corpus_id"),
            "corpus_version": _text(gold_ref["corpus_version"], "corpus_version"),
            "path": GOLD_CORPUS_RELATIVE_PATH,
        },
        "label_vocabulary": list(vocabulary),
        "leakage": {
            "documents_checked": date_checks,
            "future_documents_admitted": 0,
            "withheld_document_total": sum(
                entry["withheld_document_count"] for entry in per_slice
            ),
        },
        "overall": {
            "accuracy": correct / len(items),
            "correct": correct,
            "item_count": len(items),
        },
        "report_id": _text(benchmark["report_id"], "report_id"),
        "slices": per_slice,
        "status": "PASS",
        "system_under_test": {
            "name": _text(system["name"], "name"),
            "synthetic": True,
            "version": _text(system["version"], "version"),
        },
        "version": _text(benchmark["version"], "version"),
    }
    report["report_hash"] = hash_excluding(report, "report_hash")
    return SealedReport(canonical_json(report))


def evaluate_benchmark(repository_root: str | Path) -> SealedReport:
    """Evaluate the dataset exactly as it is committed."""

    return evaluate(load_benchmark(repository_root), repository_root)


def verify_results(repository_root: str | Path) -> dict[str, Any]:
    """Re-derive the committed results artifact and refuse any drift."""

    committed = load_results(repository_root)
    derived = evaluate_benchmark(repository_root).payload
    if committed != derived:
        _fail(
            "RESULTS_STALE",
            "the committed results artifact is not the report the committed "
            "dataset produces",
            {
                "committed_hash": committed.get("report_hash"),
                "derived_hash": derived["report_hash"],
            },
        )
    return derived
