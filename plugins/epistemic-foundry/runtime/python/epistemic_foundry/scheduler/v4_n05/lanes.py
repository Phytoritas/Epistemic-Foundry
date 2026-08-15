"""N05 bounded proposal/evaluation/persistence lanes and their schedule gate.

Real concurrency is the worst possible thing to gate with a test, because the
interleaving that breaks a bound is exactly the one a test will not reproduce.
So this module does not run lanes; it *judges* an interleaving.  A schedule is a
caller-supplied sequence of lane events, and the position of an event in that
sequence is the only clock there is.  Nothing here reads a wall clock or a random
source, so the same schedule always produces the same verdict, and an interleaving
that broke a bound once can be replayed exactly.

Three lanes, and their identities are derived rather than invented.  The chamber
already names the pipeline stages a candidate moves through, and the three moves
between them are precisely the three lanes: the proposal lane completes a proposed
identity into the next stage, the evaluation lane completes that into the one after,
and the persistence lane completes the last move.  Naming the lanes after the stage
they conclude is what makes the lane ledgers directly usable as reconciliation input
instead of needing a translation table that could drift.

Four things are refused rather than reported.  A lane that carries more in-flight
work than its declared budget allows has exceeded a bound the run committed to
before it started, and the instant it happened is named, because "it peaked at six"
without a position is not replayable.  A candidate that starts evaluation before its
proposal concluded, or persistence before its evaluation concluded, has skipped a
stage the workflow declares.  A candidate that failed but appears in no failure
accounting has vanished silently, which is the failure mode this whole package
exists to prevent.  And a schedule that ends with work still queued or still in
flight has not finished fanning in; reporting its counts as final would launder a
partial result into a complete one.  ``FINDING_CODES`` names three further
classes the same way, so no defect is reported only as a count.

A finding never corrects the schedule it found.  Work that skipped a stage, or
that no one proposed, is still carried through the lanes exactly as the events
describe, so the ledgers show what the run really produced and the reconciliation
sees it too.  Rewriting the interleaving into the one that should have happened
would hide the very thing being judged; only an event with no coherent state to
move from is dropped, and that is itself a named finding.

The phase progression is checked against the workflow rather than asserted.  Node
identities come from the F05 graph loader, the lane-to-node binding lives beside
this module as data, and the loader requires each lane's nodes to depend
transitively on the previous lane's nodes.  This module holds no canonical schema
enum value and no workflow node identity as a string literal (EF4-I22).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ...budgets.envelope import (
    LIMIT_DIMENSIONS,
    BudgetViolation,
    normalize_hard_limits,
)
from ...domain.hashing import hash_excluding
from ...effects.v4_e05 import (
    reconcile_effect_ledger,
    require_effect_reconciliation,
)
from ...evolution.v4_f05 import load_graph
from ...evolution_chamber.reconciliation import (
    STAGES,
    reconcile_candidates,
    require_reconciled,
)

#: The lane-to-workflow-node binding, kept as data so this module names no node.
BINDING_PATH: Final = Path(__file__).with_name("lane-phase-binding.json")

#: Lane identities, derived from the pipeline stage each lane concludes a
#: candidate into.  ``STAGES`` opens at the stage a candidate is already in when
#: it reaches the scheduler, so the lanes are the moves after it.
LANES: Final[tuple[str, ...]] = STAGES[1:]
#: How many lanes this package models.  Checked against the derivation so a
#: pipeline stage added upstream fails here instead of silently adding a lane
#: nothing declares a bound or a phase binding for.
LANE_COUNT: Final = 3
#: The lane that turns a proposed identity into a candidate.
PROPOSAL_LANE: Final = LANES[0]
#: The lane that evaluates a candidate the proposal lane produced.
EVALUATION_LANE: Final = LANES[1]
#: The lane that writes an evaluated candidate into durable state.
PERSISTENCE_LANE: Final = LANES[2]

#: The budget dimension that bounds in-flight work.  This is a limit *field*
#: name from the budget envelope contract, not a wire value, and the loader
#: checks it against the envelope's own dimension list before using it.
CONCURRENCY_DIMENSION: Final = "concurrency"

#: What a caller may say happened to one candidate in one lane.  A candidate is
#: queued, then begins work, then either concludes or fails; there is no fifth
#: thing a lane can do to it.
LANE_ENQUEUE: Final = "enqueue"
LANE_START: Final = "start"
LANE_CONCLUDE: Final = "conclude"
LANE_FAIL: Final = "fail"
ACTIONS: Final[tuple[str, ...]] = (
    LANE_ENQUEUE,
    LANE_START,
    LANE_CONCLUDE,
    LANE_FAIL,
)

#: Which reconciliation this run could perform.  The E05 engine needs effect and
#: mutation receipts; a schedule verified without them reconciles the candidate
#: fan-out only, and says so rather than implying the stronger check ran.
EFFECT_LEDGER_SCOPE: Final = "effect_ledger"
CANDIDATE_LEDGER_SCOPE: Final = "candidate_ledger"


class ScheduleError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    raise ScheduleError(code, message, context)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping")
    return dict(value)  # type: ignore[arg-type]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string")
    return str(value)


def _require_lane_derivation() -> None:
    """The lanes must still be derivable from the pipeline the chamber names."""

    if len(LANES) != LANE_COUNT:
        _fail(
            "LANE_DERIVATION_DRIFT",
            "the pipeline no longer yields the lane count this package models, "
            "so a lane would exist with no declared bound and no phase binding",
            {"declared": LANE_COUNT, "derived": len(LANES)},
        )
    if CONCURRENCY_DIMENSION not in LIMIT_DIMENSIONS:
        _fail(
            "LANE_DERIVATION_DRIFT",
            "the budget envelope no longer declares the dimension that bounds "
            "in-flight work, so a lane bound would be read from nothing",
            {"dimension": CONCURRENCY_DIMENSION},
        )


def upstream_lane(lane: str) -> str | None:
    """The lane a candidate must conclude before this one may start it."""

    if lane not in LANES:
        _fail("LANE_UNDECLARED", "no such lane exists", {"lane": lane})
    index = LANES.index(lane)
    return None if index == 0 else LANES[index - 1]


@dataclass(frozen=True)
class PhaseBinding:
    """Which declared workflow nodes each lane drives, read from the graph."""

    nodes_by_lane: Mapping[str, tuple[str, ...]]
    reasons: Mapping[str, str]

    def nodes_of(self, lane: str) -> tuple[str, ...]:
        if lane not in self.nodes_by_lane:
            _fail("LANE_UNDECLARED", "no such lane exists", {"lane": lane})
        return self.nodes_by_lane[lane]

    def as_report(self) -> dict[str, list[str]]:
        return {lane: list(nodes) for lane, nodes in self.nodes_by_lane.items()}


def _ancestors(
    dependencies: Mapping[str, tuple[str, ...]], node: str
) -> frozenset[str]:
    """Every node reachable upstream of ``node`` in the declared graph."""

    seen: set[str] = set()
    stack = list(dependencies.get(node, ()))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(dependencies.get(current, ()))
    return frozenset(seen)


def load_phase_binding(repository_root: str | Path) -> PhaseBinding:
    """Read the lane-to-node binding and bind it to the declared EVOLVE graph.

    The graph is the authority on which nodes exist and how they depend on each
    other, so both the identities and the ordering are checked against it.  A
    lane whose nodes do not descend from the previous lane's nodes describes a
    phase progression the workflow never declared, and a scheduler that enforced
    that progression would be enforcing its own invention.
    """

    _require_lane_derivation()
    graph = load_graph(repository_root)

    try:
        document = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail("BINDING_UNREADABLE", f"the lane phase binding is unusable: {error}")
        raise  # pragma: no cover - _fail always raises
    if not isinstance(document, Mapping):
        _fail("BINDING_UNREADABLE", "the lane phase binding is not a mapping")
    if not str(document.get("binding_contract", "")).strip():  # type: ignore[union-attr]
        _fail("BINDING_UNREADABLE", "the lane phase binding names no contract")

    entries = document.get("lanes")  # type: ignore[union-attr]
    if not isinstance(entries, Mapping) or not entries:
        _fail("BINDING_UNREADABLE", "the lane phase binding declares no lanes")

    missing = sorted(set(LANES) - set(entries))
    unknown = sorted(set(entries) - set(LANES))
    if missing or unknown:
        _fail(
            "BINDING_DRIFT",
            "the lane phase binding no longer covers the derived lanes exactly",
            {"missing": missing, "unknown": unknown},
        )

    nodes_by_lane: dict[str, tuple[str, ...]] = {}
    reasons: dict[str, str] = {}
    claimed: dict[str, str] = {}
    for lane in LANES:
        entry = _mapping(entries[lane], f"lanes[{lane}]")
        declared = entry.get("node_ids")
        if not isinstance(declared, list) or not declared:
            _fail(
                "BINDING_UNREADABLE",
                f"lane {lane} binds no workflow node",
                {"lane": lane},
            )
        if not str(entry.get("reason", "")).strip():
            _fail(
                "BINDING_UNREASONED",
                "every lane must state why it drives the nodes it claims",
                {"lane": lane},
            )
        nodes = tuple(_text(item, "node_ids[]") for item in declared)
        undeclared = sorted(set(nodes) - set(graph.nodes))
        if undeclared:
            _fail(
                "PHASE_NODE_UNDECLARED",
                "a lane binds a node the workflow does not declare, so the lane "
                "would drive a phase that does not exist",
                {"lane": lane, "nodes": undeclared},
            )
        for node in nodes:
            if node in claimed:
                _fail(
                    "PHASE_NODE_SHARED",
                    "two lanes claim the same workflow node, so one candidate "
                    "would be counted as concluded twice",
                    {"lanes": sorted({claimed[node], lane}), "node": node},
                )
            claimed[node] = lane
        nodes_by_lane[lane] = nodes
        reasons[lane] = str(entry["reason"])

    for lane in LANES:
        previous = upstream_lane(lane)
        if previous is None:
            continue
        required = set(nodes_by_lane[previous])
        unsupported = sorted(
            node
            for node in nodes_by_lane[lane]
            if not (_ancestors(graph.dependencies, node) & required)
        )
        if unsupported:
            _fail(
                "PHASE_ORDER_UNSUPPORTED",
                "a lane's node does not descend from the previous lane's nodes, "
                "so the lane order is asserted rather than declared by the graph",
                {"lane": lane, "nodes": unsupported, "upstream_lane": previous},
            )

    return PhaseBinding(nodes_by_lane=nodes_by_lane, reasons=reasons)


@dataclass(frozen=True)
class LaneEvent:
    """One thing that happened to one candidate in one lane.

    There is no timestamp, on purpose.  The position of the event in the
    schedule is the instant it happened, which is the only ordering a replay can
    reproduce exactly.
    """

    lane: str
    action: str
    candidate_id: str


def load_lane_bounds(lane_limits: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    """Read each lane's in-flight bound from its declared budget limits.

    The limits go through the budget envelope's own normalizer, so a misnamed
    dimension is refused there rather than sitting in the schedule looking like a
    bound while enforcing nothing.  A lane that declares no concurrency limit is
    refused outright: an unbounded lane cannot exceed a bound, which would make
    this gate pass by having nothing to check.
    """

    _require_lane_derivation()
    limits = _mapping(lane_limits, "lane_limits")
    missing = sorted(set(LANES) - set(limits))
    unknown = sorted(set(limits) - set(LANES))
    if missing or unknown:
        _fail(
            "LANE_SET_INVALID",
            "the declared lane budgets do not cover the lanes exactly",
            {"missing": missing, "unknown": unknown},
        )

    bounds: dict[str, int] = {}
    for lane in LANES:
        try:
            normalized = normalize_hard_limits(
                _mapping(limits[lane], f"limits[{lane}]")
            )
        except BudgetViolation as error:
            _fail(
                "LANE_LIMIT_INVALID",
                f"lane {lane} declares a limit the budget contract refuses: {error}",
                {"lane": lane},
            )
            raise  # pragma: no cover - _fail always raises
        bound = normalized[CONCURRENCY_DIMENSION]
        if isinstance(bound, bool) or not isinstance(bound, int) or bound < 1:
            _fail(
                "LANE_UNBOUNDED",
                "a lane must declare an in-flight bound of at least one, because "
                "an unbounded lane can never be observed to exceed anything",
                {"bound": bound, "lane": lane},
            )
        bounds[lane] = int(bound)
    return bounds


@dataclass
class _LaneState:
    """Mutable walk state for one lane; never exposed to the caller."""

    queued: set[str]
    running: set[str]
    concluded: set[str]
    lost: set[str]


def verify_schedule(
    repository_root: str | Path,
    *,
    proposed: Sequence[str],
    events: Sequence[LaneEvent],
    lane_limits: Mapping[str, Mapping[str, Any]],
    failure_ledger: Sequence[str] = (),
    cancelled: Sequence[str] = (),
    effect_receipts: Sequence[Mapping[str, Any]] = (),
    mutation_receipts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Walk a schedule and account for every event, bound and candidate.

    Returns the accounting; ``require_valid_schedule`` turns an unaccounted
    schedule into a typed refusal.  Splitting them keeps the report usable for a
    schedule still being assembled, where lanes still holding work is expected
    rather than a failure.

    Nothing passed in is mutated.  The walk builds its own sets, so a caller can
    hand the same schedule to the gate twice and get byte-equal reports.
    """

    binding = load_phase_binding(repository_root)
    bounds = load_lane_bounds(lane_limits)
    expected = {_text(item, "proposed[]") for item in proposed}

    state = {
        lane: _LaneState(queued=set(), running=set(), concluded=set(), lost=set())
        for lane in LANES
    }
    bound_breaches: list[dict[str, Any]] = []
    order_violations: list[dict[str, Any]] = []
    unsequenced: list[dict[str, Any]] = []
    unproposed: list[dict[str, Any]] = []

    for instant, event in enumerate(events):
        if not isinstance(event, LaneEvent):
            _fail("INPUT_INVALID", f"events[{instant}] is not a LaneEvent")
        if event.lane not in LANES:
            _fail(
                "LANE_UNDECLARED",
                "no such lane exists",
                {"instant": instant, "lane": event.lane},
            )
        if event.action not in ACTIONS:
            _fail(
                "ACTION_UNDECLARED",
                "a lane event must be one of the four things a lane can do",
                {"action": event.action, "instant": instant},
            )
        candidate = _text(event.candidate_id, "candidate_id")
        lane = state[event.lane]
        position = {
            "candidate_id": candidate,
            "instant": instant,
            "lane": event.lane,
        }

        if event.action == LANE_ENQUEUE:
            if candidate in (lane.queued | lane.running | lane.concluded | lane.lost):
                unsequenced.append({**position, "action": event.action})
                continue
            # An unproposed candidate is still queued, because the lane really
            # did accept it.  Dropping it here would hide the work downstream
            # and turn one finding into a cascade of unsequenced events.
            if candidate not in expected:
                unproposed.append(position)
            lane.queued.add(candidate)
            continue

        if event.action == LANE_START:
            if candidate not in lane.queued:
                unsequenced.append(
                    {**position, "action": event.action, "expected": LANE_ENQUEUE}
                )
                continue
            previous = upstream_lane(event.lane)
            if previous is not None and candidate not in state[previous].concluded:
                # The lane started it out of order, and the rest of the schedule
                # is what actually followed; refusing to model the start would
                # replace the observed interleaving with a corrected one.
                order_violations.append({**position, "upstream_lane": previous})
            lane.queued.discard(candidate)
            lane.running.add(candidate)
            if len(lane.running) > bounds[event.lane]:
                bound_breaches.append(
                    {
                        **position,
                        "bound": bounds[event.lane],
                        "in_flight": len(lane.running),
                    }
                )
            continue

        if candidate not in lane.running:
            unsequenced.append(
                {**position, "action": event.action, "expected": LANE_START}
            )
            continue
        lane.running.discard(candidate)
        if event.action == LANE_CONCLUDE:
            lane.concluded.add(candidate)
        else:
            lane.lost.add(candidate)

    incomplete_fanin = [
        {
            "in_flight": sorted(state[name].running),
            "lane": name,
            "queued": sorted(state[name].queued),
        }
        for name in LANES
        if state[name].queued or state[name].running
    ]

    observed_failures: set[str] = set()
    for name in LANES:
        observed_failures |= state[name].lost
    declared_failures = {_text(item, "failure_ledger[]") for item in failure_ledger}
    silent_losses = sorted(observed_failures - declared_failures)
    unaccounted_claims = sorted(declared_failures - observed_failures)

    ledgers = {stage: sorted(state[stage].concluded) for stage in LANES}
    terminal = sorted(declared_failures)
    left_behind = sorted({_text(item, "cancelled[]") for item in cancelled})

    if effect_receipts or mutation_receipts:
        scope = EFFECT_LEDGER_SCOPE
        reconciliation = reconcile_effect_ledger(
            proposed=sorted(expected),
            generated=ledgers[PROPOSAL_LANE],
            evaluated=ledgers[EVALUATION_LANE],
            persisted=ledgers[PERSISTENCE_LANE],
            failed=terminal,
            cancelled=left_behind,
            effect_receipts=effect_receipts,
            mutation_receipts=mutation_receipts,
        )
    else:
        scope = CANDIDATE_LEDGER_SCOPE
        reconciliation = reconcile_candidates(
            proposed=sorted(expected),
            generated=ledgers[PROPOSAL_LANE],
            evaluated=ledgers[EVALUATION_LANE],
            persisted=ledgers[PERSISTENCE_LANE],
            failed=terminal,
            cancelled=left_behind,
        )

    report: dict[str, Any] = {
        "bounds": dict(bounds),
        "counts": {
            "events": len(events),
            "lanes": len(LANES),
            "observed_failures": len(observed_failures),
        },
        "incomplete_fanin": incomplete_fanin,
        "lane_bound_breaches": bound_breaches,
        "lane_ledgers": ledgers,
        "lane_order_violations": order_violations,
        "phase_binding": binding.as_report(),
        "reconciliation": reconciliation,
        "reconciliation_scope": scope,
        "silent_losses": silent_losses,
        "unaccounted_failure_claims": unaccounted_claims,
        "unproposed_candidates": unproposed,
        "unsequenced_events": unsequenced,
    }
    report["valid"] = bool(reconciliation["reconciled"]) and not (
        bound_breaches
        or incomplete_fanin
        or order_violations
        or silent_losses
        or unaccounted_claims
        or unproposed
        or unsequenced
    )
    return report


