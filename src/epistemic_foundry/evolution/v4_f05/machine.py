"""F05 EVOLVE subprotocol state machine, return edges and typed stop certificates.

A pipeline that only moves forward cannot search.  What makes EVOLVE a search is
the return edge: after a generation is scored, control goes back to parent
selection and does it again.  That edge is also where a search loses its
integrity, because looping is exactly how a run can spin past its budget, resume
from a state that was never sealed, or continue after a safety stop.

So the machine treats the return edge as the thing to constrain.  Forward moves
must follow the dependency the workflow declares; nothing else is a legal
transition.  A return edge is admitted only across a committed checkpoint, so a
run can never re-enter the loop from a resume point that does not exist
(EF4-I61), and the stop certificate must name a checkpoint the run actually
committed.  It is bounded by the run's own LoopContract, so exceeding
``max_iterations`` without stopping is refused rather than run.  And a run may
leave the machine only through a typed stop certificate (EF4-I62): a run that
simply stops is indistinguishable from one that crashed, so it is refused.

The machine deliberately does not claim to order the stop against the
transitions: the caller supplies a run and how it ended, with no evidence of
which came first, so an ordering rule would be asserted rather than derived.
What is derivable is whether the certified resume point is one this run
committed, and that is what is checked.

Every vocabulary is read rather than restated.  Node identities and their
dependencies come from ``workflows/evolution_chamber_cycle.workflow.yaml``, the
terminal states from the same file, and the stop-reason classification from
``evolution_chamber.checkpoint``, which declares it.  This module holds no
canonical schema enum value as a string literal (EF4-I22).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from ...evolution_chamber.checkpoint import (
    ADVERSE_STOPS,
    ORDERLY_STOPS,
    missing_components,
)

#: The workflow that declares the EVOLVE node vocabulary and its dependencies.
WORKFLOW_PATH: Final = "workflows/evolution_chamber_cycle.workflow.yaml"
#: Fields a LoopContract must carry for the machine to bound a return edge.
_LOOP_FIELDS: Final = (
    "entry_node_id",
    "exit_node_id",
    "max_iterations",
    "dry_rounds_required",
)


class EvolveStateError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    raise EvolveStateError(code, message, context)


@dataclass(frozen=True)
class EvolveGraph:
    """The declared node graph, read from the workflow rather than restated."""

    nodes: tuple[str, ...]
    dependencies: Mapping[str, tuple[str, ...]]
    terminal_states: tuple[str, ...]

    def depends_on(self, node: str) -> tuple[str, ...]:
        if node not in self.dependencies:
            _fail(
                "NODE_UNDECLARED", "the workflow declares no such node", {"node": node}
            )
        return self.dependencies[node]

    @property
    def entry_nodes(self) -> tuple[str, ...]:
        return tuple(node for node in self.nodes if not self.dependencies[node])


def load_graph(repository_root: str | Path) -> EvolveGraph:
    """Read the node graph and terminal states from the declaring workflow."""

    path = Path(repository_root) / WORKFLOW_PATH
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as error:
        _fail("WORKFLOW_UNREADABLE", f"{WORKFLOW_PATH} is unusable: {error}")
        raise  # pragma: no cover - _fail always raises
    if not isinstance(document, Mapping):
        _fail("WORKFLOW_UNREADABLE", f"{WORKFLOW_PATH} is not a mapping")

    declared = document.get("nodes")
    if not isinstance(declared, list) or not declared:
        _fail("WORKFLOW_UNREADABLE", "the workflow declares no nodes")

    dependencies: dict[str, tuple[str, ...]] = {}
    order: list[str] = []
    for entry in declared:  # type: ignore[union-attr]
        if not isinstance(entry, Mapping) or "node_id" not in entry:
            _fail("WORKFLOW_UNREADABLE", "a workflow node has no node_id")
        node = str(entry["node_id"])
        if node in dependencies:
            _fail("WORKFLOW_UNREADABLE", "a node id is declared twice", {"node": node})
        upstream = entry.get("depends_on") or []
        if not isinstance(upstream, list):
            _fail("WORKFLOW_UNREADABLE", f"{node} declares a non-list depends_on")
        dependencies[node] = tuple(str(item) for item in upstream)
        order.append(node)

    for node, upstream in dependencies.items():
        unknown = sorted(set(upstream) - set(dependencies))
        if unknown:
            _fail(
                "WORKFLOW_UNREADABLE",
                "a node depends on one the workflow does not declare",
                {"node": node, "unknown": unknown},
            )

    terminal = document.get("terminal_states")
    if not isinstance(terminal, list) or not terminal:
        _fail("WORKFLOW_UNREADABLE", "the workflow declares no terminal states")
    return EvolveGraph(
        nodes=tuple(order),
        dependencies=dependencies,
        terminal_states=tuple(str(item) for item in terminal),  # type: ignore[union-attr]
    )


def stop_reasons() -> tuple[str, ...]:
    """The stop vocabulary, from the module that declares its classification."""

    return tuple(sorted(ORDERLY_STOPS | ADVERSE_STOPS))


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping")
    return dict(value)  # type: ignore[arg-type]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string")
    return str(value)


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail("INPUT_INVALID", f"{label} must be an integer of at least 1")
    return int(value)


@dataclass(frozen=True)
class LoopBound:
    """The return-edge budget a run declared before it started looping."""

    entry_node_id: str
    exit_node_id: str
    max_iterations: int
    dry_rounds_required: int


def load_loop_bound(contract: Mapping[str, Any], graph: EvolveGraph) -> LoopBound:
    """Read the loop contract and bind its endpoints to declared nodes."""

    record = _mapping(contract, "LoopContract")
    missing = sorted(field for field in _LOOP_FIELDS if field not in record)
    if missing:
        _fail(
            "LOOP_CONTRACT_INCOMPLETE",
            "a return edge needs a loop contract that bounds it",
            {"missing": missing},
        )
    entry = _text(record["entry_node_id"], "entry_node_id")
    exit_node = _text(record["exit_node_id"], "exit_node_id")
    for node in (entry, exit_node):
        if node not in graph.dependencies:
            _fail(
                "LOOP_ENDPOINT_UNDECLARED",
                "a loop endpoint must be a node the workflow declares",
                {"node": node},
            )
    if entry == exit_node:
        _fail(
            "LOOP_ENDPOINT_INVALID",
            "a loop whose entry and exit are the same node encloses nothing",
            {"node": entry},
        )
    dry = record["dry_rounds_required"]
    if isinstance(dry, bool) or not isinstance(dry, int) or dry < 0:
        _fail("INPUT_INVALID", "dry_rounds_required must be a non-negative integer")
    return LoopBound(
        entry_node_id=entry,
        exit_node_id=exit_node,
        max_iterations=_positive_int(record["max_iterations"], "max_iterations"),
        dry_rounds_required=int(dry),
    )


@dataclass(frozen=True)
class Transition:
    """One observed move, with whatever the run had sealed when it happened."""

    source: str
    target: str
    checkpoint_id: str | None = None
    checkpoint: Mapping[str, Any] | None = None


def _is_return_edge(graph: EvolveGraph, transition: Transition) -> bool:
    """A move that is not a declared forward dependency of its target."""

    return transition.source not in graph.depends_on(transition.target)


def _validate_forward(graph: EvolveGraph, transition: Transition) -> None:
    if transition.source not in graph.dependencies:
        _fail(
            "NODE_UNDECLARED",
            "the workflow declares no such source node",
            {"node": transition.source},
        )
    graph.depends_on(transition.target)


def evaluate_run(
    repository_root: str | Path,
    *,
    transitions: Sequence[Transition],
    loop_contract: Mapping[str, Any],
    stop_certificate: Mapping[str, Any] | None,
    dry_rounds_observed: int = 0,
) -> dict[str, Any]:
    """Walk an observed run and account for every edge it took.

    Returns the accounting; ``require_valid_run`` turns an unaccounted run into
    a typed refusal.  Splitting them keeps the report usable for a run that is
    still in progress, where an absent stop certificate is expected rather than
    a failure.
    """

    graph = load_graph(repository_root)
    bound = load_loop_bound(loop_contract, graph)

    forward: list[dict[str, str]] = []
    returns: list[dict[str, Any]] = []
    undeclared: list[dict[str, str]] = []
    uncheckpointed: list[dict[str, str]] = []
    incomplete_checkpoints: list[dict[str, Any]] = []
    misplaced: list[dict[str, str]] = []

    for position, transition in enumerate(transitions):
        if not isinstance(transition, Transition):
            _fail("INPUT_INVALID", f"transitions[{position}] is not a Transition")
        _validate_forward(graph, transition)
        edge = {"source": transition.source, "target": transition.target}
        if not _is_return_edge(graph, transition):
            forward.append(edge)
            continue

        # A return edge is only legitimate between the loop's declared
        # endpoints; anything else is a jump the contract never bounded.
        if (
            transition.source != bound.exit_node_id
            or transition.target != bound.entry_node_id
        ):
            misplaced.append(edge)
            undeclared.append(edge)
            continue
        if transition.checkpoint_id is None:
            uncheckpointed.append(edge)
            continue
        if transition.checkpoint is not None:
            gaps = missing_components(transition.checkpoint)
            if gaps:
                incomplete_checkpoints.append({**edge, "missing": gaps})
                continue
        returns.append({**edge, "checkpoint_id": transition.checkpoint_id})

    iterations = len(returns)
    over_budget = iterations > bound.max_iterations
    dry_shortfall = max(0, bound.dry_rounds_required - int(dry_rounds_observed))

    certificate_findings: dict[str, Any] = {}
    stopped_adversely = False
    if stop_certificate is not None:
        record = _mapping(stop_certificate, "EvolutionStopCertificate")
        reason = _text(record.get("stop_reason"), "stop_reason")
        if reason not in stop_reasons():
            certificate_findings["unknown_stop_reason"] = reason
        stopped_adversely = reason in ADVERSE_STOPS
        if not record.get("conditions_observed"):
            certificate_findings["no_conditions_observed"] = True
        if record.get("partial_results_visible") is not True:
            certificate_findings["partial_work_hidden"] = True
        certified_checkpoint = str(record.get("checkpoint_id") or "").strip()
        if not certified_checkpoint:
            certificate_findings["no_checkpoint"] = True
        elif returns and certified_checkpoint not in {
            entry["checkpoint_id"] for entry in returns
        }:
            # The certificate names a resume point this run never committed, so
            # resuming from it would restore a state the run never reached.
            certificate_findings["uncommitted_checkpoint"] = certified_checkpoint
        # A stop that leaves work behind must say so; an empty unresolved set
        # alongside a mid-search stop reason would hide the remaining map.
        unresolved = record.get("unresolved_candidates") or []
        unassessed = record.get("unassessed_niches") or []
        certificate_findings["preserved_work"] = {
            "unassessed_niches": len(unassessed),
            "unresolved_candidates": len(unresolved),
        }

    report: dict[str, Any] = {
        "counts": {
            "forward_edges": len(forward),
            "return_edges": iterations,
            "transitions": len(transitions),
        },
        "dry_round_budget": {
            "minimum": bound.dry_rounds_required,
            "observed": int(dry_rounds_observed),
            "shortfall": dry_shortfall,
        },
        "incomplete_checkpoints": incomplete_checkpoints,
        "iterations": {
            "limit": bound.max_iterations,
            "over_budget": over_budget,
            "used": iterations,
        },
        "loop": {
            "entry_node_id": bound.entry_node_id,
            "exit_node_id": bound.exit_node_id,
        },
        "misplaced_return_edges": misplaced,
        "stop_certificate": certificate_findings or None,
        "stopped_adversely": stopped_adversely,
        "terminated": stop_certificate is not None,
        "uncheckpointed_return_edges": uncheckpointed,
        "undeclared_transitions": undeclared,
    }
    report["valid"] = not (
        undeclared
        or uncheckpointed
        or incomplete_checkpoints
        or misplaced
        or over_budget
        or any(key != "preserved_work" for key in certificate_findings)
    )
    return report


#: What each unaccounted finding means.  Keys are report fields, not wire
#: vocabulary, so naming them declares nothing the schemas own.
FINDING_CODES: Final = {
    "undeclared_transitions": (
        "TRANSITION_UNDECLARED",
        "a move followed no declared dependency and no bounded return edge, so "
        "the run took a path the workflow never described",
    ),
    "misplaced_return_edges": (
        "RETURN_EDGE_MISPLACED",
        "a return edge jumped between nodes the loop contract does not bound, "
        "so the iteration budget never applied to it",
    ),
    "uncheckpointed_return_edges": (
        "RETURN_EDGE_UNCHECKPOINTED",
        "a return edge re-entered the loop without a committed checkpoint, so "
        "the run would resume from a state that was never sealed",
    ),
    "incomplete_checkpoints": (
        "CHECKPOINT_INCOMPLETE",
        "a return edge crossed a checkpoint missing a required component, so "
        "the resume point binds a configuration that never existed",
    ),
}


def require_valid_run(report: Mapping[str, Any]) -> None:
    """Refuse an unaccounted run, naming the failure class that stopped it."""

    for field, (code, message) in FINDING_CODES.items():
        findings = report.get(field)
        if findings:
            _fail(code, message, {field: findings})

    iterations = report.get("iterations") or {}
    if iterations.get("over_budget"):
        _fail(
            "ITERATION_BUDGET_EXCEEDED",
            "the run looped more times than its own contract allows, so the "
            "search continued past the bound it declared before starting",
            dict(iterations),
        )

    if not report.get("terminated"):
        _fail(
            "RUN_UNTERMINATED",
            "the run left the machine without a stop certificate, so a stop "
            "cannot be distinguished from a crash (EF4-I62)",
        )

    findings = report.get("stop_certificate") or {}
    unexpected = sorted(key for key in findings if key != "preserved_work")
    if unexpected:
        _fail(
            "STOP_CERTIFICATE_INVALID",
            "the stop certificate does not certify the stop it records",
            {"findings": {key: findings[key] for key in unexpected}},
        )

    if not report.get("valid"):
        _fail(
            "RUN_UNACCOUNTED",
            "the run is not marked valid and no finding explains why",
        )
