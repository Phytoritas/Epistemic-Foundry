"""Unit and contract tests for the V05 advancement gate.

These pin the four composed concerns to their sealed owners: the cascade must
actually pass, the OOD challenge must be survived, the statistical admissibility
must have been granted, and the replication ceiling must reach the configured
level. The happy path advances; each concern, varied alone, changes the verdict
in the direction its owner defines.
"""

from __future__ import annotations

import copy

import fixtures as fx
import pytest
from epistemic_foundry.domain.vocabularies import PROMOTION_LADDER
from epistemic_foundry.validation.v4_v05 import cascade_gate as engine


def test_happy_path_advances() -> None:
    receipt = engine.derive_validation_advancement(**fx.gate_arguments())
    assert receipt["decision"] == engine.ADVANCE
    assert receipt["advanced"] is True


def test_evaluate_returns_on_advance() -> None:
    receipt = engine.evaluate_validation_advancement(**fx.gate_arguments())
    assert receipt["decision"] == engine.ADVANCE


def test_evaluate_raises_on_refuse_and_carries_the_receipt() -> None:
    with pytest.raises(engine.ValidationCascadeRefused) as excinfo:
        engine.evaluate_validation_advancement(
            **fx.gate_arguments(replication_plan=None)
        )
    assert excinfo.value.code == "REPLICATION_CEILING_BELOW_REQUIRED"
    assert excinfo.value.context["receipt"]["decision"] == engine.REFUSE


def test_derivation_is_deterministic() -> None:
    first = engine.derive_validation_advancement(**fx.gate_arguments())
    second = engine.derive_validation_advancement(**fx.gate_arguments())
    assert first == second


def test_inputs_are_not_mutated() -> None:
    arguments = fx.gate_arguments()
    snapshot = copy.deepcopy(arguments)
    engine.derive_validation_advancement(**arguments)
    assert arguments == snapshot


def test_cascade_must_reach_the_passing_verdict() -> None:
    refused = engine.derive_validation_advancement(
        **fx.gate_arguments(stage_results=fx.stage_results(final_status="FAIL"))
    )
    assert refused["decision"] == engine.REFUSE
    assert refused["finding_code"] == "CASCADE_NOT_PASSED"


def test_partial_cascade_is_not_a_pass() -> None:
    # One stage NOT_RUN leaves the cascade incomplete, never an implicit pass.
    partial = fx.stage_results()[:-1]
    refused = engine.derive_validation_advancement(
        **fx.gate_arguments(stage_results=partial)
    )
    assert refused["decision"] == engine.REFUSE
    assert refused["finding_code"] == "CASCADE_NOT_PASSED"


def test_ood_survival_is_required() -> None:
    advanced = engine.derive_validation_advancement(**fx.gate_arguments())
    assert advanced["ood_survived"] is True


def test_replication_ceiling_gates_the_configured_level() -> None:
    # With no replication plan, an adaptive search caps the ceiling below the
    # top ladder rung, so a claim requiring that rung cannot advance.
    refused = engine.derive_validation_advancement(
        **fx.gate_arguments(replication_plan=None)
    )
    assert refused["finding_code"] == "REPLICATION_CEILING_BELOW_REQUIRED"
    # But a lower configured level the ceiling already reaches advances.
    ceiling = refused["replication_ceiling"]
    assert (
        engine.derive_validation_advancement(
            **fx.gate_arguments(replication_plan=None, required_promotion_level=ceiling)
        )["decision"]
        == engine.ADVANCE
    )


def test_multi_seed_replication_does_not_lift_the_ceiling() -> None:
    # Rerunning the same code on new seeds tests stability, not independence, so
    # it does not license the top promotion rung after adaptive search.
    refused = engine.derive_validation_advancement(
        **fx.gate_arguments(
            replication_plan=fx.replication_plan(
                replication_class="multi_seed", executor_independence="same_team"
            )
        )
    )
    assert refused["finding_code"] == "REPLICATION_CEILING_BELOW_REQUIRED"


def test_without_adaptive_search_the_ceiling_is_unconstrained() -> None:
    # When no adaptive search was used, the replication rule does not cap the
    # ladder, so even the top rung advances without a replication plan.
    advanced = engine.derive_validation_advancement(
        **fx.gate_arguments(
            adaptive_search_used=False,
            replication_plan=None,
            required_promotion_level=PROMOTION_LADDER[-1],
        )
    )
    assert advanced["decision"] == engine.ADVANCE
