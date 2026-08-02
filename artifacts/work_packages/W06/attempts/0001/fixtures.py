"""Fixtures for the W06 crash-recovery, replay and reconciliation suites.

Every record is built by the module that owns its shape rather than typed as a
literal: checkpoints and stop certificates by ``evolution_chamber.checkpoint``,
the resume through the sealed W05 workflow, the replay report by
``release.replay``, the schedule integration by the sealed N06 gate, evaluator
bundles and holdout manifests by ``verifier_firewall.firewall``, and the node
graph by the F05 loader reading the workflow.  A fixture the canonical schema
would refuse tests nothing but the fixture.

The crash-damaged variants — a roster the resume lost, a candidate driven into
two terminal states, a replay that resolved its pins but did not reproduce — are
built from a healthy recovery and then broken, because a healthy runtime cannot
produce them and they are exactly what the gate exists to catch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.evolution.v4_f05 import Transition, load_graph
from epistemic_foundry.evolution_chamber.checkpoint import (
    ORDERLY_STOPS,
    build_evolution_checkpoint,
    build_stop_certificate,
)
from epistemic_foundry.governance.quarantine import (
    DEFECT_CLASSES,
    build_evaluator_mutation_proposal,
)
from epistemic_foundry.recovery.v4_w05 import reassess_after_evaluator_drift
from epistemic_foundry.release.replay import (
    REQUIRED_PIN_CATEGORIES,
    build_replay_report,
)
from epistemic_foundry.scheduler.v4_n05 import (
    CONCURRENCY_DIMENSION,
    EVALUATION_LANE,
    LANE_CONCLUDE,
    LANE_ENQUEUE,
    LANE_START,
    LANES,
    PERSISTENCE_LANE,
    PROPOSAL_LANE,
    LaneEvent,
)
from epistemic_foundry.scheduler.v4_n06 import (
    ADMISSION_DEFERRAL,
    seal_integration_record,
    verify_integration,
)
from epistemic_foundry.verifier_firewall.firewall import (
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)

ROOT = Path(__file__).resolve().parents[5]
GRAPH = load_graph(ROOT)

#: The EVOLVE loop the committed checkpoint returns across, read from the F05
#: workflow the same way the sealed machine reads it.
LOOP_EXIT = "commit_evolution_checkpoint"
LOOP_ENTRY = "select_epistemic_parents"

RUN_ID = "ER-W06-1"
OTHER_RUN_ID = "ER-W06-9"
SEALED_AT = "2026-08-03T00:00:00.000Z"
CREATED_AT = "2026-08-03T01:00:00.000Z"
RESUMED_AT = "2026-08-03T02:00:00.000Z"
REASSESSED_AT = "2026-08-03T04:00:00.000Z"

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64

A_DEFECT_CLASS = DEFECT_CLASSES[0]
AN_ORDERLY_STOP = sorted(ORDERLY_STOPS)[0]

#: The replay mode, read from the canonical replay-report schema rather than
#: named, so a vocabulary change breaks the fixture instead of hiding.
STRICT_MODE = default_registry().document("replay-report")["properties"]["mode"][
    "enum"
][0]


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
        checkpoint_id=f"ECP-W06-{index}",
        created_at=CREATED_AT,
    )


def forward_path() -> list[Transition]:
    """One legal forward move per declared dependency in the graph."""
    return [
        Transition(source=upstream, target=node)
        for node in GRAPH.nodes
        for upstream in GRAPH.depends_on(node)
    ]


def loop_contract(max_iterations: int = 3, dry_rounds_required: int = 1) -> dict:
    return {
        "loop_id": "LOOP-EVOLVE-W06",
        "workflow_id": "evolution_chamber_cycle",
        "entry_node_id": LOOP_ENTRY,
        "exit_node_id": LOOP_EXIT,
        "max_iterations": max_iterations,
        "dry_rounds_required": dry_rounds_required,
    }


def stop_certificate(
    *,
    reason: str = AN_ORDERLY_STOP,
    checkpoint_id: str = "ECP-W06-1",
    run_id: str = RUN_ID,
) -> dict[str, Any]:
    return build_stop_certificate(
        evolution_run_id=run_id,
        stop_reason=reason,
        conditions_observed=["the host process crashed and was restarted"],
        unresolved_candidates=["CAND-3"],
        unassessed_niches=["NICHE-1"],
        checkpoint_id=checkpoint_id,
        certificate_id="ESC-W06-1",
    )


# -- replay --------------------------------------------------------------


def replay_report(
    *,
    source_run_id: str = RUN_ID,
    unavailable_pins: tuple[str, ...] = (),
    mismatches: int = 0,
    verdict_differences: tuple[str, ...] = (),
    gate_differences: tuple[str, ...] = (),
) -> dict[str, Any]:
    """A byte-for-byte replay of the recovered run, built by its owner.

    All required pin categories are named so the run is comparable, and with no
    mismatches or differences the owner derives ``EXACT`` — the only equivalence
    a recovery may be built on.
    """
    return build_replay_report(
        source_run_id=source_run_id,
        replay_run_id="REPLAY-W06-1",
        mode=STRICT_MODE,
        pinned_artifacts=[f"{category}:PIN" for category in REQUIRED_PIN_CATEGORIES],
        unavailable_pins=list(unavailable_pins),
        artifact_hash_matches=7,
        artifact_hash_mismatches=mismatches,
        gate_differences=list(gate_differences),
        verdict_differences=list(verdict_differences),
        replay_id="RR-W06-1",
        created_at=CREATED_AT,
    )


# -- schedule integration ------------------------------------------------


def _limits() -> dict[str, Any]:
    return {
        PROPOSAL_LANE: {CONCURRENCY_DIMENSION: 2},
        EVALUATION_LANE: {CONCURRENCY_DIMENSION: 2},
        PERSISTENCE_LANE: {CONCURRENCY_DIMENSION: 2},
    }


def _serial_events(candidate: str) -> list[LaneEvent]:
    return [
        event
        for lane in LANES
        for event in (
            LaneEvent(lane, LANE_ENQUEUE, candidate),
            LaneEvent(lane, LANE_START, candidate),
            LaneEvent(lane, LANE_CONCLUDE, candidate),
        )
    ]


def integration_report(*, run_id: str = RUN_ID) -> dict[str, Any]:
    """A clean N06 verdict for one candidate walking every lane in order."""
    events = _serial_events("CAND-1")
    return verify_integration(
        ROOT,
        proposed=["CAND-1"],
        events=events,
        lane_limits=_limits(),
        admission_policy=ADMISSION_DEFERRAL,
        progress_horizon=len(events),
        worker_assignments={"CAND-1": "WORKER-A"},
    )


def sealed_integration_record(*, run_id: str = RUN_ID) -> dict[str, Any]:
    return seal_integration_record(integration_report(), run_id=run_id)


# -- candidate roster ----------------------------------------------------

#: A fan-out that reconciles: three candidates committed before the crash, all
#: three persisted after the resume, nothing lost and nothing counted twice.
EXPECTED = ("CAND-1", "CAND-2", "CAND-3")


def reconcile_arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "expected_candidate_ids": list(EXPECTED),
        "proposed": list(EXPECTED),
        "generated": list(EXPECTED),
        "evaluated": list(EXPECTED),
        "persisted": list(EXPECTED),
        "failed": [],
        "cancelled": [],
    }
    arguments.update(overrides)
    return arguments


# -- recovery ------------------------------------------------------------


def recovery_arguments(**overrides: Any) -> dict[str, Any]:
    """A crash recovery whose every surface agrees on one run."""
    arguments: dict[str, Any] = {
        "checkpoint": checkpoint(),
        "continuation": forward_path(),
        "loop_contract": loop_contract(),
        "stop_certificate": stop_certificate(),
        "resumed_at": RESUMED_AT,
        "replay_report": replay_report(),
        "dry_rounds_observed": 1,
        "resume_id": "EWR-W06-1",
        "recovery_id": "RGC-W06-1",
        **reconcile_arguments(),
    }
    arguments.update(overrides)
    return arguments


# -- evaluator drift / future-only update --------------------------------


def holdout() -> dict[str, Any]:
    return build_holdout_manifest(
        evaluator_id="EVAL-W06-1",
        split_strategy="temporal",
        public_partition_refs=["PUB-1"],
        hidden_partition_handles=["HID-1"],
        ood_partition_handles=["OOD-1"],
        adversarial_partition_handles=["ADV-1"],
        content_hashes=[DIGEST_A],
        acl_policy_hash=DIGEST_B,
        log_redaction_policy="drop hidden handles from every log line",
        cache_isolation_policy="per-run cache, never shared with generators",
        holdout_id="HO-W06-1",
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
    record = sealed_bundle()
    record["metric_contract_hash"] = DIGEST_C
    return record


def comparisons(sealed_id: str = "EVAL-W06-1") -> list[dict[str, Any]]:
    return [
        {
            "comparison_id": "CMP-1",
            "evaluator_bundle_id": sealed_id,
            "candidate_ids": ["CAND-1"],
        }
    ]


def reassessment_for(run_id: str = RUN_ID) -> dict[str, Any]:
    """A drift reassessment bound to a quarantined future-run proposal."""
    return reassess_after_evaluator_drift(
        firewall=firewall(),
        current_bundle=drifted_bundle(),
        comparisons=comparisons(),
        source_run_id=run_id,
        defect_class=A_DEFECT_CLASS,
        evidence_artifact_ids=["EV-1"],
        proposed_change="re-derive the metric contract before the next seal",
        reassessed_at=REASSESSED_AT,
        reassessment_id="EWR-W06-2",
        proposal_id="EMP-W06-1",
    )


def proposal_for(run_id: str = RUN_ID) -> dict[str, Any]:
    return build_evaluator_mutation_proposal(
        source_run_id=run_id,
        current_evaluator_bundle_id="EVAL-W06-1",
        defect_class=A_DEFECT_CLASS,
        evidence_artifact_ids=["EV-1"],
        proposed_change="re-derive the metric contract before the next seal",
        proposal_id="EMP-W06-1",
    )


#: A proposal status that may influence a future run, read from the canonical
#: schema rather than named, so a vocabulary change surfaces here.
_PROPOSAL_STATUS_ENUM = default_registry().document("evaluator-mutation-proposal")[
    "properties"
]["status"]["enum"]
APPROVED_FOR_FUTURE = _PROPOSAL_STATUS_ENUM[2]


def approved_proposal_for(run_id: str = RUN_ID) -> dict[str, Any]:
    """A proposal qualified for future runs, so it may reach a different run.

    Built through the quarantine owner and then advanced to the approved status
    the schema declares, with its digest re-derived so the record stays
    self-consistent.  A freshly built proposal is inert for every run; only an
    approved one exercises the allowed forward-only path.
    """
    from epistemic_foundry.domain.hashing import hash_excluding

    proposal = proposal_for(run_id)
    proposal["status"] = APPROVED_FOR_FUTURE
    proposal["proposal_hash"] = hash_excluding(proposal, "proposal_hash")
    return proposal
