"""Q04 adversarial benchmark gate.

An adversarial score without its baseline is not a robustness measurement, it
is a mood.  So every adversarial item here is a perturbation *of a named
baseline item*, and the baseline item is itself a case drawn from the sealed
Q01 gold corpus.  The delta the report publishes is the difference between the
system's accuracy on the perturbed items and its accuracy on exactly the same
baselines those items were derived from — one pairing, both directions
enforced: an adversarial item without its baseline is ``BASELINE_MISSING``, a
baseline nothing perturbs is ``BASELINE_UNPAIRED``, and a baseline perturbed
twice is ``BASELINE_PAIRED_TWICE``.

A perturbation that moves the gold label is the dangerous kind, because it is
indistinguishable from a mislabelled item.  When the adversarial gold label
differs from its baseline's, the item must carry the rationale for the move
(``LABEL_CHANGE_UNJUSTIFIED``); when it does not differ, it must not carry one
(``RATIONALE_UNEXPECTED``), so the rationale field cannot become decoration.

Coverage is measured, never announced.  Attack classes are declared in the
dataset and every declared class must carry at least one item
(``ATTACK_CLASS_UNPOPULATED``): a report listing an attack class it never
exercised claims a defence nobody tested.  Where a class declares a textual
signature — the injected imperative of a prompt-injection item, for instance —
an item of that class whose evidence text does not carry it is refused
(``ATTACK_SIGNATURE_ABSENT``), so the label on the attack matches the attack.

The label vocabulary and every baseline label are read from the sealed gold
corpus rather than restated here, and the label that counts as a known false
claim is named by the dataset and checked against that vocabulary.  The dataset
carries its own content hash, the report re-derives its own, and no clock or
randomness lives in this module: ``evaluated_at`` and ``report_id`` come from
the dataset.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: The benchmark dataset this harness governs.
BENCHMARK_RELATIVE_PATH: Final = "evals/adversarial/adversarial_cases.json"
#: The machine-readable results artifact this harness re-derives.
RESULTS_RELATIVE_PATH: Final = "evals/adversarial/adversarial_results.json"
#: The sealed Q01 corpus every baseline item is drawn from.
GOLD_CORPUS_RELATIVE_PATH: Final = "evals/gold/insight_gold_cases.json"

_BENCHMARK_FIELDS: Final = frozenset(
    {
        "adversarial_items",
        "attack_classes",
        "baseline_items",
        "benchmark_id",
        "dataset_hash",
        "evaluated_at",
        "false_claim_label",
        "gold_corpus_ref",
        "report_id",
        "system_under_test",
        "version",
    }
)
_GOLD_REF_FIELDS: Final = frozenset({"corpus_id", "corpus_version", "path"})
_SYSTEM_FIELDS: Final = frozenset({"name", "synthetic", "version"})
_ATTACK_CLASS_FIELDS: Final = frozenset(
    {"attack_class", "description", "evidence_marker"}
)
_BASELINE_FIELDS: Final = frozenset(
    {
        "evidence_text",
        "gold_case_id",
        "gold_label",
        "item_id",
        "predicted_label",
        "statement",
    }
)
_ADVERSARIAL_FIELDS: Final = frozenset(
    {
        "attack_class",
        "baseline_item_id",
        "evidence_text",
        "gold_label",
        "item_id",
        "label_change_rationale",
        "predicted_label",
        "statement",
    }
)

#: Every way this harness refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "ATTACK_CLASS_DUPLICATED": (
        "one attack class is declared twice, so two descriptions and two "
        "signatures would govern the same set of items"
    ),
    "ATTACK_CLASS_UNDECLARED": (
        "an item names an attack class the dataset never declares, which puts "
        "an unreviewable row into the per-class robustness breakdown"
    ),
    "ATTACK_CLASS_UNPOPULATED": (
        "a declared attack class carries no item, so the report would claim "
        "coverage of an attack the benchmark never actually ran"
    ),
    "ATTACK_SIGNATURE_ABSENT": (
        "an item's evidence text does not carry the signature its attack class "
        "declares, so the item is filed under an attack it does not perform"
    ),
    "BASELINE_MISSING": (
        "an adversarial item names a baseline item the dataset does not carry, "
        "so its robustness delta would be measured against nothing"
    ),
    "BASELINE_PAIRED_TWICE": (
        "two adversarial items perturb one baseline, which weights that "
        "baseline twice in the delta and leaves another baseline unmeasured"
    ),
    "BASELINE_UNGROUNDED": (
        "a baseline item cites a case the sealed Q01 corpus does not carry, so "
        "the unperturbed half of the comparison traces to no annotated source"
    ),
    "BASELINE_UNPAIRED": (
        "a baseline item that no adversarial item perturbs inflates the "
        "baseline half of the delta against a smaller adversarial half"
    ),
    "BASELINE_UNPERTURBED": (
        "an adversarial item's statement and evidence are byte-identical to "
        "its baseline, so it measures the baseline a second time under an "
        "attack label"
    ),
    "BENCHMARK_UNREADABLE": (
        "the committed benchmark dataset could not be read or parsed, so no "
        "robustness claim can be grounded in the items it names"
    ),
    "DATASET_HASH_MISMATCH": (
        "the dataset content no longer matches the hash it publishes, which "
        "means an item, a label or a rationale was edited after the seal"
    ),
    "DUPLICATE_ITEM": (
        "one item id appears twice across the baseline and adversarial sets, "
        "so a pairing would resolve to whichever record was read last"
    ),
    "FALSE_CLAIM_COVERAGE_ABSENT": (
        "no adversarial item carries the label that marks a known false claim, "
        "so a rejection rate would be reported over an empty denominator"
    ),
    "FIELD_SET_INVALID": (
        "a record carries an unknown or missing field, and a benchmark whose "
        "shape drifts silently stops measuring what it claims to measure"
    ),
    "GOLD_CORPUS_UNREADABLE": (
        "the sealed gold corpus could not be read, so neither the label "
        "vocabulary nor the per-case labels can be bound to their source"
    ),
    "GOLD_CORPUS_REF_MISMATCH": (
        "the benchmark-declared gold corpus identity does not match the "
        "sealed corpus that supplies its labels"
    ),
    "GOLD_LABEL_MISMATCH": (
        "a baseline item's gold label disagrees with the label the sealed "
        "corpus carries for that case, which would grade the system against a "
        "private relabelling"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this harness requires, and continuing "
        "would publish metrics over material it never validated"
    ),
    "LABEL_CHANGE_UNJUSTIFIED": (
        "a perturbation moved the gold label away from its baseline without a "
        "recorded rationale, which is indistinguishable from a mislabelled item"
    ),
    "LABEL_INVALID": (
        "a label lies outside the vocabulary the sealed gold corpus declares, "
        "so accuracy would be computed over a class nobody annotated"
    ),
    "RATIONALE_UNEXPECTED": (
        "an item whose gold label matches its baseline records a rationale for "
        "a change it did not make, which turns the field into decoration"
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
    "SYSTEM_OVERCLAIM": (
        "the recorded predictions are a committed fixture; a dataset claiming "
        "a live system under test requires recorded runs this repository does "
        "not carry"
    ),
}


class AdversarialEvalError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise AdversarialEvalError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise AdversarialEvalError(code, message, context)


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


def _read_json(path: Path, code: str, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(code, f"{label} could not be read: {error}", {"path": str(path)})
        raise  # pragma: no cover - _fail always raises


def load_gold_corpus(repository_root: str | Path) -> dict[str, Any]:
    """Read the sealed Q01 corpus every baseline item is drawn from."""

    path = Path(repository_root) / GOLD_CORPUS_RELATIVE_PATH
    loaded = _read_json(path, "GOLD_CORPUS_UNREADABLE", "the sealed gold corpus")
    return _mapping(loaded, "gold corpus")


def _gold_case_labels(corpus: Mapping[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for index, entry in enumerate(_sequence(corpus.get("cases"), "gold cases")):
        case = _mapping(entry, f"gold cases[{index}]")
        labels[_text(case.get("case_id"), "case_id")] = _text(
            case.get("gold_label"), "gold_label"
        )
    if not labels:
        _fail("GOLD_CORPUS_UNREADABLE", "the sealed gold corpus declares no case")
    return labels


def gold_case_labels(repository_root: str | Path) -> dict[str, str]:
    """Case id to gold label, read from the sealed corpus rather than restated."""

    return _gold_case_labels(load_gold_corpus(repository_root))


def gold_labels(repository_root: str | Path) -> tuple[str, ...]:
    """The label vocabulary, taken from the sealed corpus that declares it."""

    return tuple(sorted(set(gold_case_labels(repository_root).values())))


def load_benchmark(repository_root: str | Path) -> dict[str, Any]:
    """Read the committed adversarial dataset."""

    path = Path(repository_root) / BENCHMARK_RELATIVE_PATH
    loaded = _read_json(path, "BENCHMARK_UNREADABLE", "the adversarial dataset")
    return _mapping(loaded, "benchmark")


def load_results(repository_root: str | Path) -> dict[str, Any]:
    """Read the committed machine-readable results artifact."""

    path = Path(repository_root) / RESULTS_RELATIVE_PATH
    loaded = _read_json(path, "RESULTS_UNREADABLE", "the adversarial results")
    return _mapping(loaded, "results")


def _validate_attack_classes(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    classes: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(
        _sequence(payload["attack_classes"], "attack_classes")
    ):
        record = _mapping(entry, f"attack_classes[{index}]")
        _exact_fields(record, _ATTACK_CLASS_FIELDS, f"attack_classes[{index}]")
        name = _text(record["attack_class"], "attack_class")
        if name in classes:
            _fail(
                "ATTACK_CLASS_DUPLICATED",
                "an attack class may be declared only once",
                {"attack_class": name},
            )
        marker = record["evidence_marker"]
        if marker is not None:
            marker = _text(marker, "evidence_marker")
        classes[name] = {
            "attack_class": name,
            "description": _text(record["description"], "description"),
            "evidence_marker": marker,
        }
    if not classes:
        _fail("INPUT_INVALID", "the benchmark declares no attack class")
    return classes


def _validate_label(
    value: object, label: str, vocabulary: Sequence[str], item_id: str
) -> str:
    text = _text(value, label)
    if text not in vocabulary:
        _fail(
            "LABEL_INVALID",
            f"{label} must be a label the sealed gold corpus declares",
            {"allowed": list(vocabulary), "item_id": item_id, "value": text},
        )
    return text


def _validate_baselines(
    payload: Mapping[str, Any],
    case_labels: Mapping[str, str],
    vocabulary: Sequence[str],
    seen: set[str],
) -> dict[str, dict[str, Any]]:
    baselines: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(
        _sequence(payload["baseline_items"], "baseline_items")
    ):
        record = _mapping(entry, f"baseline_items[{index}]")
        _exact_fields(record, _BASELINE_FIELDS, f"baseline_items[{index}]")
        item_id = _text(record["item_id"], "item_id")
        if item_id in seen:
            _fail("DUPLICATE_ITEM", "item ids must be unique", {"item_id": item_id})
        seen.add(item_id)
        gold_case_id = _text(record["gold_case_id"], "gold_case_id")
        if gold_case_id not in case_labels:
            _fail(
                "BASELINE_UNGROUNDED",
                "a baseline item must cite a case the sealed gold corpus carries",
                {"gold_case_id": gold_case_id, "item_id": item_id},
            )
        gold_label = _validate_label(
            record["gold_label"], "gold_label", vocabulary, item_id
        )
        if gold_label != case_labels[gold_case_id]:
            _fail(
                "GOLD_LABEL_MISMATCH",
                "a baseline item's gold label must equal the sealed corpus label",
                {
                    "corpus_label": case_labels[gold_case_id],
                    "gold_case_id": gold_case_id,
                    "item_id": item_id,
                    "item_label": gold_label,
                },
            )
        baselines[item_id] = {
            "evidence_text": _text(record["evidence_text"], "evidence_text"),
            "gold_case_id": gold_case_id,
            "gold_label": gold_label,
            "item_id": item_id,
            "predicted_label": _validate_label(
                record["predicted_label"], "predicted_label", vocabulary, item_id
            ),
            "statement": _text(record["statement"], "statement"),
        }
    if not baselines:
        _fail("INPUT_INVALID", "the benchmark declares no baseline item")
    return baselines


def _validate_adversarial(
    payload: Mapping[str, Any],
    baselines: Mapping[str, Mapping[str, Any]],
    classes: Mapping[str, Mapping[str, Any]],
    vocabulary: Sequence[str],
    seen: set[str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    paired: dict[str, str] = {}
    for index, entry in enumerate(
        _sequence(payload["adversarial_items"], "adversarial_items")
    ):
        record = _mapping(entry, f"adversarial_items[{index}]")
        _exact_fields(record, _ADVERSARIAL_FIELDS, f"adversarial_items[{index}]")
        item_id = _text(record["item_id"], "item_id")
        if item_id in seen:
            _fail("DUPLICATE_ITEM", "item ids must be unique", {"item_id": item_id})
        seen.add(item_id)
        baseline_id = _text(record["baseline_item_id"], "baseline_item_id")
        if baseline_id not in baselines:
            _fail(
                "BASELINE_MISSING",
                "an adversarial item must name a baseline item the dataset carries",
                {"baseline_item_id": baseline_id, "item_id": item_id},
            )
        if baseline_id in paired:
            _fail(
                "BASELINE_PAIRED_TWICE",
                "a baseline item may be perturbed by exactly one adversarial item",
                {
                    "baseline_item_id": baseline_id,
                    "item_ids": [paired[baseline_id], item_id],
                },
            )
        paired[baseline_id] = item_id
        baseline = baselines[baseline_id]

        attack_class = _text(record["attack_class"], "attack_class")
        if attack_class not in classes:
            _fail(
                "ATTACK_CLASS_UNDECLARED",
                "an item must name an attack class the dataset declares",
                {"attack_class": attack_class, "item_id": item_id},
            )
        statement = _text(record["statement"], "statement")
        evidence = _text(record["evidence_text"], "evidence_text")
        if statement == baseline["statement"] and evidence == baseline["evidence_text"]:
            _fail(
                "BASELINE_UNPERTURBED",
                "an adversarial item must differ from the baseline it perturbs",
                {"baseline_item_id": baseline_id, "item_id": item_id},
            )
        marker = classes[attack_class]["evidence_marker"]
        if marker is not None and marker not in evidence:
            _fail(
                "ATTACK_SIGNATURE_ABSENT",
                "the evidence text does not carry the signature its attack "
                "class declares",
                {
                    "attack_class": attack_class,
                    "evidence_marker": marker,
                    "item_id": item_id,
                },
            )

        gold_label = _validate_label(
            record["gold_label"], "gold_label", vocabulary, item_id
        )
        rationale = record["label_change_rationale"]
        changed = gold_label != baseline["gold_label"]
        if changed:
            if rationale is None or not str(rationale).strip():
                _fail(
                    "LABEL_CHANGE_UNJUSTIFIED",
                    "a perturbation that moves the gold label must record why",
                    {
                        "baseline_label": baseline["gold_label"],
                        "gold_label": gold_label,
                        "item_id": item_id,
                    },
                )
            rationale = _text(rationale, "label_change_rationale")
        elif rationale is not None:
            _fail(
                "RATIONALE_UNEXPECTED",
                "an item whose gold label matches its baseline records no "
                "change rationale",
                {"item_id": item_id},
            )

        items.append(
            {
                "attack_class": attack_class,
                "baseline_item_id": baseline_id,
                "evidence_text": evidence,
                "gold_label": gold_label,
                "item_id": item_id,
                "label_change_rationale": rationale,
                "label_changed": changed,
                "predicted_label": _validate_label(
                    record["predicted_label"], "predicted_label", vocabulary, item_id
                ),
                "statement": statement,
            }
        )
    if not items:
        _fail("INPUT_INVALID", "the benchmark declares no adversarial item")

    unpaired = sorted(set(baselines) - set(paired))
    if unpaired:
        _fail(
            "BASELINE_UNPAIRED",
            "every baseline item must be perturbed by exactly one adversarial item",
            {"baseline_item_ids": unpaired},
        )
    unpopulated = sorted(
        name
        for name in classes
        if not any(item["attack_class"] == name for item in items)
    )
    if unpopulated:
        _fail(
            "ATTACK_CLASS_UNPOPULATED",
            "a declared attack class must carry at least one item",
            {"attack_classes": unpopulated},
        )
    return items


def _accuracy(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    correct = sum(
        1 for record in records if record["predicted_label"] == record["gold_label"]
    )
    return {
        "accuracy": correct / len(records) if records else None,
        "correct": correct,
        "item_count": len(records),
        "missed_item_ids": sorted(
            record["item_id"]
            for record in records
            if record["predicted_label"] != record["gold_label"]
        ),
    }


def _rejection(
    records: Sequence[Mapping[str, Any]], false_claim_label: str
) -> dict[str, Any]:
    known_false = [
        record for record in records if record["gold_label"] == false_claim_label
    ]
    rejected = [
        record
        for record in known_false
        if record["predicted_label"] == false_claim_label
    ]
    rejected_ids = {record["item_id"] for record in rejected}
    return {
        "admitted_item_ids": sorted(
            record["item_id"]
            for record in known_false
            if record["item_id"] not in rejected_ids
        ),
        "known_false_count": len(known_false),
        "rate": len(rejected) / len(known_false) if known_false else None,
        "rejected_count": len(rejected),
    }


def evaluate(payload: Mapping[str, Any], repository_root: str | Path) -> SealedReport:
    """Validate the pairing, measure the robustness delta, and seal the report."""

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

    gold_corpus = load_gold_corpus(repository_root)
    declared_gold_identity = {
        "corpus_id": _text(gold_ref["corpus_id"], "corpus_id"),
        "corpus_version": _text(gold_ref["corpus_version"], "corpus_version"),
    }
    actual_gold_identity = {
        "corpus_id": gold_corpus.get("corpus_id"),
        "corpus_version": gold_corpus.get("corpus_version"),
    }
    if (
        not all(
            isinstance(value, str) and bool(value.strip())
            for value in actual_gold_identity.values()
        )
        or actual_gold_identity != declared_gold_identity
    ):
        _fail(
            "GOLD_CORPUS_REF_MISMATCH",
            "the dataset must cite the identity declared by the sealed gold corpus",
            {
                "actual": actual_gold_identity,
                "declared": declared_gold_identity,
            },
        )

    case_labels = _gold_case_labels(gold_corpus)
    vocabulary = tuple(sorted(set(case_labels.values())))
    false_claim_label = _text(benchmark["false_claim_label"], "false_claim_label")
    if false_claim_label not in vocabulary:
        _fail(
            "LABEL_INVALID",
            "the false-claim label must be a label the sealed gold corpus declares",
            {"allowed": list(vocabulary), "value": false_claim_label},
        )

    classes = _validate_attack_classes(benchmark)
    seen: set[str] = set()
    baselines = _validate_baselines(benchmark, case_labels, vocabulary, seen)
    adversarial = _validate_adversarial(benchmark, baselines, classes, vocabulary, seen)

    baseline_records = [baselines[item["baseline_item_id"]] for item in adversarial]
    baseline_overall = _accuracy(baseline_records)
    adversarial_overall = _accuracy(adversarial)
    adversarial_rejection = _rejection(adversarial, false_claim_label)
    if adversarial_rejection["known_false_count"] == 0:
        _fail(
            "FALSE_CLAIM_COVERAGE_ABSENT",
            "no adversarial item carries the label that marks a known false claim",
            {"false_claim_label": false_claim_label},
        )

    per_class: list[dict[str, Any]] = []
    for name in sorted(classes):
        members = [item for item in adversarial if item["attack_class"] == name]
        paired = [baselines[item["baseline_item_id"]] for item in members]
        adversarial_side = _accuracy(members)
        baseline_side = _accuracy(paired)
        per_class.append(
            {
                "adversarial": adversarial_side,
                "attack_class": name,
                "baseline": baseline_side,
                "evidence_marker": classes[name]["evidence_marker"],
                "item_ids": sorted(item["item_id"] for item in members),
                "label_changed_count": sum(
                    1 for item in members if item["label_changed"]
                ),
                "robustness_delta": (
                    adversarial_side["accuracy"] - baseline_side["accuracy"]
                ),
            }
        )

    report: dict[str, Any] = {
        "adversarial": adversarial_overall,
        "attack_classes": per_class,
        "baseline": baseline_overall,
        "benchmark_id": _text(benchmark["benchmark_id"], "benchmark_id"),
        "counts": {
            "adversarial_items": len(adversarial),
            "attack_classes": len(classes),
            "baseline_items": len(baselines),
            "label_changed_items": sum(
                1 for item in adversarial if item["label_changed"]
            ),
        },
        "dataset_hash": declared_hash,
        "evaluated_at": _text(benchmark["evaluated_at"], "evaluated_at"),
        "false_claim_rejection": {
            "adversarial": adversarial_rejection,
            "baseline": _rejection(baseline_records, false_claim_label),
            "false_claim_label": false_claim_label,
        },
        "gold_corpus_ref": {
            "corpus_id": actual_gold_identity["corpus_id"],
            "corpus_version": actual_gold_identity["corpus_version"],
            "path": GOLD_CORPUS_RELATIVE_PATH,
        },
        "label_vocabulary": list(vocabulary),
        "pairing": {
            "baseline_items_paired": len(adversarial),
            "unpaired_baseline_item_ids": [],
        },
        "report_id": _text(benchmark["report_id"], "report_id"),
        "robustness_delta": (
            adversarial_overall["accuracy"] - baseline_overall["accuracy"]
        ),
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
