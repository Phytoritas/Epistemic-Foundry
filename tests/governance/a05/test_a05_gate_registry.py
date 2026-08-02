"""A05 gate registry, applicability matrix, and canonical workflow binding."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from epistemic_foundry.domain.vocabularies import PROMOTION_LADDER
from epistemic_foundry.governance.evolution_authority import (
    EXPECTED_PROMOTION_NODE_COUNT,
    GATE_APPLICABILITY,
    GATE_NODE_BINDINGS,
    NODE_ENTRYPOINTS,
    PROMOTION_WORKFLOW_STEPS,
    REQUIRED_RESOLVED_REF_KEYS,
    RESOLVED_REF_TUPLE_FIELDS,
    EvolutionAuthorityError,
    applicability,
    resolve_references,
    resolve_node_executor,
    verify_evolution_chamber_binding,
    verify_promotion_workflow_binding,
)
from epistemic_foundry.governance.promotion import (
    CANONICAL_GATE_IDS,
    _NOT_REQUIRED_MAX_LEVEL,
)

ROOT = Path(__file__).resolve().parents[3]


def load_workflow(name: str) -> dict:
    return yaml.safe_load(
        (ROOT / "workflows" / f"{name}.workflow.yaml").read_text(encoding="utf-8")
    )


def resolved_refs(**overrides) -> dict:
    refs = {
        key: {
            "logical_id": f"{key}-logical",
            "exact_version_or_revision": "4.0.0",
            "content_hash": "sha256:" + "a" * 64,
            "resolver_id": "resolver-fixture",
            "resolver_version": "1.0.0",
            "resolved_artifact_locator": f"artifacts/pins/{key}.json",
            "resolved_at": "2026-07-31T00:00:00Z",
            "authority_source_class": "canonical_bundle",
            "reproducibility_class": "byte_pinned",
        }
        for key in REQUIRED_RESOLVED_REF_KEYS
    }
    for key, patch in overrides.items():
        refs[key] = {**refs[key], **patch}
    return refs


def test_a05_registry_gate_order_is_the_canonical_g00_g14_set() -> None:
    assert tuple(GATE_APPLICABILITY) == CANONICAL_GATE_IDS
    assert tuple(GATE_NODE_BINDINGS) == CANONICAL_GATE_IDS
    assert len(CANONICAL_GATE_IDS) == 15
    assert len(PROMOTION_WORKFLOW_STEPS) == 18


def test_a05_registry_matrix_matches_the_charter_shape() -> None:
    for gate_id, row in GATE_APPLICABILITY.items():
        assert len(row) == len(PROMOTION_LADDER), gate_id
        assert set(row) <= {"R", "P", "C"}, gate_id
    assert GATE_APPLICABILITY["G13_HUMAN_POLICY_APPROVAL"] == ("C",) * 6
    assert applicability("G05_SEARCH_COVERAGE", "CANDIDATE") == "P"
    assert applicability("G05_SEARCH_COVERAGE", "LITERATURE_GROUNDED") == "R"
    with pytest.raises(EvolutionAuthorityError):
        applicability("G99_UNKNOWN", "CANDIDATE")
    with pytest.raises(EvolutionAuthorityError):
        applicability("G00_PIN_RESOLUTION", "SOMETIMES")


def test_a05_registry_matrix_agrees_with_the_bounded_decider() -> None:
    for gate_id, max_level in _NOT_REQUIRED_MAX_LEVEL.items():
        max_rank = PROMOTION_LADDER.index(max_level)
        row = GATE_APPLICABILITY[gate_id]
        for column, requirement in enumerate(row):
            if requirement == "P":
                assert column <= max_rank, (gate_id, PROMOTION_LADDER[column])
            if requirement == "R":
                assert column > max_rank, (gate_id, PROMOTION_LADDER[column])


def test_a05_registry_resolved_reference_contract_shape() -> None:
    assert len(REQUIRED_RESOLVED_REF_KEYS) == 20
    assert len(RESOLVED_REF_TUPLE_FIELDS) == 9
    outcome = resolve_references(resolved_refs())
    assert outcome == {"status": "PASS", "reasons": []}


def test_a05_registry_promotion_workflow_binding_passes_on_the_canonical_file() -> None:
    document = load_workflow("evolution_promotion")
    summary = verify_promotion_workflow_binding(document)

    assert summary["status"] == "PASS"
    assert summary["node_count"] == EXPECTED_PROMOTION_NODE_COUNT
    assert summary["commit_capability_holder"] == "commit_promotion_atomically"


def test_a05_registry_chamber_binding_passes_on_the_canonical_file() -> None:
    document = load_workflow("evolution_chamber_cycle")
    summary = verify_evolution_chamber_binding(document)

    assert summary["status"] == "PASS"
    assert (
        summary["promotion_delegation"] == "workflows/evolution_promotion.workflow.yaml"
    )


def test_a05_registry_workflow_tampering_fails_closed() -> None:
    document = load_workflow("evolution_promotion")
    nodes = {node["node_id"]: node for node in document["nodes"]}

    nodes["gate_g02_evaluator_holdout_firewall"]["executor_type"] = "llm"
    with pytest.raises(EvolutionAuthorityError) as raised:
        verify_promotion_workflow_binding(document)
    assert raised.value.code == "GATE_EXECUTOR_INVALID"

    document = load_workflow("evolution_promotion")
    nodes = {node["node_id"]: node for node in document["nodes"]}
    nodes["commit_promotion_atomically"]["capabilities"] = ["artifact_read"]
    with pytest.raises(EvolutionAuthorityError):
        verify_promotion_workflow_binding(document)

    document = load_workflow("evolution_promotion")
    nodes = {node["node_id"]: node for node in document["nodes"]}
    nodes["run_parliament_adjudication"]["output_schema_ref"] = (
        "schemas/promotion-decision.schema.json"
    )
    with pytest.raises(EvolutionAuthorityError) as raised:
        verify_promotion_workflow_binding(document)
    assert raised.value.code == "LLM_AUTHORITY_VIOLATION"

    document = load_workflow("evolution_promotion")
    document["nodes"] = document["nodes"][:-1]
    with pytest.raises(EvolutionAuthorityError):
        verify_promotion_workflow_binding(document)


def test_a05_registry_every_bound_runtime_node_resolves() -> None:
    document = load_workflow("evolution_promotion")
    module_prefix = "epistemic_foundry.governance.evolution_authority.nodes:"
    bound = [
        node
        for node in document["nodes"]
        if str(node["executor_ref"]).startswith(module_prefix)
    ]

    assert len(bound) == 21
    for node in bound:
        executor = resolve_node_executor(node["node_id"])
        assert callable(executor)
        assert (
            node["executor_ref"] == f"{module_prefix}{node['node_id']}"
            or node["node_id"] in NODE_ENTRYPOINTS
        )
    with pytest.raises(EvolutionAuthorityError):
        resolve_node_executor("ghost_node")
