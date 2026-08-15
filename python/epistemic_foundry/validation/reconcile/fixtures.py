"""Fixtures for the V04 result-reconciliation suites.

The three surfaces a reconciliation binds are built through the sealed sibling
components rather than written out by hand, so each fixture is a document those
contracts actually produce: the execution record comes from V03's own sealing,
the preregistration from V02's, and the target scope from V01's empty vector.
Only the ExperimentResult is assembled here, because no component in this
dependency layer emits one — it is the typed result a run hands V04 — and it is
validated against its canonical schema at the point of use.

The default narrative is one clean simulation run of the V01 reservoir target:
it executed cleanly, completed, and its preregistered falsification rule was not
triggered, so its ``modeling`` evidence is promotable at a ``modeling``
candidate class under the ``support`` role.  The variant builders move exactly
one thing at a time — the source or candidate class, the falsification outcome,
the result status, or the execution gate — so each suite can name the single
surface it is exercising.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from epistemic_foundry.validation import execution
from epistemic_foundry.validation.execution import fixtures as v03
from epistemic_foundry.validation.planning import fixtures as v02
from epistemic_foundry.validation.targets import empty_scope_vector, hash_excluding

from .contracts import reconcile_evidence

ROOT = Path(__file__).resolve().parents[4]

RUN_ID = v03.RUN_ID
RECONCILIATION_ID = "VREC-V04-1"
SOURCE_RESULT_ID = "VXRES-V04-1"
CANDIDATE_EVIDENCE_ID = "EV-V04-1"
EXECUTION_RECORD_ID = "VXR-V04-1"
DENIED_RECORD_ID = "VXR-V04-DENIED"
CREATED_AT = "2026-08-01T01:00:00Z"
SEALED_AT = "2026-08-01T00:45:00Z"
ENVIRONMENT_DIGEST = "sha256:" + "e" * 64


def execution_record(**overrides: Any) -> dict[str, Any]:
    """A sealed V03 execution record for a clean run at gate PASS."""

    authorization = execution.authorize_execution(ROOT, **v03.authorization_arguments())
    receipt = execution.build_effect_receipt(ROOT, **v03.receipt_arguments())
    arguments: dict[str, Any] = {
        "record_id": EXECUTION_RECORD_ID,
        "sealed_at": SEALED_AT,
        "authorization": authorization,
        "environment": v03.run_environment(),
        "capture": v03.run_capture(),
        "receipt": receipt,
        "reconciliation": v03.reconciliation(),
    }
    arguments.update(overrides)
    return execution.seal_execution_record(ROOT, **arguments)


def denied_execution_record(**overrides: Any) -> dict[str, Any]:
    """A sealed V03 execution record whose gate is DENIED, so nothing ran.

    The intent is edited after it was sealed, so authorization refuses it and
    the record carries no execution evidence; its run id still binds the run
    the reconciliation names.
    """

    tampered = v03.tampered_intent(target_ref="validation_target:other@1.0.0")
    authorization = execution.authorize_execution(
        ROOT, **{**v03.authorization_arguments(), "intent": tampered}
    )
    arguments: dict[str, Any] = {
        "record_id": DENIED_RECORD_ID,
        "sealed_at": SEALED_AT,
        "authorization": authorization,
    }
    arguments.update(overrides)
    return execution.seal_execution_record(ROOT, **arguments)


def experiment_result(**overrides: Any) -> dict[str, Any]:
    """One schema-valid ExperimentResult for the bound run."""

    value: dict[str, Any] = {
        "result_id": SOURCE_RESULT_ID,
        "ticket_id": "VXT-V04-1",
        "run_id": RUN_ID,
        "result_type": "simulation",
        "status": "COMPLETED",
        "input_artifact_ids": ["ART-V04-in-1"],
        "output_artifact_ids": ["ART-V04-out-1"],
        "metric_results": {"storage_estimate": 15.2},
        "falsification_outcome": "NOT_FALSIFIED",
        "evidence_class": "modeling",
        "limitations": ["single stochastic replicate"],
        "environment_digest": ENVIRONMENT_DIGEST,
        "started_at": "2026-08-01T00:05:00Z",
        "finished_at": "2026-08-01T00:35:00Z",
    }
    value.update(overrides)
    value["result_hash"] = hash_excluding(value, "result_hash")
    return value


def preregistration(**overrides: Any) -> dict[str, Any]:
    """The intact V02 preregistration the result is judged against."""

    return v02.preregistration(**overrides)


def scope_mapping(**overrides: Any) -> dict[str, Any]:
    """The V01 target scope carried onto the reconciliation record."""

    scope = empty_scope_vector(ROOT)
    scope["domain"] = "water-resources"
    scope["unit_of_analysis"] = "reservoir-season"
    scope.update(overrides)
    return scope


def quality_adjustments(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "directness": 0.4,
        "replication": None,
        "note": "single simulation replicate, no independent reproduction",
    }
    value.update(overrides)
    return value


def reconcile_arguments(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "reconciliation_id": RECONCILIATION_ID,
        "run_id": RUN_ID,
        "source_result_id": SOURCE_RESULT_ID,
        "candidate_evidence_id": CANDIDATE_EVIDENCE_ID,
        "execution_record": execution_record(),
        "experiment_result": experiment_result(),
        "target_evidence_role": "support",
        "candidate_evidence_class": "modeling",
        "scope_mapping": scope_mapping(),
        "quality_adjustments": quality_adjustments(),
        "created_at": CREATED_AT,
        "preregistration": preregistration(),
    }
    value.update(overrides)
    return value


def reconciliation(**overrides: Any) -> dict[str, Any]:
    return reconcile_evidence(ROOT, **reconcile_arguments(**overrides))
