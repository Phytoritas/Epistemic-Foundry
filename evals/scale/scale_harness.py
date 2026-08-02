"""Y04 — 50/200/2000 corpus scale qualification and graceful load shedding.

This module qualifies system *behaviour* at the three tier sizes the release
ladder names (``EVOLUTION_MVP_50`` -> ``PILOT_200`` -> ``PRODUCTION_2000``) and
proves that, under offered load beyond a hard capacity, the system sheds the
excess *gracefully* rather than silently dropping or corrupting it.

Two sealed contracts are composed here, never restated:

* **Typed budgets (Y01, ``EF4-I28``).**  The enforcement and breach-policy
  vocabularies are read from ``schemas/budget-envelope.schema.json`` at load
  time; only the ``HARD_`` enforcement labels actually bound spend.  A tier
  "qualifies" only when every measured dimension stays at or under the tier's
  ``hard_limits`` — a hard-budget overrun is a failure, mirroring the
  ``PRODUCTION_2000`` gate ``hard_budget_overrun_rate: 0``.
* **Honest observability states (Y02, ``EF4-I23``).**  Every measured signal
  collapses to exactly one of ``OK`` / ``DEGRADED`` / ``UNAVAILABLE`` /
  ``UNKNOWN`` by the same rule the sealed ``result-state`` module uses: no
  samples is ``UNKNOWN`` (health is never assumed), samples but zero good is
  ``UNAVAILABLE``, good-ratio below objective is ``DEGRADED``, at or above is
  ``OK``.  A green tier therefore always corresponds to real measured evidence.

The corpus is **synthetic and deterministic**: every document is derived from
``(seed, index)`` with no clock and no randomness, so a tier's result hash
reproduces on replay.  This harness acquires no authority and certifies no
release: MASTER_SPEC line 1371 lists *real* 50/200/2,000-scale results (licensed
corpus, production topology) as conditional external evidence.  A dataset that
claims ``licensed_corpus`` or ``release_gate_certified`` is refused as an
overclaim (``SCALE_OVERCLAIM``), and every report records those facts as false.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: Repository root (evals/scale/scale_harness.py -> repo root is two parents up).
ROOT: Final = Path(__file__).resolve().parents[2]
#: Source of truth for the budget vocabulary composed by this harness.
BUDGET_SCHEMA_RELATIVE_PATH: Final = "schemas/budget-envelope.schema.json"
#: The synthetic corpus dataset this harness qualifies.
DATASET_RELATIVE_PATH: Final = "evals/scale/scale_corpus.json"

#: Enforcement labels bound spend iff they carry this prefix (EF4-I28).
HARD_PREFIX: Final = "HARD_"

#: The four honest result states (Y02 ``result-state`` module vocabulary).
RESULT_STATES: Final = ("OK", "DEGRADED", "UNAVAILABLE", "UNKNOWN")
#: The two honest dispositions an offered work item can terminate in.
DISPOSITIONS: Final = ("ADMITTED", "SHED")

#: The six hard-limit dimensions declared required by the budget schema.
LIMIT_DIMENSIONS: Final = (
    "tokens",
    "calls",
    "wall_seconds",
    "concurrency",
    "storage_bytes",
    "network_bytes",
)


class ScaleError(Exception):
    """A typed, fail-closed refusal raised by the scale harness."""

    def __init__(self, code: str, message: str, **context: Any) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.context = context


# --------------------------------------------------------------------------- #
# Canonical hashing (matches the sealed receipt writers: sorted-key compact
# JSON with the hash field removed).
# --------------------------------------------------------------------------- #
def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(value: Any, *, drop_key: str) -> str:
    payload = {k: v for k, v in value.items() if k != drop_key}
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# --------------------------------------------------------------------------- #
# Budget vocabulary — composed from the schema, never restated.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BudgetVocabulary:
    enforcement_labels: tuple[str, ...]
    breach_policies: tuple[str, ...]
    limit_dimensions: tuple[str, ...]

    def bounds_spend(self, enforcement: str) -> bool:
        """Only ``HARD_`` labels bound spend (EF4-I28)."""
        if enforcement not in self.enforcement_labels:
            raise ScaleError(
                "BUDGET_VOCABULARY_INVALID",
                "enforcement label is not a member of the sealed vocabulary",
                enforcement=enforcement,
            )
        return enforcement.startswith(HARD_PREFIX)


def load_budget_vocabulary(root: Path = ROOT) -> BudgetVocabulary:
    schema = json.loads((root / BUDGET_SCHEMA_RELATIVE_PATH).read_text("utf-8"))
    props = schema.get("properties", {})
    enforcement = tuple(props.get("enforcement", {}).get("enum", ()))
    breach = tuple(props.get("breach_policy", {}).get("enum", ()))
    hard_limits = props.get("hard_limits", {})
    dimensions = tuple(hard_limits.get("properties", {}).keys())
    required = hard_limits.get("required", [])
    if not enforcement or not any(e.startswith(HARD_PREFIX) for e in enforcement):
        raise ScaleError(
            "BUDGET_VOCABULARY_INVALID", "no HARD_ enforcement label in schema"
        )
    if not breach:
        raise ScaleError("BUDGET_VOCABULARY_INVALID", "breach_policy enum is empty")
    if set(dimensions) != set(required) or set(dimensions) != set(LIMIT_DIMENSIONS):
        raise ScaleError(
            "BUDGET_VOCABULARY_INVALID",
            "hard_limits dimensions drifted from the sealed contract",
            dimensions=list(dimensions),
        )
    return BudgetVocabulary(enforcement, breach, dimensions)


# --------------------------------------------------------------------------- #
# Honest result state — the sealed Y02 rule, applied to a measured window.
# --------------------------------------------------------------------------- #
def evaluate_state(
    sample_count: int, good_count: int, objective: float
) -> dict[str, Any]:
    if good_count > sample_count:
        raise ScaleError(
            "STATE_INPUT_INVALID",
            "good_count cannot exceed sample_count",
            good_count=good_count,
            sample_count=sample_count,
        )
    if not (0.0 < objective <= 1.0):
        raise ScaleError(
            "STATE_INPUT_INVALID", "objective must be in (0, 1]", objective=objective
        )
    if sample_count == 0:
        return {
            "state": "UNKNOWN",
            "sample_count": 0,
            "good_count": 0,
            "observed_ratio": None,
            "objective": objective,
        }
    ratio = good_count / sample_count
    if good_count == 0:
        state = "UNAVAILABLE"
    elif ratio >= objective:
        state = "OK"
    else:
        state = "DEGRADED"
    return {
        "state": state,
        "sample_count": sample_count,
        "good_count": good_count,
        "observed_ratio": ratio,
        "objective": objective,
    }


# --------------------------------------------------------------------------- #
# Deterministic synthetic corpus + a pure-function processing pipeline.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Document:
    index: int
    token_cost: int
    latency_ms: int
    kind: str  # ground truth: "VALID" or "POISON"


def _seed_int(seed: str, index: int) -> int:
    digest = hashlib.sha256(f"{seed}:{index}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def generate_document(gen: dict[str, Any], index: int) -> Document:
    h = _seed_int(gen["seed"], index)
    token_cost = gen["base_token_cost"] + (h % gen["token_spread"])
    latency_ms = gen["base_latency_ms"] + ((h >> 16) % gen["latency_spread"])
    kind = "POISON" if index % gen["poison_modulus"] == 0 else "VALID"
    return Document(
        index=index, token_cost=token_cost, latency_ms=latency_ms, kind=kind
    )


def generate_corpus(gen: dict[str, Any], size: int) -> list[Document]:
    return [generate_document(gen, i) for i in range(size)]


def classify(doc: Document, *, corrupt_indices: frozenset[int] = frozenset()) -> str:
    """The system under test: reads the deterministic marker and labels the doc.

    ``corrupt_indices`` injects a mislabel so the qualification's correctness
    accounting can be shown to *catch* an error rather than rubber-stamp it.
    """
    predicted = doc.kind
    if doc.index in corrupt_indices:
        predicted = "VALID" if predicted == "POISON" else "POISON"
    return predicted


# --------------------------------------------------------------------------- #
# Scale qualification: one tier.
# --------------------------------------------------------------------------- #
def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = math.ceil(0.95 * len(ordered)) - 1
    return ordered[max(0, rank)]


def qualify_tier(
    gen: dict[str, Any],
    tier: dict[str, Any],
    vocab: BudgetVocabulary,
    *,
    corrupt_indices: frozenset[int] = frozenset(),
    cost_inflation: int = 0,
) -> dict[str, Any]:
    size = tier["size"]
    budget = tier["budget"]
    enforcement = budget["enforcement"]
    if enforcement not in vocab.enforcement_labels:
        raise ScaleError(
            "BUDGET_LABEL_UNKNOWN",
            "tier enforcement not in vocabulary",
            tier=tier["name"],
            enforcement=enforcement,
        )
    if budget["breach_policy"] not in vocab.breach_policies:
        raise ScaleError(
            "BREACH_POLICY_UNKNOWN",
            "tier breach_policy not in vocabulary",
            tier=tier["name"],
            breach_policy=budget["breach_policy"],
        )
    bounds = vocab.bounds_spend(enforcement)

    docs = generate_corpus(gen, size)
    latencies: list[int] = []
    tokens = 0
    correct = 0
    persisted = 0
    for doc in docs:
        predicted = classify(doc, corrupt_indices=corrupt_indices)
        tokens += doc.token_cost + cost_inflation
        latencies.append(doc.latency_ms)
        persisted += 1
        if predicted == doc.kind:
            correct += 1

    concurrency = budget["hard_limits"]["concurrency"]
    wall_seconds = math.ceil(sum(latencies) / concurrency / 1000)
    measured = {
        "tokens": tokens,
        "calls": size,
        "wall_seconds": wall_seconds,
        "concurrency": min(concurrency, size) if size else 0,
        "storage_bytes": size * 1024,
        "network_bytes": size * 1024,
    }

    # Reconciliation (EF4-I26): no silent partial completion.
    reconciliation = {
        "expected": size,
        "processed": len(docs),
        "persisted": persisted,
        "reconciled": size == len(docs) == persisted,
    }
    if not reconciliation["reconciled"]:
        raise ScaleError(
            "SILENT_PARTIAL_COMPLETION",
            "tier counts do not reconcile",
            tier=tier["name"],
            **reconciliation,
        )

    # Budget qualification: only enforced iff the label bounds spend.
    overruns = {}
    if bounds:
        for dim in vocab.limit_dimensions:
            limit = budget["hard_limits"][dim]
            if measured[dim] > limit:
                overruns[dim] = {"measured": measured[dim], "limit": limit}
    within_budget = len(overruns) == 0

    p95 = _p95(latencies)
    latency_ok = p95 <= tier["latency_p95_budget_ms"]
    state = evaluate_state(size, correct, tier["quality_objective"])

    qualified = bool(
        within_budget
        and latency_ok
        and state["state"] == "OK"
        and reconciliation["reconciled"]
    )
    report = {
        "tier": tier["name"],
        "size": size,
        "budget_enforcement": enforcement,
        "budget_bounds_spend": bounds,
        "breach_policy": budget["breach_policy"],
        "measured": measured,
        "hard_limits": budget["hard_limits"],
        "budget_overruns": overruns,
        "within_budget": within_budget,
        "latency_p95_ms": p95,
        "latency_p95_budget_ms": tier["latency_p95_budget_ms"],
        "latency_ok": latency_ok,
        "reconciliation": reconciliation,
        "quality_state": state,
        "qualified": qualified,
        # Honest breach surfacing: an overrun applies the tier's breach policy,
        # it is never silently absorbed.
        "breach_applied": None if within_budget else budget["breach_policy"],
    }
    return report


# --------------------------------------------------------------------------- #
# Graceful load shedding: composes the hard admission capacity (Y01) with an
# honest terminal accounting (Y02).
# --------------------------------------------------------------------------- #
def run_load_shedding(
    scenario: dict[str, Any],
    vocab: BudgetVocabulary,
    *,
    admit: int | None = None,
    declared_shed: int | None = None,
    forced_state: str | None = None,
    corrupt_admitted: int = 0,
) -> dict[str, Any]:
    offered = scenario["offered_load"]
    capacity = scenario["hard_admission_capacity"]
    if scenario["admission_enforcement"] not in vocab.enforcement_labels:
        raise ScaleError(
            "BUDGET_LABEL_UNKNOWN",
            "admission enforcement not in vocabulary",
            enforcement=scenario["admission_enforcement"],
        )
    if not vocab.bounds_spend(scenario["admission_enforcement"]):
        raise ScaleError(
            "ADMISSION_UNBOUNDED",
            "load shedding requires a HARD admission enforcement",
            **scenario,
        )
    if scenario["breach_policy"] not in vocab.breach_policies:
        raise ScaleError(
            "BREACH_POLICY_UNKNOWN",
            "scenario breach_policy not in vocabulary",
            breach_policy=scenario["breach_policy"],
        )

    # The graceful policy admits the full guaranteed capacity and sheds only the
    # excess. ``admit`` overrides this to let fail-closed tests probe misbehaviour.
    admitted = min(offered, capacity) if admit is None else admit
    if admitted > capacity:
        raise ScaleError(
            "ADMISSION_OVERRUN",
            "admitted work exceeds the hard admission capacity",
            admitted=admitted,
            capacity=capacity,
        )
    shed = (offered - admitted) if declared_shed is None else declared_shed

    # Exact terminal reconciliation (EF4-I26): every offered item is either
    # ADMITTED or SHED — nothing is silently dropped.
    if admitted + shed != offered:
        raise ScaleError(
            "SHED_RECONCILIATION_FAILURE",
            "admitted + shed does not equal offered load",
            admitted=admitted,
            shed=shed,
            offered=offered,
        )

    # Admitted work is processed; ``corrupt_admitted`` mislabels some so the
    # honest state can be shown to react rather than always reporting OK.
    good = max(0, admitted - corrupt_admitted)
    admitted_spend = {
        "tokens": admitted * scenario["per_item_token_cost"],
        "calls": admitted,
    }
    admitted_limits = scenario["admitted_budget"]["hard_limits"]
    admitted_within_budget = (
        admitted_spend["tokens"] <= admitted_limits["tokens"]
        and admitted_spend["calls"] <= admitted_limits["calls"]
    )

    # Honest state: shedding is real degradation of *offered* service, never a
    # shade of healthy. Full service with all-good is OK; any shed or any bad
    # admitted result is DEGRADED; zero good admitted is UNAVAILABLE.
    state = evaluate_state(admitted, good, 1.0)["state"]
    if shed > 0 and state == "OK":
        state = "DEGRADED"
    if forced_state is not None:
        if forced_state not in RESULT_STATES:
            raise ScaleError(
                "STATE_UNKNOWN_LABEL",
                "forced state is not a result state",
                forced_state=forced_state,
            )
        # A claim of health while work was shed or corrupted is dishonest.
        if forced_state == "OK" and (shed > 0 or good < admitted):
            raise ScaleError(
                "STATE_DISHONEST",
                "cannot report OK while load was shed or admitted work failed",
                shed=shed,
                good=good,
                admitted=admitted,
            )
        state = forced_state

    # Bounded degradation: the guaranteed hard capacity is always served.
    served_floor_met = admitted >= min(offered, capacity)
    partial = shed > 0
    report = {
        "scenario": scenario["name"],
        "offered_load": offered,
        "hard_admission_capacity": capacity,
        "admitted": admitted,
        "shed": shed,
        "shed_reason": scenario["shed_reason"] if shed else None,
        "reconciled": admitted + shed == offered,
        "admitted_good": good,
        "admitted_spend": admitted_spend,
        "admitted_within_budget": admitted_within_budget,
        "served_floor_met": served_floor_met,
        "bounded_degradation": served_floor_met and (admitted <= capacity),
        "state": state,
        "partial": partial,
        "breach_applied": scenario["breach_policy"] if partial else None,
        "graceful": bool(
            admitted + shed == offered
            and served_floor_met
            and admitted <= capacity
            and admitted_within_budget
            and good == admitted
            and (state == "DEGRADED" if partial else state == "OK")
        ),
    }
    return report


# --------------------------------------------------------------------------- #
# Dataset loading + overclaim guard + full evaluation.
# --------------------------------------------------------------------------- #
def load_dataset(root: Path = ROOT) -> dict[str, Any]:
    dataset = json.loads((root / DATASET_RELATIVE_PATH).read_text("utf-8"))
    if not dataset.get("synthetic", False):
        raise ScaleError(
            "SCALE_OVERCLAIM",
            "scale corpus must declare itself synthetic",
            dataset_id=dataset.get("dataset_id"),
        )
    if dataset.get("licensed_corpus", False) or dataset.get(
        "release_gate_certified", False
    ):
        raise ScaleError(
            "SCALE_OVERCLAIM",
            "synthetic corpus cannot claim a licensed corpus or a certified release gate",
            dataset_id=dataset.get("dataset_id"),
        )
    expected = dataset.get("dataset_hash")
    if expected and expected != "sha256:PLACEHOLDER":
        actual = content_hash(dataset, drop_key="dataset_hash")
        if actual != expected:
            raise ScaleError(
                "DATASET_HASH_MISMATCH",
                "dataset hash does not match content",
                expected=expected,
                actual=actual,
            )
    return dataset


def evaluate_scale(root: Path = ROOT) -> dict[str, Any]:
    dataset = load_dataset(root)
    vocab = load_budget_vocabulary(root)
    gen = dataset["generator"]
    tiers = [qualify_tier(gen, tier, vocab) for tier in dataset["tiers"]]
    report = {
        "report_id": f"{dataset['dataset_id']}-SCALE",
        "dataset_id": dataset["dataset_id"],
        "synthetic": True,
        "licensed_corpus": False,
        "release_gate_certified": False,
        "status": "PASS" if all(t["qualified"] for t in tiers) else "FAIL",
        "tiers": tiers,
        "report_hash": "sha256:PLACEHOLDER",
    }
    report["report_hash"] = content_hash(report, drop_key="report_hash")
    return report


def evaluate_load_shedding(root: Path = ROOT) -> dict[str, Any]:
    dataset = load_dataset(root)
    vocab = load_budget_vocabulary(root)
    result = run_load_shedding(dataset["overload_scenario"], vocab)
    report = {
        "report_id": f"{dataset['dataset_id']}-LOAD-SHEDDING",
        "dataset_id": dataset["dataset_id"],
        "synthetic": True,
        "status": "PASS" if result["graceful"] else "FAIL",
        "result": result,
        "report_hash": "sha256:PLACEHOLDER",
    }
    report["report_hash"] = content_hash(report, drop_key="report_hash")
    return report


if __name__ == "__main__":
    import sys

    kind = sys.argv[1] if len(sys.argv) > 1 else "scale"
    out = evaluate_scale() if kind == "scale" else evaluate_load_shedding()
    print(json.dumps(out, indent=2, ensure_ascii=False))