#: What each unaccounted finding means, in the order a reader should be sent to
#: them: work with no provenance makes every later count meaningless, a schedule
#: describing an impossible interleaving explains the gaps that follow it, and
#: only after the order is established do the bound, the fan-in and the failure
#: accounting mean what they appear to mean.  Keys are report fields, not wire
#: vocabulary, so naming them declares nothing the schemas own.
FINDING_CODES: Final = {
    "unproposed_candidates": (
        "CANDIDATE_UNPROPOSED",
        "a lane accepted a candidate that was never proposed, so work entered "
        "the run with no provenance and no expected count to reconcile against",
    ),
    "unsequenced_events": (
        "EVENT_UNSEQUENCED",
        "a lane event arrived for a candidate that was not in the state the "
        "action requires, so the schedule describes an interleaving no lane "
        "could have produced",
    ),
    "lane_order_violations": (
        "LANE_ORDER_VIOLATED",
        "a candidate began work in a lane before the previous lane concluded "
        "it, so a stage the workflow declares was skipped rather than run",
    ),
    "lane_bound_breaches": (
        "LANE_BOUND_EXCEEDED",
        "a lane carried more in-flight work than the bound it declared before "
        "the run started, at the named instant in the schedule",
    ),
    "incomplete_fanin": (
        "FANIN_INCOMPLETE",
        "the schedule ended with a lane still holding queued or in-flight work, "
        "so its counts are a partial result being reported as a final one",
    ),
    "silent_losses": (
        "SILENT_LOSS",
        "a candidate failed in a lane and appears in no failure accounting, so "
        "it left the run without anything recording that it did",
    ),
    "unaccounted_failure_claims": (
        "FAILURE_UNOBSERVED",
        "the failure accounting names a candidate no lane was observed to fail, "
        "so the ledger asserts an outcome the schedule does not contain",
    ),
}


