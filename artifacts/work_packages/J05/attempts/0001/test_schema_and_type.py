"""schema_and_type_check — the registry reads its vocabulary, never restates it.

The mutable search space comes from the sealed C05 family index through the I05
intake that already owns reading it, the operator shape from
`mutation-operator-spec`, the prompt genome and its statuses from
`prompt-genome`, and the proposal statuses from `prompt-mutation-proposal`.
Every positional selection this package makes is asserted here against the
declaring schema, so a reordering breaks loudly instead of quietly activating
the wrong status, and every module is scanned for the enum literals EF4-I22
forbids a second runtime copy of.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

from epistemic_foundry.contracts import default_registry
from epistemic_foundry.governance.quarantine import INERT_STATUSES
from epistemic_foundry.operators.v4_j05 import (
    ACTIVE_POSITION,
    FINDING_CODES,
    GOVERNANCE_WORKFLOW,
    OPERATOR_SPEC_KIND,
    PROMPT_GENOME_KIND,
    PROMPT_PROPOSAL_KIND,
    QUARANTINED_POSITION,
    MutationOperatorError,
    active_prompt_status,
    governance_retroactivity_node,
    mutable_genome_kinds,
    mutable_prompt_genome_kind,
    operator_contract,
    prompt_genome_contract,
    prompt_proposal_contract,
    prompt_status_vocabulary,
    proposal_status_vocabulary,
    quarantined_prompt_status,
)
from epistemic_foundry.operators.v4_j05 import declarations as declarations_module

ROOT = Path(__file__).resolve().parents[5]
ENGINE = ROOT / "src/epistemic_foundry/operators/v4_j05"
SEARCH_SPACE_INDEX = ROOT / "schemas/v4_c05/family-index.json"


def string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def engine_literals() -> set[str]:
    held: set[str] = set()
    for path in sorted(ENGINE.glob("*.py")):
        held |= string_literals(path)
    return held


def test_the_search_space_comes_from_the_sealed_c05_index() -> None:
    index = json.loads(SEARCH_SPACE_INDEX.read_text(encoding="utf-8"))
    declared = tuple(
        sorted(
            entry.rsplit("/", 1)[-1].removesuffix(".schema.json")
            for entry in index["mutable_search_space"]
        )
    )

    assert mutable_genome_kinds() == declared
    assert mutable_prompt_genome_kind() == PROMPT_GENOME_KIND
    assert PROMPT_GENOME_KIND in declared


def test_the_prompt_status_vocabulary_is_declared_quarantined_first() -> None:
    # The lifecycle births a genome at position 0 and calls position 2 active.
    # That positional rule is only sound while the schema declares the
    # vocabulary in this order, so the assumption is pinned here.
    document = default_registry().document(PROMPT_GENOME_KIND)

    assert document["properties"]["status"]["enum"] == [
        "QUARANTINED",
        "QUALIFIED",
        "ACTIVE",
        "RETIRED",
        "REJECTED",
    ]
    assert prompt_status_vocabulary() == tuple(document["properties"]["status"]["enum"])
    assert QUARANTINED_POSITION == 0
    assert ACTIVE_POSITION == 2


def test_the_selected_statuses_agree_with_the_quarantines_inert_set() -> None:
    """The positions are checked against the module that owns inertness."""
    assert quarantined_prompt_status() in INERT_STATUSES
    assert active_prompt_status() not in INERT_STATUSES
    assert quarantined_prompt_status() != active_prompt_status()


def test_the_proposal_vocabulary_declares_every_inert_status() -> None:
    document = default_registry().document(PROMPT_PROPOSAL_KIND)

    assert proposal_status_vocabulary() == tuple(
        document["properties"]["status"]["enum"]
    )
    assert INERT_STATUSES <= set(proposal_status_vocabulary())
    assert len(proposal_status_vocabulary()) == 4


def test_every_field_the_lifecycle_writes_is_required_by_the_schema() -> None:
    document = prompt_genome_contract()
    required = set(document["required"])

    assert required <= set(document["properties"])
    for field in (
        "prompt_genome_id",
        "version",
        "task_class",
        "template",
        "allowed_context_classes",
        "forbidden_authorities",
        "fitness_history_ids",
        "parent_prompt_ids",
        "status",
        "prompt_hash",
    ):
        assert field in required, field


def test_every_field_the_registry_reads_is_required_by_the_operator_schema() -> None:
    document = operator_contract()
    required = set(document["required"])

    for field in (
        "operator_id",
        "version",
        "operator_class",
        "input_genome_types",
        "output_genome_type",
        "prompt_ref",
        "risk_class",
        "operator_hash",
    ):
        assert field in required, field


def test_every_field_the_activation_reads_is_required_by_the_proposal_schema() -> None:
    document = prompt_proposal_contract()
    required = set(document["required"])

    for field in (
        "proposal_id",
        "source_prompt_genome_id",
        "proposed_prompt_genome_id",
        "status",
        "proposal_hash",
    ):
        assert field in required, field


def test_the_engine_holds_no_prompt_or_proposal_status_literal() -> None:
    vocabulary = set(prompt_status_vocabulary()) | set(proposal_status_vocabulary())

    assert engine_literals() & vocabulary == set()


def test_the_engine_holds_no_operator_class_or_risk_class_literal() -> None:
    document = default_registry().document(OPERATOR_SPEC_KIND)
    vocabulary = set(document["properties"]["operator_class"]["enum"]) | set(
        document["properties"]["risk_class"]["enum"]
    )

    assert engine_literals() & vocabulary == set()


def test_the_governance_workflow_still_declares_the_retroactivity_node() -> None:
    document = yaml.safe_load((ROOT / GOVERNANCE_WORKFLOW).read_text(encoding="utf-8"))
    declared = {node["node_id"] for node in document["nodes"]}

    assert governance_retroactivity_node() in declared
    assert (
        "current scores are never retroactively repaired by mutable evaluators"
        in (document["invariants"])
    )


def test_every_finding_names_a_typed_code_and_a_reason() -> None:
    assert len(FINDING_CODES) == 27
    for code, reason in FINDING_CODES.items():
        assert code == code.upper()
        assert len(reason) > 50, code


def test_the_refusal_carries_its_code_message_and_context() -> None:
    error = MutationOperatorError("PROMPT_MUTATION_INERT", "message", {"a": 1})

    assert error.code == "PROMPT_MUTATION_INERT"
    assert str(error) == "message"
    assert error.context == {"a": 1}


def test_an_undeclared_finding_code_cannot_be_raised() -> None:
    with pytest.raises(MutationOperatorError) as caught:
        declarations_module._fail("INVENTED_CODE", "message")

    assert caught.value.code == "INPUT_INVALID"
    assert caught.value.context == {"code": "INVENTED_CODE"}
