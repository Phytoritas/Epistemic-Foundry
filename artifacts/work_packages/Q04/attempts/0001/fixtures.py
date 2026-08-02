"""Fixtures for the Q04 benchmark-gate suites.

Every fixture starts from the committed dataset rather than from a hand-built
approximation, so a refusal test proves that the real benchmark would be
refused after one specific edit — not that some invented payload is invalid.
Each builder takes a mutation callable, applies it to a deep copy and reseals
the dataset hash, because a payload that still carries the old hash would be
refused by ``DATASET_HASH_MISMATCH`` before the edit under test was ever
reached.  ``unsealed`` deliberately skips the reseal; that is the one case
where the stale hash *is* the thing being tested.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import adversarial_harness
import time_sliced_harness

ROOT = Path(__file__).resolve().parents[5]

Mutation = Callable[[dict[str, Any]], None]


def time_sliced_payload() -> dict[str, Any]:
    """The committed time-sliced dataset, deep-copied so tests may edit it."""

    return copy.deepcopy(time_sliced_harness.load_benchmark(ROOT))


def adversarial_payload() -> dict[str, Any]:
    """The committed adversarial dataset, deep-copied so tests may edit it."""

    return copy.deepcopy(adversarial_harness.load_benchmark(ROOT))


def sealed_time_sliced(mutate: Mutation | None = None) -> dict[str, Any]:
    payload = time_sliced_payload()
    if mutate is not None:
        mutate(payload)
    payload["dataset_hash"] = time_sliced_harness.hash_excluding(
        payload, "dataset_hash"
    )
    return payload


def sealed_adversarial(mutate: Mutation | None = None) -> dict[str, Any]:
    payload = adversarial_payload()
    if mutate is not None:
        mutate(payload)
    payload["dataset_hash"] = adversarial_harness.hash_excluding(
        payload, "dataset_hash"
    )
    return payload


def unsealed_time_sliced(mutate: Mutation) -> dict[str, Any]:
    """A mutated dataset that keeps its stale hash, for the seal test itself."""

    payload = time_sliced_payload()
    mutate(payload)
    return payload


def unsealed_adversarial(mutate: Mutation) -> dict[str, Any]:
    """A mutated dataset that keeps its stale hash, for the seal test itself."""

    payload = adversarial_payload()
    mutate(payload)
    return payload


#: Everything the two gates read off disk, in the layout they expect.
MIRRORED_FILES = (
    "evals/gold/insight_gold_cases.json",
    "evals/time_sliced/time_sliced_cases.json",
    "evals/time_sliced/time_sliced_results.json",
    "evals/adversarial/adversarial_cases.json",
    "evals/adversarial/adversarial_results.json",
)


def mirror_repository(destination: Path) -> Path:
    """Copy the committed files into a throwaway root.

    The read-side refusals — an absent dataset, an absent gold corpus, a
    results artifact that no longer matches — can only be exercised honestly
    by removing or editing a file, which must never happen to the committed
    tree.  So they are exercised against a byte-identical copy instead.
    """

    for relative in MIRRORED_FILES:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    return destination


def _find(records: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    for record in records:
        if record[key] == value:
            return record
    raise AssertionError(f"{key}={value}")


def time_sliced_item(payload: dict[str, Any], item_id: str) -> dict[str, Any]:
    return _find(payload["items"], "item_id", item_id)


def time_sliced_slice(payload: dict[str, Any], slice_id: str) -> dict[str, Any]:
    return _find(payload["slices"], "slice_id", slice_id)


def time_sliced_document(payload: dict[str, Any], document_id: str) -> dict[str, Any]:
    return _find(payload["documents"], "document_id", document_id)


def adversarial_item(payload: dict[str, Any], item_id: str) -> dict[str, Any]:
    return _find(payload["adversarial_items"], "item_id", item_id)


def baseline_item(payload: dict[str, Any], item_id: str) -> dict[str, Any]:
    return _find(payload["baseline_items"], "item_id", item_id)


def attack_class(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return _find(payload["attack_classes"], "attack_class", name)
