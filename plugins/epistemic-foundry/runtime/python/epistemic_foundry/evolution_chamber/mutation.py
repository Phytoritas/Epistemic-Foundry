"""Mutation with authority-field immutability.

Contract source: `schemas/mutation-receipt.schema.json`.

`manifests/development_manifest.yaml` states the rule directly:

    Candidate, prompt, challenge and experiment evolution may not mutate
    Foundry authority, current evaluator, hidden holdout, policy, promotion
    gates or prior ledger history.

So the forbidden set is enforced by path before any change is applied, and the
receipt records `changed_paths` and `preserved_paths` computed from the actual
before/after states rather than from the operator's description of its own
edit. An operator that reports one thing and does another is caught by the diff.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding, sha256_of_payload
from ..domain.ids import new_id

#: Genome/candidate paths that carry authority. Mutating any of these would let
#: a candidate alter the rules it is evaluated against.
FORBIDDEN_MUTATION_PATHS: frozenset[str] = frozenset(
    {
        "evaluator_bundle_id",
        "holdout_manifest_id",
        "policy_bundle_id",
        "policy_hash",
        "promotion_recommendation",
        "promotion_decision_id",
        "granted_level",
        "status",
        "gate_decision_ids",
        "hard_gate_status",
        "approval_record_ids",
        "ledger_event_ids",
        "lineage_id",
        "provenance_hash",
        "random_seed",
        "spec_hash",
    }
)


class AuthorityMutationRefused(PermissionError):
    """A mutation attempted to change a field that carries authority."""


def _changed_paths(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Top-level keys whose canonical value differs, including add/remove."""
    keys = set(before) | set(after)
    changed: list[str] = []
    for key in sorted(keys):
        if key not in before or key not in after:
            changed.append(key)
            continue
        if sha256_of_payload(before[key]) != sha256_of_payload(after[key]):
            changed.append(key)
    return changed


def apply_mutation(
    candidate: Mapping[str, Any],
    changes: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply `changes` to `candidate`, refusing any authority-field edit.

    The check runs against the requested change set *and* the resulting diff, so
    a no-op write to a forbidden field is still refused: permitting it would
    make the boundary depend on whether the operator happened to pick the same
    value.
    """
    requested = set(changes) & FORBIDDEN_MUTATION_PATHS
    if requested:
        raise AuthorityMutationRefused(
            f"refusing mutation of authority field(s) {', '.join(sorted(requested))}: "
            "evolution may propose but may not certify itself"
        )
    mutated = dict(candidate)
    mutated.update(changes)
    escaped = set(_changed_paths(candidate, mutated)) & FORBIDDEN_MUTATION_PATHS
    if escaped:
        raise AuthorityMutationRefused(
            f"mutation changed authority field(s) {', '.join(sorted(escaped))} indirectly"
        )
    return mutated


def build_mutation_receipt(
    *,
    evolution_run_id: str,
    operator_id: str,
    input_candidates: Sequence[Mapping[str, Any]],
    output_candidate: Mapping[str, Any],
    effect_receipt_id: str,
    input_candidate_ids: Sequence[str] | None = None,
    output_candidate_id: str | None = None,
    validation_status: str = "PASS",
    warnings: Sequence[str] = (),
    mutation_receipt_id: str | None = None,
) -> dict[str, Any]:
    """Record a mutation with a diff-derived changed/preserved split.

    `changed_paths` and `preserved_paths` are computed from the first input and
    the output, never taken from the caller: a receipt that trusts the operator's
    self-description cannot detect an operator that edits more than it admits.
    """
    if not input_candidates:
        raise ValueError("a mutation receipt must reference at least one input candidate")
    baseline = input_candidates[0]
    changed = _changed_paths(baseline, output_candidate)
    escaped = set(changed) & FORBIDDEN_MUTATION_PATHS
    if escaped:
        raise AuthorityMutationRefused(
            f"refusing to record a mutation that changed authority field(s) "
            f"{', '.join(sorted(escaped))}"
        )
    preserved = sorted(set(baseline) - set(changed))

    receipt: dict[str, Any] = {
        "mutation_receipt_id": mutation_receipt_id or new_id("MR"),
        "evolution_run_id": evolution_run_id,
        "operator_id": operator_id,
        "input_candidate_ids": list(
            input_candidate_ids
            if input_candidate_ids is not None
            else [str(item.get("genome_id") or item.get("candidate_id")) for item in input_candidates]
        ),
        "output_candidate_id": output_candidate_id
        or str(output_candidate.get("genome_id") or output_candidate.get("candidate_id")),
        "changed_paths": changed,
        "preserved_paths": preserved,
        "validation_status": validation_status,
        "warnings": list(warnings),
        "effect_receipt_id": effect_receipt_id,
    }
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    validate_artifact("mutation-receipt", receipt)
    return receipt
