"""Fixtures for the W05 resume, cancel and drift reassessment suites.

Every record is built by the module that owns its shape rather than typed out as
a literal: checkpoints and stop certificates by ``evolution_chamber.checkpoint``,
evaluator bundles and holdout manifests by ``verifier_firewall.firewall``, the
node graph by the F05 loader reading the workflow.  A fixture the canonical
schema would refuse tests nothing but the fixture, and a fixture that restated a
component name would keep passing after the vocabulary moved.

The damaged variants are hand-built on purpose.  A healthy runtime cannot
produce a checkpoint missing a component or one whose digest no longer matches,
because the builder refuses — and those are exactly the resume points the
workflow exists to catch, so they are constructed from a healthy one and then
broken.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from epistemic_foundry.domain.hashing import hash_excluding
from epistemic_foundry.evolution.v4_f05 import Transition, load_graph
from epistemic_foundry.evolution_chamber.checkpoint import (
    ADVERSE_STOPS,
    CHECKPOINT_COMPONENTS,
    ORDERLY_STOPS,
    build_evolution_checkpoint,
    build_stop_certificate,
)
from epistemic_foundry.governance.quarantine import DEFECT_CLASSES
from epistemic_foundry.verifier_firewall.firewall import (
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)

ROOT = Path(__file__).resolve().parents[5]
GRAPH = load_graph(ROOT)

#: The loop the EVOLVE cycle actually closes: the committed checkpoint returns
#: to parent selection.  Read from the workflow through the machine's loader by
#: the schema-and-type suite, which is what keeps these two names honest.
LOOP_EXIT = "commit_evolution_checkpoint"
LOOP_ENTRY = "select_epistemic_parents"

RUN_ID = "ER-W05-1"
OTHER_RUN_ID = "ER-W05-9"
SEALED_AT = "2026-08-03T00:00:00.000Z"
CREATED_AT = "2026-08-03T01:00:00.000Z"
RESUMED_AT = "2026-08-03T02:00:00.000Z"
RECORDED_AT = "2026-08-03T03:00:00.000Z"
REASSESSED_AT = "2026-08-03T04:00:00.000Z"

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64

#: A defect class taken from the quarantine module's vocabulary, never typed.
A_DEFECT_CLASS = DEFECT_CLASSES[0]

#: Stop reasons drawn from the module that classifies them, so a vocabulary
#: change breaks these fixtures rather than letting them name a stop the
#: checkpoint module no longer recognises.
AN_ORDERLY_STOP = sorted(ORDERLY_STOPS)[0]
AN_ADVERSE_STOP = sorted(ADVERSE_STOPS)[0]

#: One component name, read from the declaring module, used to break a
#: checkpoint in the negative suites.
A_COMPONENT = sorted(CHECKPOINT_COMPONENTS)[0]


# -- resume points -------------------------------------------------------


def checkpoint(index: int = 1, *, run_id: str = RUN_ID) -> dict[str, Any]:
    """A committed resume point: all seven components, sealed together."""
    return build_evolution_checkpoint(
        evolution_run_id=run_id,
        generation=index,
        population_artifact_ids=[f"POP-{index}"],
        archive_snapshot_id=f"ARCH-{index}",
        island_state_ids=[f"ISL-{index}"],
        operator_bandit_state_id=f"BANDIT-{index}",
        evaluator_bundle_hash=DIGEST_A,
        budget_state_id=f"BUDGET-{index}",
        sequential_testing_ledger_id=f"LEDGER-{index}",
        checkpoint_id=f"ECP-W05-{index}",
        created_at=CREATED_AT,
    )


def incomplete_checkpoint(index: int = 1) -> dict[str, Any]:
    """A resume point that lost a component, with its digest re-derived.

    The digest is recomputed so the record is self-consistent: the point is that
    a partial capture is refused for being partial, not for failing a hash.
    """
    record = checkpoint(index)
    record[A_COMPONENT] = [] if isinstance(record[A_COMPONENT], list) else ""
    record["checkpoint_hash"] = hash_excluding(record, "checkpoint_hash")
    return record


def uncommitted_checkpoint(index: int = 1) -> dict[str, Any]:
    """A complete capture that was never committed, so it carries no id."""
    record = checkpoint(index)
    record.pop("checkpoint_id")
    record["checkpoint_hash"] = hash_excluding(record, "checkpoint_hash")
    return record


def tampered_checkpoint(index: int = 1) -> dict[str, Any]:
    """A committed resume point edited after sealing, digest left behind."""
    record = checkpoint(index)
    record["budget_state_id"] = "BUDGET-EDITED"
    return record


# -- runs ----------------------------------------------------------------


def forward_path() -> list[Transition]:
    """One legal forward move per declared dependency in the graph."""
    return [
        Transition(source=upstream, target=node)
        for node in GRAPH.nodes
        for upstream in GRAPH.depends_on(node)
    ]


def loop_contract(max_iterations: int = 3, dry_rounds_required: int = 1) -> dict:
    return {
        "loop_id": "LOOP-EVOLVE-W05",
        "workflow_id": "evolution_chamber_cycle",
        "entry_node_id": LOOP_ENTRY,
        "exit_node_id": LOOP_EXIT,
        "max_iterations": max_iterations,
        "dry_rounds_required": dry_rounds_required,
    }


def stop_certificate(
    *,
    reason: str = AN_ORDERLY_STOP,
    checkpoint_id: str = "ECP-W05-1",
    run_id: str = RUN_ID,
    conditions: tuple[str, ...] = ("the operator asked the search to stop",),
    unresolved: tuple[str, ...] = ("CAND-7",),
    unassessed: tuple[str, ...] = ("NICHE-3",),
) -> dict[str, Any]:
    """A stop certificate in the canonical shape, built by its owner."""
    return build_stop_certificate(
        evolution_run_id=run_id,
        stop_reason=reason,
        conditions_observed=list(conditions),
        unresolved_candidates=list(unresolved),
        unassessed_niches=list(unassessed),
        checkpoint_id=checkpoint_id,
        certificate_id="ESC-W05-1",
    )


def resume_arguments(**overrides: Any) -> dict[str, Any]:
    """A run resumed from a committed checkpoint and carried to a stop."""
    arguments: dict[str, Any] = {
        "checkpoint": checkpoint(),
        "continuation": forward_path(),
        "loop_contract": loop_contract(),
        "stop_certificate": stop_certificate(),
        "resumed_at": RESUMED_AT,
        "dry_rounds_observed": 1,
        "resume_id": "EWR-W05-1",
    }
    arguments.update(overrides)
    return arguments


# -- cancellation --------------------------------------------------------


def cancel_arguments(**overrides: Any) -> dict[str, Any]:
    """A cancel that leaves two candidates and one niche unfinished."""
    arguments: dict[str, Any] = {
        "evolution_run_id": RUN_ID,
        "stop_reason": AN_ORDERLY_STOP,
        "conditions_observed": ["the operator asked the search to stop"],
        "checkpoint": checkpoint(),
        "proposed_candidate_ids": ["CAND-1", "CAND-2", "CAND-3"],
        "evaluated_candidate_ids": ["CAND-1"],
        "mapped_niche_ids": ["NICHE-1", "NICHE-2"],
        "assessed_niche_ids": ["NICHE-1"],
        "recorded_at": RECORDED_AT,
        "cancellation_id": "EWC-W05-1",
        "certificate_id": "ESC-W05-2",
    }
    arguments.update(overrides)
    return arguments


# -- evaluator and drift -------------------------------------------------


def holdout() -> dict[str, Any]:
    return build_holdout_manifest(
        evaluator_id="EVAL-W05-1",
        split_strategy="temporal",
        public_partition_refs=["PUB-1"],
        hidden_partition_handles=["HID-1"],
        ood_partition_handles=["OOD-1"],
        adversarial_partition_handles=["ADV-1"],
        content_hashes=[DIGEST_A],
        acl_policy_hash=DIGEST_B,
        log_redaction_policy="drop hidden handles from every log line",
        cache_isolation_policy="per-run cache, never shared with generators",
        holdout_id="HO-W05-1",
        sealed_at=SEALED_AT,
    )


def sealed_bundle(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    record = manifest or holdout()
    return build_evaluator_bundle(
        evaluator_version="4.0.0",
        code_artifact_id="EVCODE-1",
        code_hash=DIGEST_A,
        metric_contract_hash=DIGEST_B,
        environment_digest=DIGEST_C,
        dependency_lock_hash=DIGEST_A,
        data_contract_hash=DIGEST_B,
        policy_bundle_hash=DIGEST_C,
        qualification_report_id="QR-1",
        holdout_manifest_id=str(record["holdout_id"]),
        evaluator_id=str(record["evaluator_id"]),
        sealed_at=SEALED_AT,
    )


def firewall() -> VerifierFirewall:
    manifest = holdout()
    return VerifierFirewall(
        sealed_bundle(manifest),
        manifest,
        holdout_read_principal_ids=["PRIN-AUDITOR-1"],
    )


def drifted_bundle() -> dict[str, Any]:
    """The evaluator as it now stands: one metric contract later."""
    record = sealed_bundle()
    record["metric_contract_hash"] = DIGEST_C
    return record


def disguised_bundle() -> dict[str, Any]:
    """A drifted evaluator whose recorded digest was rewritten to match.

    This is the case a version label or a stored hash cannot catch, and the one
    the firewall's content recomputation exists for.
    """
    record = drifted_bundle()
    record["bundle_hash"] = hash_excluding(record, "bundle_hash")
    return record


def comparisons(sealed_id: str = "EVAL-W05-1") -> list[dict[str, Any]]:
    """Two comparisons under the sealed evaluator and one under another."""
    return [
        {
            "comparison_id": "CMP-2",
            "evaluator_bundle_id": sealed_id,
            "candidate_ids": ["CAND-1", "CAND-2"],
            "recorded_at": RECORDED_AT,
        },
        {
            "comparison_id": "CMP-1",
            "evaluator_bundle_id": sealed_id,
            "candidate_ids": ["CAND-3", "CAND-4"],
            "recorded_at": RECORDED_AT,
        },
        {
            "comparison_id": "CMP-3",
            "evaluator_bundle_id": "EVAL-W05-OTHER",
            "candidate_ids": ["CAND-5"],
            "recorded_at": RECORDED_AT,
        },
    ]


def reassessment_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "firewall": firewall(),
        "current_bundle": drifted_bundle(),
        "comparisons": comparisons(),
        "source_run_id": RUN_ID,
        "defect_class": A_DEFECT_CLASS,
        "evidence_artifact_ids": ["EV-1", "EV-2"],
        "proposed_change": "re-derive the metric contract before the next seal",
        "reassessed_at": REASSESSED_AT,
        "reassessment_id": "EWR-W05-2",
        "proposal_id": "EMP-W05-1",
    }
    arguments.update(overrides)
    return arguments