def require_valid_schedule(report: Mapping[str, Any]) -> None:
    """Refuse an unaccounted schedule, naming the failure class that stopped it.

    The reconciliation refusal is raised by the engine that owns it — E05's when
    receipts were supplied, the chamber's otherwise — rather than being rewrapped
    here.  Restating those failure classes under scheduler codes would give the
    same defect two names and send a reader to the wrong module.
    """

    for field, (code, message) in FINDING_CODES.items():
        findings = report.get(field)
        if findings:
            _fail(code, message, {field: findings})

    reconciliation = report.get("reconciliation")
    if not isinstance(reconciliation, Mapping):
        _fail(
            "RECONCILIATION_ABSENT",
            "the report carries no reconciliation, so the lane ledgers were "
            "never checked against the expected fan-out at all",
        )
    scope = report.get("reconciliation_scope")
    if scope == EFFECT_LEDGER_SCOPE:
        require_effect_reconciliation(reconciliation)
    elif scope == CANDIDATE_LEDGER_SCOPE:
        require_reconciled(reconciliation)
    else:
        _fail(
            "RECONCILIATION_SCOPE_UNKNOWN",
            "the report does not say which reconciliation ran, so how strongly "
            "the lane ledgers were checked cannot be established",
            {"scope": scope},
        )

    if not report.get("valid"):
        _fail(
            "SCHEDULE_UNACCOUNTED",
            "the schedule is not marked valid and no finding explains why",
        )


