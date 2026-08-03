"""Executor-resolution gate for the canonical workflow set.

Every workflow declares ``completeness_contract.missing_node_policy: FAIL``,
which says a run fails if a node it needs is missing. That policy is only
meaningful if something checks whether the nodes resolve — and until this gate
existed, nothing did. An audit found that of the code-backed ``executor_ref``
values across the canonical workflows, the large majority name modules that do
not exist, so every workflow is unsatisfiable by its own declared policy while
looking executable.

This gate does not pretend that hole is closed. It makes it *declared*:

* a node whose ``executor_status`` is ``executor_bound`` MUST resolve — a broken
  promise is a hard failure. No node declares the field yet, so that check
  currently covers nothing; the uptake is pinned by a census rather than left
  implied, because a gate over an empty set reads exactly like a gate that
  passed;
* the overall resolution census is pinned, so the number can improve but never
  silently regress;
* prompt-backed and subworkflow nodes are counted separately rather than being
  quietly folded into either side.

Resolution accepts two dispatch shapes, because the repository legitimately uses
both: a module attribute, and membership in a module-level registry mapping
(``NODE_ENTRYPOINTS`` in the promotion authority module binds G01..G13 that way).
An earlier audit reported those thirteen promotion gates as missing precisely
because it only checked attributes; that false positive is why the registry
shape is checked here.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from epistemic_foundry.contracts import repo_root

#: Lower bound on code-backed references that resolve to a callable today.
#: Raise it when the orchestrator gains executors; never lower it to make a
#: change pass. Was 33 while ``_resolves`` accepted non-callable dict members;
#: the honest figure is 25 (12 module attributes + 13 via NODE_ENTRYPOINTS).
MINIMUM_RESOLVED_REFS = 25

#: Upper bound on distinct missing modules. Lower it as modules land.
MAXIMUM_MISSING_MODULES = 225

#: Upper bound on unresolved references. Distinct *modules* is the wrong metric
#: on its own: adding more unbacked nodes that point at an already-missing
#: module never moves that ceiling, so the hole can grow while the number that
#: is supposed to bound it stands still. References are what actually grow.
MAXIMUM_MISSING_REFERENCES = 240

#: Workflow nodes that currently declare ``executor_status``. This is zero: the
#: field exists in node-contract.schema.json as an opt-in promise and no node
#: has taken it up yet, so ``test_nodes_declared_bound_actually_resolve``
#: iterates an empty set and proves nothing today. That is declared here rather
#: than left for a reader to discover, and the count is pinned so the gate stops
#: being vacuous the moment a node does declare one.
EXPECTED_EXECUTOR_STATUS_DECLARATIONS = 0


def _workflow_files() -> list[Path]:
    return sorted((repo_root() / "workflows").glob("*.workflow.yaml"))


def _nodes() -> list[tuple[str, dict]]:
    nodes: list[tuple[str, dict]] = []
    for path in _workflow_files():
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for node in document.get("nodes") or []:
            nodes.append((path.name, node))
    return nodes


def _resolves(reference: str) -> tuple[bool, str]:
    """Resolve ``module:attribute`` to something that can actually be executed.

    Both dispatch shapes must yield a *callable*. An earlier version of this
    helper accepted membership in any module-level dict, which counted eight
    references against ``retrieval.lanes:ABSENT_LANE_REASONS`` — a mapping of
    lane name to the prose reason that lane is deliberately **not** searched —
    as resolved executors. A gate written to stop executor overclaim was itself
    overclaiming by a third, and the census floor had been pinned at the
    inflated figure. The same hole made every module resolve any builtin name,
    because ``__builtins__`` is a dict in every imported module.
    """
    if ":" not in reference:
        return False, "not_a_python_reference"
    module_name, attribute = reference.rsplit(":", 1)
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return False, "module_missing"
    target = getattr(module, attribute, None)
    if callable(target):
        return True, "module_attribute"
    if target is not None:
        return False, "attribute_not_callable"
    for name in dir(module):
        if name.startswith("__"):
            continue
        value = getattr(module, name, None)
        if isinstance(value, dict) and callable(value.get(attribute)):
            return True, f"registry:{name}"
    return False, "attribute_missing"


def _is_python_reference(reference: str) -> bool:
    return ":" in reference and not reference.endswith(".md")


def test_every_workflow_node_declares_an_executor_reference() -> None:
    missing = [
        f"{workflow}:{node.get('node_id')}"
        for workflow, node in _nodes()
        if not str(node.get("executor_ref") or "").strip()
    ]
    assert not missing, f"nodes without an executor_ref: {missing[:10]}"


def test_nodes_declared_bound_actually_resolve() -> None:
    """A node may be unbuilt, but it may not claim to be built and not be."""
    broken = []
    for workflow, node in _nodes():
        if node.get("executor_status") != "executor_bound":
            continue
        reference = str(node.get("executor_ref") or "")
        resolved, how = _resolves(reference)
        if not resolved:
            broken.append(f"{workflow}:{node.get('node_id')} -> {reference} ({how})")
    assert not broken, (
        "nodes declare executor_status 'executor_bound' but do not resolve: "
        + "; ".join(broken)
    )


def test_promotion_gate_chain_resolves() -> None:
    """G00..G14 are the promotion chain; an unbacked gate is a safety defect."""
    from epistemic_foundry.governance.promotion import CANONICAL_GATE_IDS

    module = importlib.import_module(
        "epistemic_foundry.governance.evolution_authority.nodes"
    )
    entrypoints = getattr(module, "NODE_ENTRYPOINTS", None)
    assert isinstance(entrypoints, dict), "NODE_ENTRYPOINTS registry is missing"
    bound = {
        name
        for name, value in entrypoints.items()
        if name.startswith("gate_g") and callable(value)
    }
    assert len(bound) >= len(CANONICAL_GATE_IDS) - 1, (
        f"promotion gate chain is under-bound: {len(bound)} callables for "
        f"{len(CANONICAL_GATE_IDS)} canonical gate ids"
    )


def test_executor_resolution_census_does_not_regress() -> None:
    """Report the hole honestly and forbid it from growing."""
    references = {
        str(node.get("executor_ref") or "")
        for _, node in _nodes()
        if _is_python_reference(str(node.get("executor_ref") or ""))
    }
    resolved: list[str] = []
    missing_modules: set[str] = set()
    attribute_missing: list[str] = []
    for reference in sorted(references):
        ok, how = _resolves(reference)
        if ok:
            resolved.append(reference)
        elif how == "module_missing":
            missing_modules.add(reference.rsplit(":", 1)[0])
        else:
            attribute_missing.append(reference)

    assert len(resolved) >= MINIMUM_RESOLVED_REFS, (
        f"executor resolution regressed: {len(resolved)} resolve, "
        f"expected at least {MINIMUM_RESOLVED_REFS}"
    )
    assert len(missing_modules) <= MAXIMUM_MISSING_MODULES, (
        f"missing executor modules grew to {len(missing_modules)}, "
        f"ceiling is {MAXIMUM_MISSING_MODULES}"
    )
    unresolved = len(references) - len(resolved)
    assert unresolved <= MAXIMUM_MISSING_REFERENCES, (
        f"unresolved executor references grew to {unresolved}, ceiling is "
        f"{MAXIMUM_MISSING_REFERENCES}"
    )


def test_executor_status_declaration_census_is_declared() -> None:
    """State plainly how much the executor_status gate actually covers."""
    declared = [
        f"{workflow}:{node.get('node_id')}"
        for workflow, node in _nodes()
        if node.get("executor_status") is not None
    ]
    assert len(declared) == EXPECTED_EXECUTOR_STATUS_DECLARATIONS, (
        f"{len(declared)} nodes declare executor_status but the census pins "
        f"{EXPECTED_EXECUTOR_STATUS_DECLARATIONS}. Update the constant "
        "deliberately — this gate is only as wide as the field's uptake, and "
        f"the change is: {declared[:10]}"
    )


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_missing_node_policy_is_declared_fail_closed(path: Path) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    contract = document.get("completeness_contract") or {}
    assert contract.get("missing_node_policy") == "FAIL", (
        f"{path.name} does not declare a fail-closed missing_node_policy"
    )
