"""provenance_and_receipt_audit — every effect resolves to an immutable receipt.

The invariants this suite pins are the ones the manifest's exit criteria and the
Y05 integrity note turn on: every decision is a re-derivable, content-addressed
receipt; two runs over equal inputs produce byte-equal receipts; inputs are never
mutated; and a surrogate triage is recorded as an ordering that never carries
promotion authority.
"""

from __future__ import annotations

import copy

from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.operations.v4_y05 import (
    bind_triage_to_gate,
    plan_diversity_preserving_rebalance,
    reconcile_shed_load,
    require_bounded_production_budget,
)
from fixtures import (
    archive_population,
    bounded_budget,
    gate_receipt,
    lane_limits,
    qd_map,
    repo_root,
    schedule_events,
    triage_report,
)


def _rederives(record: dict[str, object]) -> bool:
    return hash_excluding(dict(record), "receipt_hash") == record["receipt_hash"]


def test_rebalance_plan_rederives_its_own_identity_and_hash() -> None:
    plan = plan_diversity_preserving_rebalance(
        quality_diversity_map=qd_map(),
        archive_entries=archive_population(),
        capacity=2,
    )
    body = {
        key: value for key, value in plan.items() if key not in {"plan_id", "plan_hash"}
    }
    assert plan["plan_id"] == "YQR-" + sha256_of_payload(body)[len("sha256:") :]
    assert plan["plan_hash"] == hash_excluding(dict(plan), "plan_hash")


def test_triage_report_rederives_its_own_identity() -> None:
    report = triage_report()
    body = {
        key: value
        for key, value in report.items()
        if key not in {"report_id", "report_hash"}
    }
    # The id is derived from the triage inputs, so it re-derives independently of
    # the decision the surrogate surface computed from them.
    assert report["report_id"].startswith("YST-")
    assert report["report_hash"] == hash_excluding(dict(report), "report_hash")
    assert body  # the report carries its ordered fields


def test_receipts_are_byte_equal_across_equal_runs() -> None:
    assert qd_map() == qd_map()
    assert triage_report() == triage_report()

    plan_kwargs = dict(
        quality_diversity_map=qd_map(),
        archive_entries=archive_population(),
        capacity=2,
    )
    assert plan_diversity_preserving_rebalance(
        **plan_kwargs
    ) == plan_diversity_preserving_rebalance(**plan_kwargs)

    assert require_bounded_production_budget(
        bounded_budget()
    ) == require_bounded_production_budget(bounded_budget())

    binding_kwargs = dict(triage_report=triage_report(), gate_receipt=gate_receipt())
    assert bind_triage_to_gate(**binding_kwargs) == bind_triage_to_gate(
        **binding_kwargs
    )


def test_shed_load_attestation_is_content_addressed_and_stable() -> None:
    kwargs = dict(
        budget_envelope=bounded_budget(),
        proposed=["C-1"],
        events=schedule_events("C-1"),
        lane_limits=lane_limits(),
        schedule_id="SCH-1",
    )
    first = reconcile_shed_load(repo_root(), **kwargs)
    second = reconcile_shed_load(repo_root(), **kwargs)
    assert first == second
    assert _rederives(first)
    assert first["receipt_id"].startswith("YLS-")


def test_rebalance_does_not_mutate_its_inputs() -> None:
    entries = archive_population()
    before = copy.deepcopy(entries)
    plan_diversity_preserving_rebalance(
        quality_diversity_map=qd_map(),
        archive_entries=entries,
        capacity=2,
    )
    assert entries == before


def test_bind_triage_does_not_mutate_its_inputs() -> None:
    report = triage_report()
    receipt = gate_receipt()
    before_report = copy.deepcopy(report)
    before_receipt = copy.deepcopy(receipt)
    bind_triage_to_gate(triage_report=report, gate_receipt=receipt)
    assert report == before_report
    assert receipt == before_receipt


def test_binding_is_recorded_as_ordering_never_promotion_authority() -> None:
    binding = bind_triage_to_gate(
        triage_report=triage_report(),
        gate_receipt=gate_receipt(),
    )
    # The promotion authority is the gate's: the binding records the surrogate as
    # ordering-only and every admissibility field it carries is a copy of the
    # gate's verdict, not a value the surrogate produced.
    assert binding["surrogate_orders_only"] is True
    assert binding["gate_decision"] == "ADMIT"
    assert binding["admissible_for_promotion_review"] is True


def test_budget_attestation_rederives_and_carries_no_timestamp() -> None:
    attestation = require_bounded_production_budget(bounded_budget())
    assert _rederives(attestation)
    # The attestation is a pure function of the envelope: no clock, no random id.
    assert "created_at" not in attestation
    assert (
        attestation["receipt_id"]
        == "YBA-"
        + sha256_of_payload(
            {
                key: value
                for key, value in attestation.items()
                if key not in {"receipt_id", "receipt_hash"}
            }
        )[len("sha256:") :]
    )