def seal_schedule_verdict(
    report: Mapping[str, Any], *, schedule_id: str
) -> dict[str, Any]:
    """Seal a re-derivable verdict record for one verified schedule.

    The record carries no timestamp and no minted identifier, so two runs over
    the same schedule produce byte-equal records whose hash re-derives from their
    own content.  A verdict that could not be recomputed from the schedule would
    be an assertion about a run rather than evidence of it.
    """

    identifier = _text(schedule_id, "schedule_id")
    for field in ("bounds", "lane_ledgers", "phase_binding", "reconciliation"):
        if field not in report:
            _fail(
                "VERDICT_INPUT_INCOMPLETE",
                "a verdict may only be sealed over a report this gate produced",
                {"missing": field},
            )
    reconciliation = _mapping(report["reconciliation"], "reconciliation")

    verdict: dict[str, Any] = {
        "bounds": dict(report["bounds"]),  # type: ignore[arg-type]
        "findings": {
            field: len(report.get(field) or ()) for field in sorted(FINDING_CODES)
        },
        "lane_ledgers": {
            lane: list(values)
            for lane, values in dict(report["lane_ledgers"]).items()  # type: ignore[arg-type]
        },
        "phase_binding": {
            lane: list(nodes)
            for lane, nodes in dict(report["phase_binding"]).items()  # type: ignore[arg-type]
        },
        "reconciled": bool(reconciliation.get("reconciled")),
        "reconciliation_scope": report.get("reconciliation_scope"),
        "schedule_id": identifier,
        "valid": bool(report.get("valid")),
    }
    verdict["verdict_hash"] = hash_excluding(verdict, "verdict_hash")
    return verdict


def verdict_hash_matches(verdict: Mapping[str, Any]) -> bool:
    """True when a sealed verdict re-derives its own hash from its content."""

    record = _mapping(verdict, "schedule verdict")
    return hash_excluding(record, "verdict_hash") == record.get("verdict_hash")
