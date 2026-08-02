"""Fixtures for the V02 preregistered ValidationPlan suites.

The target these plans bind is V01's own fixture manifest, imported from the
sealed component rather than copied, so a V02 suite can never pass against a
target V01 would not actually accept.  The one change is a second declared
output, because a register with a single endpoint cannot show that the
endpoints a plan publishes are derived from the predictions rather than
supplied alongside them.

Every document here is built through this component's own builders, so each
fixture is a document the contract accepts and the canonical schemas validate.
The hand-written pieces are the *declarations* — stages, predictions and plan
arguments — which is exactly what a caller writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from epistemic_foundry.validation.targets import build_eligibility_report
from epistemic_foundry.validation.targets.fixtures import port
from epistemic_foundry.validation.targets.fixtures import (
    target_manifest as v01_target_manifest,
)

from .contracts import build_stage_plan, preregister_plan

ROOT = Path(__file__).resolve().parents[4]

TARGET_ID = "vt-reservoir-sim"
TARGET_VERSION = "1.4.0"
GENOME_ID = "HGEN-V02-1"
HYPOTHESIS_ID = "HYP-V02-1"
PLAN_ID = "VPLAN-V02-0001"
AMENDED_PLAN_ID = "VPLAN-V02-0002"
RECEIPT_ID = "VPREREG-V02-1"
AMENDED_RECEIPT_ID = "VPREREG-V02-2"
PREREGISTERED_AT = "2026-08-01T00:00:00Z"
REPORT_ID = "VTER-V02-1"
SCREENED_AT = "2026-08-01T00:00:00Z"
CASCADE_PLAN_ID = "VCAS-V02-1"
ENVIRONMENT_DIGEST = "sha256:" + "c" * 64
IDENTIFIABILITY_NOTE = "inflow and abstraction are not separable"


def outputs() -> list[dict[str, Any]]:
    """Two declared output ports, so endpoints can be seen to be derived."""

    return [
        port("storage_estimate", "number", unit="m3"),
        port("spill_volume", "number", unit="m3"),
    ]


def target_manifest(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {"outputs": outputs()}
    arguments.update(overrides)
    return v01_target_manifest(**arguments)


def eligibility_report(*manifests: Any, **overrides: str) -> dict[str, Any]:
    arguments: dict[str, str] = {"report_id": REPORT_ID, "screened_at": SCREENED_AT}
    arguments.update(overrides)
    documents = list(manifests) if manifests else [target_manifest()]
    return build_eligibility_report(ROOT, documents, **arguments)


def stages() -> list[dict[str, Any]]:
    """A cheap contract screen first, then simulation, then replication."""

    return [
        {
            "stage_id": "contract-screen",
            "stage_class": "contract",
            "entry_rule": "the bound target is screened eligible",
            "pass_rule": "every declared port resolves against the manifest",
            "failure_action": "reject",
            "budget_fraction": 0.1,
        },
        {
            "stage_id": "scenario-simulation",
            "stage_class": "simulation",
            "entry_rule": "the contract screen passed",
            "pass_rule": "no falsification criterion fires across the matrix",
            "failure_action": "restrict",
            "budget_fraction": 0.5,
        },
        {
            "stage_id": "independent-replication",
            "stage_class": "replication",
            "entry_rule": "the simulation stage passed without restriction",
            "pass_rule": "an independent run reproduces the preregistered contrast",
            "failure_action": "escalate",
            "budget_fraction": 0.3,
        },
    ]


def stage_plan(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "cascade_plan_id": CASCADE_PLAN_ID,
        "candidate_class": "reservoir-drawdown-hypothesis",
        "stages": stages(),
        "max_total_budget": 100.0,
        "early_stop_policy": "stop at the first stage whose failure action rejects",
    }
    arguments.update(overrides)
    return build_stage_plan(ROOT, **arguments)


def falsification(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "falsifier_gene_id": "FALS-V02-1",
        "statement": "storage does not rise to the preregistered drawdown floor",
        "trigger_type": "predictive_failure",
        "severity": "critical",
        "comparator": "<",
        "threshold": 12.5,
        "unit": "m3",
        "decision_rule": "reject the linked prediction and cap promotion at review",
    }
    value.update(overrides)
    return value


def prediction(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "prediction_gene_id": "PRED-V02-1",
        "statement": "managed drawdown raises end-of-season storage",
        "observable_id": "storage_estimate",
        "expected_direction": "increase",
        "expected_range": "12.5 to 18.0 m3",
        "time_horizon": "one season",
        "scope_vector_id": "SCOPE-V02-1",
        "discrimination_targets": ["passive-release alternative"],
        "exploratory": False,
        "falsification": falsification(),
    }
    value.update(overrides)
    return value


def exploratory_prediction(**overrides: Any) -> dict[str, Any]:
    value = prediction(
        prediction_gene_id="PRED-V02-3",
        statement="spill timing shifts in a way the current model cannot rank",
        observable_id="spill_volume",
        expected_direction="qualitative",
        expected_range="not quantified before the run",
        exploratory=True,
        falsification=None,
    )
    value.update(overrides)
    return value


def predictions() -> list[dict[str, Any]]:
    """Two falsifiable predictions and one labelled exploratory."""

    return [
        prediction(),
        prediction(
            prediction_gene_id="PRED-V02-2",
            statement="managed drawdown lowers uncontrolled spill volume",
            observable_id="spill_volume",
            expected_direction="decrease",
            expected_range="0.0 to 4.0 m3",
            falsification=falsification(
                falsifier_gene_id="FALS-V02-2",
                statement="spill volume stays above the preregistered ceiling",
                comparator=">=",
                threshold=4.0,
            ),
        ),
        exploratory_prediction(),
    ]


def plan_arguments(**overrides: Any) -> dict[str, Any]:
    manifest = overrides.pop("target_manifest", None) or target_manifest()
    arguments: dict[str, Any] = {
        "target_manifest": manifest,
        "eligibility_report": eligibility_report(manifest),
        "cascade_plan": stage_plan(),
        "predictions": predictions(),
        "genome_id": GENOME_ID,
        "receipt_id": RECEIPT_ID,
        "preregistered_at": PREREGISTERED_AT,
        "plan_id": PLAN_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "target_id": TARGET_ID,
        "target_version": TARGET_VERSION,
        "objective": "decide whether managed drawdown raises end-of-season storage",
        "variable_mapping": {
            "drawdown_state": "{reservoir_level}",
            "forcing": "{rainfall_series}",
        },
        "mechanism_mapping": {
            "storage_release": "release lowers {reservoir_level} before the peak"
        },
        "baseline": {"model": "storage ~ rainfall + seasonal mean release"},
        "actions": [
            {"action": "simulate", "arguments": {}},
            {"action": "perturb", "arguments": {"parameter": "{seed}"}},
        ],
        "scenario_matrix": [
            {"drought_severity": "mild"},
            {"drought_severity": "severe"},
        ],
        "inputs": {"dataset_artifact_id": "ART-V02-1"},
        "controlled_conditions": {
            "abstraction": "{reservoir_level} is held at the seasonal mean"
        },
        "metrics": ["adjusted_mean_difference", "holdout_error"],
        "assumptions": ["the gauge record is comparable across the two scenarios"],
        "identifiability_warnings": [IDENTIFIABILITY_NOTE],
        "random_seed": 104729,
        "environment_digest": ENVIRONMENT_DIGEST,
        "resource_limits": {
            "timeout_seconds": 1800,
            "cpu_count": 2,
            "memory_mb": 4096,
        },
        "provenance_manifest_id": "PM-VPLAN-V02-1",
        "analysis_plan_artifact_id": "ART-ANALYSIS-V02-1",
        "stopping_rules": [
            "stop when every scenario completes or a safety gate blocks execution"
        ],
        "data_leakage_guards": ["holdout labels are unavailable to the planner"],
        "approval_record_ids": [],
    }
    arguments.update(overrides)
    return arguments


def preregistration(**overrides: Any) -> dict[str, Any]:
    return preregister_plan(ROOT, **plan_arguments(**overrides))


def amendment(predecessor: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """A successor plan that names the seal it descends from."""

    arguments: dict[str, Any] = {
        "amends": predecessor,
        "plan_id": AMENDED_PLAN_ID,
        "receipt_id": AMENDED_RECEIPT_ID,
    }
    arguments.update(overrides)
    return preregistration(**arguments)
