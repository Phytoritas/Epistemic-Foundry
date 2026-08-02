"""End-to-end: the components must compose into one honest research cycle.

Unit tests prove each refusal in isolation. This file proves the refusals still
hold when the components are wired together, which is where a boundary usually
leaks: a cascade that reports PARTIAL must actually stop promotion, and a
session must not reach Export on gates the Parliament never saw.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from migrations.contracts import (
    LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED,
    LegacyDocumentRegistrationEvidenceRequired,
    migrate_legacy_document_manifest,
    rollback_legacy_document_manifest,
)

from epistemic_foundry.domain.status import ForgePhase, WorkClass
from epistemic_foundry.evidence_parliament import build_adjudication
from epistemic_foundry.evolution_chamber import build_evolution_run_spec
from epistemic_foundry.foundry_kernel import ForgeKernel, TransitionRejected
from epistemic_foundry.foundry_kernel.gates import GateSpec, evaluate_gate, gate_decision
from epistemic_foundry.governance import PromotionRequest, decide_promotion
from epistemic_foundry.governance.promotion import (
    CANONICAL_GATE_IDS,
    MissingEffectReceipt,
    PromotionCommitter,
    PromotionIdempotencyConflict,
    PromotionLevel,
    PromotionRevisionConflict,
    promotion_idempotency_key,
)
from epistemic_foundry.domain.hashing import hash_excluding, sha256_of_payload
from epistemic_foundry.noetic_ledger import NoeticLedger, build_effect_receipt
from epistemic_foundry.red_queen_lab import build_challenge_result, survived_challenges
from epistemic_foundry.validation_bay import (
    aggregate_cascade_status,
    build_cascade_plan,
    build_stage_result,
)
from epistemic_foundry.verifier_firewall import (
    VerifierFirewall,
    build_evaluator_bundle,
    build_holdout_manifest,
)

POLICY_HASH = "sha256:" + "c" * 64
CORPUS_HASH = "sha256:" + "d" * 64
PACK_HASH = "sha256:" + "a" * 64


def _load_json(relative_path: str) -> dict:
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / relative_path).read_text(encoding="utf-8"))


def _document_registration_migration() -> dict:
    return migrate_legacy_document_manifest(
        _load_json("migrations/contracts/fixtures/document-manifest-v3.json"),
        registration_request=_load_json(
            "examples/sample_document-registration-request.json"
        ),
        immutable_registration_evidence=_load_json(
            "migrations/contracts/fixtures/document-registration-evidence.json"
        ),
        migration_id="MR-DOCUMENT-REGISTRATION-FIXTURE-0001",
        recorded_at="2026-07-30T00:03:00Z",
    )


def test_document_registration_migration_requires_more_than_final_manifest() -> None:
    with pytest.raises(LegacyDocumentRegistrationEvidenceRequired) as excinfo:
        migrate_legacy_document_manifest(
            _load_json("migrations/contracts/fixtures/document-manifest-v3.json"),
            registration_request=None,
            immutable_registration_evidence=None,
            migration_id="MR-DOCUMENT-REGISTRATION-FIXTURE-0001",
            recorded_at="2026-07-30T00:03:00Z",
        )
    assert excinfo.value.code == LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED


def test_document_registration_migration_emits_canonical_lineage() -> None:
    root = Path(__file__).resolve().parents[1]
    result = _document_registration_migration()
    expected = {
        "document_registration_request": _load_json(
            "examples/sample_document-registration-request.json"
        ),
        "document_registration": _load_json(
            "examples/sample_document-registration.json"
        ),
        "document_manifest": _load_json("examples/sample_document-manifest.json"),
    }
    for name, expected_payload in expected.items():
        assert result[name] == expected_payload

    schema_paths = {
        "document_registration_request": "schemas/document-registration-request.schema.json",
        "document_registration": "schemas/document-registration.schema.json",
        "document_manifest": "schemas/document-manifest.schema.json",
        "migration_record": "migrations/contracts/migration-record.schema.json",
    }
    for name, relative_path in schema_paths.items():
        schema = _load_json(relative_path)
        Draft202012Validator.check_schema(schema)
        errors = list(
            Draft202012Validator(
                schema,
                format_checker=Draft202012Validator.FORMAT_CHECKER,
            ).iter_errors(result[name])
        )
        assert errors == []

    assert result["migration_record"] == _load_json(
        "migrations/contracts/fixtures/document-registration-migration-record.json"
    )
    legacy = _load_json("migrations/contracts/fixtures/document-manifest-v3.json")
    assert rollback_legacy_document_manifest(result, legacy) == legacy


def test_document_registration_migration_rejects_unbound_receipt_evidence() -> None:
    evidence = _load_json(
        "migrations/contracts/fixtures/document-registration-evidence.json"
    )
    evidence["immutable_evidence_ids"].remove(evidence["source_effect_receipt_id"])
    with pytest.raises(
        LegacyDocumentRegistrationEvidenceRequired, match="required artifacts/receipts"
    ):
        migrate_legacy_document_manifest(
            _load_json("migrations/contracts/fixtures/document-manifest-v3.json"),
            registration_request=_load_json(
                "examples/sample_document-registration-request.json"
            ),
            immutable_registration_evidence=evidence,
            migration_id="MR-DOCUMENT-REGISTRATION-FIXTURE-0001",
            recorded_at="2026-07-30T00:03:00Z",
        )


def test_document_registration_migration_rejects_noncanonical_request_fields() -> None:
    request = _load_json("examples/sample_document-registration-request.json")
    request["inferred_from_final_manifest"] = True
    with pytest.raises(
        LegacyDocumentRegistrationEvidenceRequired, match="field mismatch"
    ):
        migrate_legacy_document_manifest(
            _load_json("migrations/contracts/fixtures/document-manifest-v3.json"),
            registration_request=request,
            immutable_registration_evidence=_load_json(
                "migrations/contracts/fixtures/document-registration-evidence.json"
            ),
            migration_id="MR-DOCUMENT-REGISTRATION-FIXTURE-0001",
            recorded_at="2026-07-30T00:03:00Z",
        )


def test_document_registration_migration_rejects_rehashed_nested_schema_violations() -> None:
    schema = _load_json("schemas/document-registration-request.schema.json")
    preimage_fields = schema["x-canonical-hash"]["preimage_fields"]
    mutations = (
        lambda request: request["source_origin"].__setitem__(
            "original_uri", "file:///private/fixture.txt"
        ),
        lambda request: request["source_origin"].__setitem__("unexpected", True),
        lambda request: request["external_identifier_hints"][0].__setitem__(
            "verified", True
        ),
        lambda request: request.__setitem__("declared_filename", "../fixture.txt"),
        lambda request: request.__setitem__("declared_media_type", "not-a-media-type"),
        lambda request: request.__setitem__("confidentiality", "publicish"),
    )
    for mutate in mutations:
        request = _load_json("examples/sample_document-registration-request.json")
        mutate(request)
        request_hash = sha256_of_payload(
            {field: request[field] for field in preimage_fields}
        )
        request["request_hash"] = request_hash
        request["request_id"] = "DREQ-" + request_hash.removeprefix("sha256:")
        with pytest.raises(LegacyDocumentRegistrationEvidenceRequired):
            migrate_legacy_document_manifest(
                _load_json("migrations/contracts/fixtures/document-manifest-v3.json"),
                registration_request=request,
                immutable_registration_evidence=_load_json(
                    "migrations/contracts/fixtures/document-registration-evidence.json"
                ),
                migration_id="MR-DOCUMENT-REGISTRATION-FIXTURE-0001",
                recorded_at="2026-07-30T00:03:00Z",
            )


@pytest.mark.parametrize(
    ("field", "hostile_value", "message"),
    (
        ("source_effect_receipt_id", None, "source_effect_receipt_id"),
        ("submitted_by_principal_id", "", "submitted principal"),
        ("registration_ledger_event_id", None, "registration_ledger_event_id"),
        ("source_content_hash", "sha256:not-a-digest", "canonical sha256"),
        ("registered_at", "2026-07-30T00:02:00+09:00", "ending in Z"),
    ),
)
def test_document_registration_migration_rejects_malformed_immutable_evidence(
    field: str, hostile_value: object, message: str
) -> None:
    evidence = _load_json(
        "migrations/contracts/fixtures/document-registration-evidence.json"
    )
    original = evidence[field]
    evidence[field] = hostile_value
    if original in evidence["immutable_evidence_ids"]:
        evidence["immutable_evidence_ids"].remove(original)
        if hostile_value is not None:
            evidence["immutable_evidence_ids"].append(hostile_value)
    with pytest.raises(LegacyDocumentRegistrationEvidenceRequired, match=message):
        migrate_legacy_document_manifest(
            _load_json("migrations/contracts/fixtures/document-manifest-v3.json"),
            registration_request=_load_json(
                "examples/sample_document-registration-request.json"
            ),
            immutable_registration_evidence=evidence,
            migration_id="MR-DOCUMENT-REGISTRATION-FIXTURE-0001",
            recorded_at="2026-07-30T00:03:00Z",
        )


def test_document_registration_migration_rejects_source_identity_drift() -> None:
    evidence = _load_json(
        "migrations/contracts/fixtures/document-registration-evidence.json"
    )
    evidence["source_content_hash"] = "sha256:" + "0" * 64
    with pytest.raises(
        LegacyDocumentRegistrationEvidenceRequired, match="source content hash"
    ):
        migrate_legacy_document_manifest(
            _load_json("migrations/contracts/fixtures/document-manifest-v3.json"),
            registration_request=_load_json(
                "examples/sample_document-registration-request.json"
            ),
            immutable_registration_evidence=evidence,
            migration_id="MR-DOCUMENT-REGISTRATION-FIXTURE-0001",
            recorded_at="2026-07-30T00:03:00Z",
        )


def test_document_registration_migration_rejects_non_utc_recorded_at() -> None:
    with pytest.raises(
        LegacyDocumentRegistrationEvidenceRequired, match="recorded_at.*ending in Z"
    ):
        migrate_legacy_document_manifest(
            _load_json("migrations/contracts/fixtures/document-manifest-v3.json"),
            registration_request=_load_json(
                "examples/sample_document-registration-request.json"
            ),
            immutable_registration_evidence=_load_json(
                "migrations/contracts/fixtures/document-registration-evidence.json"
            ),
            migration_id="MR-DOCUMENT-REGISTRATION-FIXTURE-0001",
            recorded_at="2026-07-30T09:03:00+09:00",
        )


def test_document_registration_migration_rollback_is_hash_bound() -> None:
    result = _document_registration_migration()
    legacy = _load_json("migrations/contracts/fixtures/document-manifest-v3.json")
    tampered = copy.deepcopy(legacy)
    tampered["document_id"] = "DOC-TAMPERED"
    with pytest.raises(
        LegacyDocumentRegistrationEvidenceRequired, match="source hash"
    ):
        rollback_legacy_document_manifest(result, tampered)

STAGES = (
    {
        "stage_id": "S0",
        "stage_class": "contract",
        "entry_rule": "always",
        "pass_rule": "contracts valid",
        "failure_action": "reject",
        "budget_fraction": 0.1,
    },
    {
        "stage_id": "S5",
        "stage_class": "holdout",
        "entry_rule": "after S0",
        "pass_rule": "preregistered threshold met",
        "failure_action": "restrict",
        "budget_fraction": 0.5,
    },
)


def _promotion_gate_decisions(*, not_required: tuple[str, ...] = ()) -> tuple[dict, ...]:
    decisions = []
    for index, gate_id in enumerate(CANONICAL_GATE_IDS):
        is_not_required = gate_id in not_required
        timestamp = "2026-07-28T00:00:00+00:00"
        decision = {
            "gate_id": f"GD-FIXTURE-{index:02d}",
            "gate_version": "4.0.0",
            "run_id": "RUN-1",
            "name": gate_id,
            "status": "PASS",
            "reasons": [
                "POLICY_NOT_REQUIRED: sealed PolicyBundle rule PB-RULE-LOW-RISK-1"
                if is_not_required
                else "substantive gate evidence verified"
            ],
            "evidence_ids": [
                "ART-POLICY-NOT-REQUIRED-1"
                if is_not_required
                else f"ART-{gate_id}-1"
            ],
            "input_artifact_ids": [f"ART-{gate_id}-INPUT-1"],
            "policy_bundle_hash": POLICY_HASH,
            "decision": "PASS",
            "blocker_ids": [],
            "waiver_authority": None,
            "waiver_reason": None,
            "evaluated_at": timestamp,
            "created_at": timestamp,
            "policy_version": "4.0.0-fixture.1",
            "non_waivable": True,
            "evaluator_type": "deterministic",
            "input_hash": "sha256:" + "b" * 64,
        }
        decision["decision_hash"] = hash_excluding(decision, "decision_hash")
        decisions.append(decision)
    return tuple(decisions)


@pytest.fixture()
def kernel(tmp_path) -> ForgeKernel:
    return ForgeKernel(NoeticLedger(tmp_path / "ledger.jsonl"))


@pytest.fixture()
def firewall() -> VerifierFirewall:
    holdout = build_holdout_manifest(
        evaluator_id="EVAL-INTEGRATION-1",
        split_strategy="temporal",
        public_partition_refs=["ART-HOLDOUT-PUBLIC-INTEGRATION-1"],
        hidden_partition_handles=["opaque://holdout/hidden/integration-1"],
        ood_partition_handles=["opaque://holdout/ood/integration-1"],
        adversarial_partition_handles=["opaque://holdout/adversarial/integration-1"],
        content_hashes=["sha256:" + "1" * 64],
        acl_policy_hash="sha256:" + "2" * 64,
        log_redaction_policy="redact every sealed partition handle",
        cache_isolation_policy="evaluator-only content-addressed cache",
        holdout_id="HO-INTEGRATION-1",
        sealed_at="2026-07-28T00:00:00+00:00",
    )
    bundle = build_evaluator_bundle(
        evaluator_version="1.0.0",
        code_artifact_id="ART-EVALUATOR-CODE-INTEGRATION-1",
        code_hash="sha256:" + "3" * 64,
        metric_contract_hash="sha256:" + "4" * 64,
        environment_digest="sha256:" + "5" * 64,
        dependency_lock_hash="sha256:" + "6" * 64,
        data_contract_hash="sha256:" + "7" * 64,
        policy_bundle_hash=POLICY_HASH,
        qualification_report_id="EQR-INTEGRATION-1",
        holdout_manifest_id=holdout["holdout_id"],
        evaluator_id=holdout["evaluator_id"],
        sealed_at="2026-07-28T00:00:00+00:00",
    )
    return VerifierFirewall(
        bundle,
        holdout,
        holdout_read_principal_ids=["PRIN-validator"],
    )


def _advance(kernel: ForgeKernel, state: dict, to_phase: ForgePhase, **kwargs) -> dict:
    request = kernel.build_request(
        state,
        to_phase=to_phase,
        actor_id="AG-1",
        actor_role="bounded_maker",
        reason=f"advance to {to_phase}",
        gate_result_ids=kwargs.get("gate_result_ids", ()),
    )
    return kernel.apply_transition(state, request, gate_decisions=kwargs.get("gate_decisions", ()))


def _reach_gate(kernel: ForgeKernel) -> dict:
    state = kernel.open_session(
        workspace_id="WS-1",
        run_spec_id="RUN-1",
        work_class=WorkClass.E3,
        policy_hash=POLICY_HASH,
        corpus_snapshot_hash=CORPUS_HASH,
    )
    for phase in (ForgePhase.FRAME, ForgePhase.OBSERVE, ForgePhase.REASON, ForgePhase.GATE):
        state = _advance(kernel, state, phase)
    return state


def _cascade(statuses: dict[str, str]) -> tuple[dict, str]:
    plan = build_cascade_plan(
        candidate_class="hypothesis",
        stages=STAGES,
        max_total_budget=100.0,
        early_stop_policy="stop on hard failure",
    )
    results = [
        build_stage_result(
            cascade_plan_id=plan["cascade_plan_id"],
            candidate_id="CAND-1",
            stage_id=stage_id,
            status=status,
            metric_values={"m": 1.0},
            uncertainty_summary="95% CI [0.9, 1.1]",
            started_at="2026-07-27T00:00:00+00:00",
        )
        for stage_id, status in statuses.items()
    ]
    return plan, aggregate_cascade_status(plan, results)


def _promotion_request(**overrides) -> PromotionRequest:
    values = {
        "candidate_id": "CAND-1",
        "candidate_revision": 1,
        "current_level": PromotionLevel.INBOX,
        "requested_level": PromotionLevel.CANDIDATE,
        "policy_promotion_ceiling": PromotionLevel.REPLICATED,
        "hard_gate_status": "PASS",
        "fitness_vector_id": "FV-1",
        "phase_e_artifact_set_id": "PAS-E-1",
        "promotion_pack_artifact_ids": ("ART-PROMOTION-PACK-1",),
        "promotion_pack_hash": PACK_HASH,
        "gate_decision_ids": CANONICAL_GATE_IDS,
        "artifact_receipt_ids": ("AR-PROMOTION-PACK-1",),
        "effect_receipt_id": "EF-PROMOTION-COMMIT-1",
        "request_action_intent_id": "AI-REQUEST-PROMOTION-1",
        "commit_action_intent_id": "AI-COMMIT-PROMOTION-1",
        "policy_bundle_hash": POLICY_HASH,
        "parliament_adjudication_id": "ADJ-1",
        "attestation_id": None,
        "replication_status": "REPLICATED",
        "selective_inference_report_id": "SIR-1",
        "replication_result_ids": ("REP-1",),
        "approval_record_ids": ("APR-1",),
        "grounded_evidence_ids": ("EV-1",),
        "dependency_cluster_ids": ("EDC-1",),
        "challenge_survived": True,
    }
    values.update(overrides)
    if "gate_decisions" not in overrides:
        not_required = (
            ("G12_INDEPENDENT_ATTESTATION",)
            if values["requested_level"]
            in {
                PromotionLevel.INBOX,
                PromotionLevel.CANDIDATE,
                PromotionLevel.LITERATURE_GROUNDED,
            }
            and values["attestation_id"] is None
            else ()
        )
        values["gate_decisions"] = _promotion_gate_decisions(
            not_required=not_required
        )
    if "idempotency_key" not in overrides:
        values["idempotency_key"] = promotion_idempotency_key(
            candidate_id=values["candidate_id"],
            candidate_revision=values["candidate_revision"],
            requested_level=values["requested_level"],
            promotion_pack_hash=values["promotion_pack_hash"],
            policy_bundle_hash=values["policy_bundle_hash"],
        )
    return PromotionRequest(**values)


def _sealed_evolution_run_spec() -> dict:
    sample_path = (
        Path(__file__).resolve().parents[1] / "examples" / "sample_evolution-run-spec.json"
    )
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    payload = {
        key: copy.deepcopy(value)
        for key, value in sample.items()
        if key not in {"evolution_run_id", "spec_hash"}
    }
    payload["evolution_run_id"] = "ER-INTEGRATION-1"
    return build_evolution_run_spec(**payload)


def test_full_cycle_promotes_only_with_complete_evidence(kernel: ForgeKernel, firewall: VerifierFirewall) -> None:
    """The honest happy path, end to end."""
    firewall.verify_self()
    evolution_spec = _sealed_evolution_run_spec()
    assert evolution_spec["spec_hash"] == hash_excluding(evolution_spec, "spec_hash")
    assert evolution_spec["resolved_refs"]["evaluator_bundle"]
    assert evolution_spec["resolved_refs"]["holdout_manifest"]
    gated = _reach_gate(kernel)

    _, cascade_status = _cascade({"S0": "PASS", "S5": "PASS"})
    assert cascade_status == "PASS"

    passing_gate = gate_decision(
        evaluate_gate(GateSpec("evidence_grounding", ("evidence_ids",)), {"evidence_ids": ["EV-1"]}),
        run_id="RUN-1",
        policy_version="4.0.0",
        inputs={"evidence_ids": ["EV-1"]},
        gate_version="4.0.0",
        input_artifact_ids=("ART-EVIDENCE-GROUNDING-INPUT-1",),
        policy_bundle_hash=POLICY_HASH,
        blocker_ids=(),
    )
    adjudication = build_adjudication(
        run_id="RUN-1",
        hypothesis_id="HYP-1",
        gate_decisions=[passing_gate],
        brief_ids=["CB-1"],
        cross_examination_ids=["CX-1"],
        verdict="SUPPORTED",
        promotion_recommendation="CANDIDATE",
        rationale="support survives cross-examination",
        strongest_support_id="EV-1",
        strongest_counterevidence_id="EV-2",
    )

    exported = _advance(
        kernel,
        gated,
        ForgePhase.EXPORT,
        gate_result_ids=[passing_gate["gate_id"]],
        gate_decisions=[passing_gate],
    )
    assert exported["phase"] == "E"

    decision = decide_promotion(
        _promotion_request(
            hard_gate_status=cascade_status,
            parliament_adjudication_id=adjudication["adjudication_id"],
        )
    )
    assert decision["decision"] == "PROMOTE"
    assert decision["granted_level"] == "CANDIDATE"
    kernel.ledger.verify()


def test_promotion_accepts_canonical_generated_gate_decisions() -> None:
    gate_decisions = tuple(
        gate_decision(
            evaluate_gate(
                GateSpec(
                    gate_name,
                    ("binding",),
                    evidence_ids=(f"ART-{gate_name}-1",),
                ),
                {"binding": f"sealed-{gate_name}"},
            ),
            run_id="RUN-PROMOTION-GATES-1",
            policy_version="4.0.0",
            inputs={"binding": f"sealed-{gate_name}"},
            gate_version="4.0.0",
            input_artifact_ids=(f"ART-{gate_name}-INPUT-1",),
            policy_bundle_hash=POLICY_HASH,
            blocker_ids=(),
            evaluated_at="2026-07-28T00:00:00+00:00",
        )
        for gate_name in CANONICAL_GATE_IDS
    )

    decision = decide_promotion(
        _promotion_request(
            gate_decisions=gate_decisions,
            attestation_id="ATT-1",
        )
    )

    assert decision["decision"] == "PROMOTE"
    assert tuple(gate["name"] for gate in gate_decisions) == CANONICAL_GATE_IDS
    assert len({gate["gate_id"] for gate in gate_decisions}) == len(CANONICAL_GATE_IDS)
    assert all(gate["gate_id"].startswith("GD-") for gate in gate_decisions)


def test_partial_cascade_blocks_promotion_end_to_end(kernel: ForgeKernel) -> None:
    """An unfinished cascade must not yield promotion, however good the rest is."""
    _, cascade_status = _cascade({"S0": "PASS"})
    assert cascade_status == "PARTIAL"

    decision = decide_promotion(
        _promotion_request(
            current_level=PromotionLevel.CANDIDATE,
            requested_level=PromotionLevel.REPLICATED,
            policy_promotion_ceiling=PromotionLevel.EMPIRICALLY_TESTED,
            conditional_grant_level=PromotionLevel.EMPIRICALLY_TESTED,
            hard_gate_status=cascade_status,
            attestation_id="ATT-1",
            replication_status="PARTIAL",
            unresolved_limitations=("one preregistered replication branch is unresolved",),
        )
    )
    assert decision["decision"] == "CONDITIONAL"
    assert decision["granted_level"] == "EMPIRICALLY_TESTED"


def test_failed_cascade_blocks_promotion_end_to_end() -> None:
    _, cascade_status = _cascade({"S0": "FAIL"})
    assert cascade_status == "FAIL"
    decision = decide_promotion(
        _promotion_request(
            hard_gate_status=cascade_status,
        )
    )
    assert decision["decision"] == "BLOCKED"
    assert decision["granted_level"] is None


def test_leakage_invalidates_the_cycle(firewall: VerifierFirewall) -> None:
    """Holdout leakage blocks promotion even with a fully passing cascade."""
    touched = firewall.leakage_invalidates(["opaque://holdout/hidden/integration-1"])
    assert touched == ["opaque://holdout/hidden/integration-1"]
    _, cascade_status = _cascade({"S0": "PASS", "S5": "PASS"})
    decision = decide_promotion(
        _promotion_request(
            hard_gate_status=cascade_status,
            leakage_detected=bool(touched),
        )
    )
    assert decision["decision"] == "BLOCKED"
    assert decision["granted_level"] is None


def test_export_is_refused_without_the_gate_the_parliament_saw(kernel: ForgeKernel) -> None:
    """A session cannot leave Gate on evidence nobody adjudicated."""
    gated = _reach_gate(kernel)
    with pytest.raises(TransitionRejected):
        _advance(kernel, gated, ForgePhase.EXPORT)


def _challenge(outcome: str, *, artifacts=("REPRO-1",)) -> dict:
    return build_challenge_result(
        challenge_genome_id="CG-1",
        target_candidate_id="CAND-1",
        stage_result_id="SER-1",
        outcome=outcome,
        severity="major",
        observed_effect=f"observed {outcome.lower()}",
        reproduction_artifact_ids=artifacts,
    )


def _promote_with(challenge_results: list[dict]) -> dict:
    _, cascade_status = _cascade({"S0": "PASS", "S5": "PASS"})
    return decide_promotion(
        _promotion_request(
            hard_gate_status=cascade_status,
            challenge_survived=survived_challenges("CAND-1", challenge_results),
        )
    )


def test_unchallenged_candidate_cannot_promote_end_to_end() -> None:
    """Red Queen survival feeds promotion: no challenge means no credit."""
    decision = _promote_with([])
    assert decision["decision"] == "UNDERDETERMINED"
    assert "Red Queen challenge" in decision["rationale"]


def test_refuted_candidate_cannot_promote_end_to_end() -> None:
    decision = _promote_with([_challenge("SURVIVED"), _challenge("REFUTED")])
    assert decision["decision"] == "UNDERDETERMINED"


def test_inconclusive_challenge_cannot_promote_end_to_end() -> None:
    """A crashed adversary must not be laundered into survival."""
    decision = _promote_with([_challenge("INCONCLUSIVE")])
    assert decision["decision"] == "UNDERDETERMINED"


def test_surviving_every_challenge_promotes_end_to_end() -> None:
    decision = _promote_with([_challenge("SURVIVED"), _challenge("SURVIVED")])
    assert decision["decision"] == "PROMOTE"


def test_every_transition_is_recorded_in_the_ledger(kernel: ForgeKernel) -> None:
    gated = _reach_gate(kernel)
    events = list(kernel.ledger.events())
    # one open_session event plus four phase transitions
    assert len(events) == 5
    assert events[0]["event_type"] == "forge.session.opened"
    assert events[-1]["event_type"] == "forge.phase.r_to_g"
    assert gated["revision"] == 4
    kernel.ledger.verify()


def _candidate() -> dict:
    return {
        "candidate_id": "CAND-1",
        "revision": 1,
        "promotion_level": "INBOX",
        "promotion_history": [],
    }


def _decision_and_effect(*, status: str = "SUCCEEDED", **overrides) -> tuple[dict, dict]:
    request = _promotion_request(**overrides)
    effect = build_effect_receipt(
        intent_id=request.commit_action_intent_id,
        run_id="RUN-1",
        status=status,
        idempotency_key=request.idempotency_key,
        started_at="2026-07-28T00:00:00+00:00",
        finished_at="2026-07-28T00:00:01+00:00",
    )
    request = dataclasses.replace(request, effect_receipt_id=effect["receipt_id"])
    return decide_promotion(request), effect


def test_receipt_bound_promotion_commit_is_atomic() -> None:
    decision, effect = _decision_and_effect()
    result = PromotionCommitter().commit(
        _candidate(), decision, expected_revision=1, effect_receipt=effect
    )
    assert result["state_changed"] is True
    assert result["candidate"]["revision"] == 2
    assert result["candidate"]["promotion_level"] == "CANDIDATE"
    assert result["candidate"]["promotion_history"][-1]["effect_receipt_id"] == effect[
        "receipt_id"
    ]


def test_crash_before_effect_receipt_does_not_promote() -> None:
    candidate = _candidate()
    decision = decide_promotion(_promotion_request())
    with pytest.raises(MissingEffectReceipt):
        PromotionCommitter().commit(
            candidate, decision, expected_revision=1, effect_receipt=None
        )
    assert candidate == _candidate()


def test_stale_candidate_revision_fails_compare_and_swap() -> None:
    decision, effect = _decision_and_effect()
    with pytest.raises(PromotionRevisionConflict):
        PromotionCommitter().commit(
            _candidate(), decision, expected_revision=2, effect_receipt=effect
        )


def test_same_idempotent_request_replays_the_original_result() -> None:
    decision, effect = _decision_and_effect()
    committer = PromotionCommitter()
    first = committer.commit(_candidate(), decision, expected_revision=1, effect_receipt=effect)
    replay = committer.commit(
        first["candidate"], decision, expected_revision=2, effect_receipt=effect
    )
    assert first["candidate"] == replay["candidate"]
    assert replay["replayed"] is True


def test_idempotency_key_reuse_with_different_request_conflicts() -> None:
    decision, effect = _decision_and_effect()
    committer = PromotionCommitter()
    committed = committer.commit(
        _candidate(), decision, expected_revision=1, effect_receipt=effect
    )
    conflicting = dict(decision)
    conflicting["rationale"] = decision["rationale"] + "; conflicting replay"
    conflicting["decision_hash"] = hash_excluding(conflicting, "decision_hash")
    with pytest.raises(PromotionIdempotencyConflict):
        committer.commit(
            committed["candidate"],
            conflicting,
            expected_revision=2,
            effect_receipt=effect,
        )


def test_blocked_decision_with_receipt_preserves_candidate_state() -> None:
    decision, effect = _decision_and_effect(
        status="NOT_EXECUTED", leakage_detected=True
    )
    candidate = _candidate()
    result = PromotionCommitter().commit(
        candidate, decision, expected_revision=1, effect_receipt=effect
    )
    assert decision["decision"] == "BLOCKED"
    assert decision["granted_level"] is None
    assert result["state_changed"] is False
    assert result["candidate"] == candidate
