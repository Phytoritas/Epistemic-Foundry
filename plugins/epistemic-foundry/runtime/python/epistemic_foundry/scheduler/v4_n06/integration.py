"""N06 backpressure, missing-worker and resource-lock integration gate.

N05 judges an interleaving: it walks a declared sequence of lane events and
refuses a schedule whose bounds, stage order, failure accounting or fan-in do
not add up.  It says plainly what it does not cover — a lane that simply stops
producing events, an enqueue arriving at a lane already at its bound, and a
resource two holders take at once are all outside its detection.  Those three
are what this module adds, and it adds them *on top of* N05 rather than beside
it: every lane state this gate reasons about is a state N05 computed.

There is exactly one lane state machine in this repository, and it is N05's.
This gate does not walk lane events.  It asks N05 for the verdict on every
prefix of the schedule, and reads the queued and in-flight sets out of the
prefix reports, so "which candidates was the persistence lane carrying at
instant nine" is answered by the sealed module that owns the question.  That is
quadratic, and deliberately so: a second walk here that agreed with N05 today
would be free to disagree with it after the next change to either, and a gate
whose state disagrees with the scheduler it gates is worse than no gate.
``MAX_SCHEDULE_EVENTS`` is where that trade stops being affordable, and a longer
schedule is refused rather than quietly re-derived by a faster copy.

Three failure modes, and each one is refused for a reason that is about
accounting rather than about performance.

Backpressure is not a speed property.  A lane already carrying its declared
bound cannot start another candidate at that instant, so an enqueue arriving
then is deferred by definition; the question this gate answers is what happened
to it afterwards.  A deferred candidate that later starts is fine, and one that
lands in explicit failure accounting is fine, because both leave a record.  One
that does neither was shed in silence, and shedding is the failure mode that
looks exactly like success from the outside: the counts are smaller, nothing
errored, and the work is gone.  The run must also declare which backpressure
policy it implements, and the gate checks the schedule against that declaration
in both directions — a run that promised to defer and instead refused is as
wrong as one that promised a refusal receipt and quietly queued the work,
because in both cases the operator's model of the system is false.

A missing worker is observed as absence, which is why it needs a declared
horizon rather than a timeout.  There is no clock here: the horizon counts
event indices, so "the evaluation lane held two candidates while eleven events
happened elsewhere" is a stall no matter how fast the machine was.  Work in
flight must also belong to someone; a candidate no declared worker holds is a
missing worker in the most literal sense, and naming it is the only way the
stall report can say who stopped.  A schedule that *ends* holding in-flight work
is not reported here at all — that is precisely N05's ``FANIN_INCOMPLETE``, and
restating it under a second code would give one defect two names.

Locks are declared as ledger entries, not inferred from lane events, because a
runtime that takes a lock without saying so is not something a declaration can
reveal.  Given the declaration, four things are refusable: a candidate that
progressed without holding a resource its lane requires, more simultaneous
holders than a resource declared it can carry, a schedule that ends with a
resource still held, and a cycle in the declared waits-for edges.  The cycle is
the deadlock: no participant can proceed, every participant is waiting on work
another participant holds, and it is a property of the graph rather than of how
long anything waited.

Refusals from N05 are re-raised exactly as N05 raised them.  A caller that
catches ``ScheduleError`` is being told the schedule itself does not add up; a
caller that catches ``IntegrationError`` is being told the schedule adds up and
the integration around it does not.  Wrapping the first in the second would send
a reader to this module for a defect that lives in the sealed one.

This module holds no canonical schema enum value as a string literal (EF4-I22),
and no lane, action or stage identity of its own: those are imported from the
scheduler that derives them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from ...domain.hashing import hash_excluding
from ..v4_n05 import (
    LANE_CONCLUDE,
    LANE_ENQUEUE,
    LANE_START,
    LANES,
    LaneEvent,
    load_lane_bounds,
    require_valid_schedule,
    seal_schedule_verdict,
    verify_schedule,
)

#: Immutable stand-ins for the optional declarations, so a default cannot be
#: mutated into the next caller's input.
NO_RESOURCES: Final[Mapping[str, int]] = MappingProxyType({})
NO_REQUIREMENTS: Final[Mapping[str, Sequence[str]]] = MappingProxyType({})

#: What a run may declare it does when a lane is already at its bound.  Deferral
#: holds the work until the lane can take it; the other admits nothing and hands
#: back a receipt naming what it turned away.  A run that does neither is
#: shedding, which is why there is no third member.
ADMISSION_DEFERRAL: Final = "deferral"
ADMISSION_RECEIPTED_REFUSAL: Final = "refusal_receipt"
ADMISSION_POLICIES: Final[tuple[str, ...]] = (
    ADMISSION_DEFERRAL,
    ADMISSION_RECEIPTED_REFUSAL,
)

#: What a holder may do to a declared resource.  Taking and giving back are the
#: only two, so a ledger entry that is neither describes a lock protocol this
#: gate cannot judge.
LOCK_ACQUIRE: Final = "acquire"
LOCK_RELINQUISH: Final = "relinquish"
LOCK_ACTIONS: Final[tuple[str, ...]] = (LOCK_ACQUIRE, LOCK_RELINQUISH)

#: The lane actions that count as a candidate making progress, and therefore as
#: the moments a required resource must actually be held.  Being queued is not
#: progress, and failing is not progress either.
PROGRESS_ACTIONS: Final[tuple[str, ...]] = (LANE_START, LANE_CONCLUDE)

#: The longest schedule this gate will re-derive state for.  State comes from
#: asking N05 about every prefix, so the work grows with the square of the
#: schedule; past this length the honest answer is a refusal rather than a
#: second, faster lane walk that could drift from the sealed one.
MAX_SCHEDULE_EVENTS: Final = 512


class IntegrationError(Exception):
    """Typed refusal carrying the code, message and offending context.

    Deliberately not a subclass of N05's ``ScheduleError``: the two describe
    different layers, and a caller must be able to tell an incoherent schedule
    from a coherent schedule that was integrated badly.
    """

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    raise IntegrationError(code, message, context)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping")
    return dict(value)  # type: ignore[arg-type]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string")
    return str(value)


def _whole(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(
            "INPUT_INVALID",
            f"{label} must be a whole number of at least {minimum}",
            {"value": value},
        )
    return int(value)


@dataclass(frozen=True)
class LockEvent:
    """One holder taking or giving back one declared resource.

    ``instant`` is an index into the lane-event schedule, not a time.  The lock
    event is applied immediately before the lane event at that index, so a
    candidate may take a resource at the same instant it starts using it, and
    an instant equal to the schedule length is the moment after the last lane
    event.
    """

    instant: int
    resource_id: str
    holder_id: str
    action: str


@dataclass(frozen=True)
class WaitEdge:
    """A holder declared to be waiting for a resource at one instant.

    The edge is deliberately not (waiter, waiter): who the waiter is blocked
    *behind* is whoever held the resource at that instant, and that is read out
    of the lock ledger rather than restated here, so a declaration cannot invent
    a wait on a resource nobody was holding.
    """

    instant: int
    holder_id: str
    resource_id: str


def _require_policy(admission_policy: object) -> str:
    policy = _text(admission_policy, "admission_policy")
    if policy not in ADMISSION_POLICIES:
        _fail(
            "ADMISSION_POLICY_UNDECLARED",
            "the run must declare which backpressure policy it implements, "
            "because a schedule can only be checked against a promise that was "
            "actually made",
            {"declared": policy},
        )
    return policy


def _require_schedule_length(events: Sequence[LaneEvent]) -> int:
    count = len(events)
    if count > MAX_SCHEDULE_EVENTS:
        _fail(
            "SCHEDULE_LENGTH_UNSUPPORTED",
            "this gate re-derives every lane state from the sealed scheduler, "
            "one call per prefix, and past this length that guarantee would "
            "have to be traded for a second lane walk that could drift from it",
            {"events": count, "supported_length": MAX_SCHEDULE_EVENTS},
        )
    return count


def _prefix_states(
    repository_root: str | Path,
    *,
    proposed: Sequence[str],
    events: Sequence[LaneEvent],
    lane_limits: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, dict[str, tuple[str, ...]]]]:
    """Lane occupancy at every instant, as computed by the sealed scheduler.

    Entry ``i`` is the state *before* the event at index ``i``, so the last
    entry is the state the schedule ended in.  Nothing here interprets a lane
    action; the queued and in-flight sets are read straight out of N05's own
    report for the prefix, and the concluded sets out of its lane ledgers.
    """

    states: list[dict[str, dict[str, tuple[str, ...]]]] = []
    for index in range(len(events) + 1):
        report = verify_schedule(
            repository_root,
            proposed=proposed,
            events=list(events[:index]),
            lane_limits=lane_limits,
        )
        queued: dict[str, tuple[str, ...]] = {lane: () for lane in LANES}
        in_flight: dict[str, tuple[str, ...]] = {lane: () for lane in LANES}
        for entry in report["incomplete_fanin"]:
            queued[entry["lane"]] = tuple(entry["queued"])
            in_flight[entry["lane"]] = tuple(entry["in_flight"])
        concluded = {
            lane: tuple(values) for lane, values in report["lane_ledgers"].items()
        }
        states.append(
            {"concluded": concluded, "in_flight": in_flight, "queued": queued}
        )
    return states


def _started_instant(
    states: Sequence[Mapping[str, Mapping[str, tuple[str, ...]]]],
    *,
    lane: str,
    candidate_id: str,
    after: int,
) -> int | None:
    """The first instant after ``after`` at which the lane was running it.

    Only a start puts a candidate in flight, so the first prefix that shows it
    running is the prefix immediately after the start; a candidate that started
    and then failed is still seen, which is what keeps a failure from reading as
    a candidate that never started at all.
    """

    for index in range(after + 1, len(states)):
        if candidate_id in states[index]["in_flight"][lane]:
            return index - 1
    return None


def _admission_findings(
    *,
    events: Sequence[LaneEvent],
    states: Sequence[Mapping[str, Mapping[str, tuple[str, ...]]]],
    bounds: Mapping[str, int],
    admission_policy: str,
    refusal_ledger: Sequence[Mapping[str, Any]],
    failure_ledger: Sequence[str],
) -> dict[str, list[dict[str, Any]]]:
    """Account for every candidate a lane could not have started when offered.

    Two things are checked and they are deliberately orthogonal.  Whether the
    schedule did what the declared policy promised is one question; whether the
    work left a record either way is another, and a run can get the first right
    and the second wrong.  Reporting them under one finding would let a shed
    candidate be excused by a matching policy, which is exactly the excuse this
    package exists to remove.
    """

    receipts: dict[tuple[str, str], str] = {}
    unreceipted: list[dict[str, Any]] = []
    unwarranted: list[dict[str, Any]] = []
    for index, entry in enumerate(refusal_ledger):
        record = _mapping(entry, f"refusal_ledger[{index}]")
        lane = _text(record.get("lane"), f"refusal_ledger[{index}].lane")
        if lane not in LANES:
            _fail(
                "REFUSAL_LANE_UNDECLARED",
                "the refusal ledger names a lane the scheduler does not derive, "
                "so the refusal cannot be matched to anything the run did",
                {"lane": lane, "position": index},
            )
        candidate = _text(
            record.get("candidate_id"), f"refusal_ledger[{index}].candidate_id"
        )
        instant = _whole(
            record.get("instant"), f"refusal_ledger[{index}].instant", minimum=0
        )
        if instant >= len(states):
            _fail(
                "REFUSAL_INSTANT_OUT_OF_RANGE",
                "a refusal is anchored past the end of the schedule, so it "
                "names an instant the run never reached",
                {"instant": instant, "position": index},
            )
        position = {
            "candidate_id": candidate,
            "instant": instant,
            "lane": lane,
            "position": index,
        }
        receipt = record.get("receipt_id")
        if not isinstance(receipt, str) or not receipt.strip():
            unreceipted.append(position)
        else:
            receipts[(lane, candidate)] = receipt
        # A refusal is only warranted by pressure: the lane must have been full
        # at the named instant, and the work it turned away must not then be
        # seen running in that same lane.
        carried = len(states[instant]["in_flight"][lane])
        ran = _started_instant(states, lane=lane, candidate_id=candidate, after=-1)
        if carried < bounds[lane] or ran is not None:
            unwarranted.append(
                {**position, "bound": bounds[lane], "in_flight": carried}
            )

    failed = {_text(item, "failure_ledger[]") for item in failure_ledger}
    deferred: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    shed: list[dict[str, Any]] = []

    for instant, event in enumerate(events):
        if event.action != LANE_ENQUEUE:
            continue
        lane = event.lane
        if len(states[instant]["in_flight"][lane]) < bounds[lane]:
            continue
        candidate = event.candidate_id
        started = _started_instant(
            states, lane=lane, candidate_id=candidate, after=instant
        )
        receipt = receipts.get((lane, candidate))
        deferred.append(
            {
                "candidate_id": candidate,
                "instant": instant,
                "lane": lane,
                "refusal_receipt_id": receipt,
                "start_instant": started,
            }
        )
        position = {
            "candidate_id": candidate,
            "declared_admission": admission_policy,
            "instant": instant,
            "lane": lane,
        }
        # Under a deferral promise, queueing the work is correct and handing
        # back a receipt instead is not.  Under a receipted-refusal promise the
        # queueing itself is the broken promise, whatever happens afterwards.
        if admission_policy == ADMISSION_DEFERRAL:
            if receipt is not None:
                conflicts.append(position)
        else:
            conflicts.append(position)
        if started is None and receipt is None and candidate not in failed:
            shed.append(position)

    return {
        "admission_policy_conflicts": conflicts,
        "deferred_admissions": deferred,
        "shed_admissions": shed,
        "unreceipted_refusals": unreceipted,
        "unwarranted_refusals": unwarranted,
    }


def _stall_findings(
    *,
    events: Sequence[LaneEvent],
    states: Sequence[Mapping[str, Mapping[str, tuple[str, ...]]]],
    progress_horizon: int,
    worker_assignments: Mapping[str, str],
) -> dict[str, list[dict[str, Any]]]:
    """Find work a lane was carrying while the schedule moved on without it.

    Progress is tracked for each candidate in each lane rather than for the
    lane as a whole, because a busy lane is the best possible hiding place for
    one stuck candidate: the lane keeps emitting events, its bound keeps being
    respected, and one worker has quietly stopped.  The horizon counts events,
    so the finding says the schedule advanced that far without this work
    advancing at all, which is a statement no machine speed can change.
    """

    workers = {
        _text(candidate, "worker_assignments key"): _text(
            worker, "worker_assignments[]"
        )
        for candidate, worker in worker_assignments.items()
    }
    last_seen: dict[tuple[str, str], int] = {}
    open_stall: set[tuple[str, str]] = set()
    stalled: list[dict[str, Any]] = []
    unattributed: list[dict[str, Any]] = []
    seen_unattributed: set[tuple[str, str]] = set()

    for instant in range(len(events) + 1):
        for lane in LANES:
            for candidate in states[instant]["in_flight"][lane]:
                key = (lane, candidate)
                if candidate not in workers and key not in seen_unattributed:
                    seen_unattributed.add(key)
                    unattributed.append(
                        {"candidate_id": candidate, "instant": instant, "lane": lane}
                    )
                elapsed = instant - last_seen.get(key, -1) - 1
                if elapsed > progress_horizon and key not in open_stall:
                    open_stall.add(key)
                    stalled.append(
                        {
                            "candidate_id": candidate,
                            "elapsed_events": elapsed,
                            "horizon": progress_horizon,
                            "lane": lane,
                            "last_progress_instant": last_seen.get(key, -1),
                            "observed_at": instant,
                            "worker_id": workers.get(candidate),
                        }
                    )
        if instant < len(events):
            key = (events[instant].lane, events[instant].candidate_id)
            last_seen[key] = instant
            open_stall.discard(key)

    return {
        "stalled_lanes": stalled,
        "unattributed_in_flight": unattributed,
    }


def _lock_walk(
    *,
    events: Sequence[LaneEvent],
    lock_events: Sequence[LockEvent],
    resource_capacities: Mapping[str, int],
    lock_requirements: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Apply the declared lock ledger against the declared schedule."""

    capacities: dict[str, int] = {}
    for resource, capacity in resource_capacities.items():
        name = _text(resource, "resource_capacities key")
        capacities[name] = _whole(capacity, f"resource_capacities[{name}]", minimum=1)

    requirements: dict[str, tuple[str, ...]] = {}
    for lane, resources in lock_requirements.items():
        name = _text(lane, "lock_requirements key")
        if name not in LANES:
            _fail(
                "REQUIREMENT_LANE_UNDECLARED",
                "a lock requirement names a lane the scheduler does not derive, "
                "so it would guard work no lane was ever going to do",
                {"lane": name},
            )
        if isinstance(resources, (str, bytes)) or not isinstance(resources, Sequence):
            _fail("INPUT_INVALID", f"lock_requirements[{name}] must be a sequence")
        needed = tuple(
            _text(item, f"lock_requirements[{name}][]")
            for item in resources  # type: ignore[union-attr]
        )
        for item in needed:
            if item not in capacities:
                _fail(
                    "RESOURCE_UNDECLARED",
                    "a lane requires a resource no declared capacity covers, so "
                    "how many holders it may carry at once is unknown",
                    {"lane": name, "resource_id": item},
                )
        requirements[name] = needed

    ledger: list[LockEvent] = []
    previous = 0
    for position, entry in enumerate(lock_events):
        if not isinstance(entry, LockEvent):
            _fail("INPUT_INVALID", f"lock_events[{position}] is not a LockEvent")
        instant = _whole(entry.instant, f"lock_events[{position}].instant", minimum=0)
        if instant > len(events):
            _fail(
                "LOCK_INSTANT_OUT_OF_RANGE",
                "a lock ledger entry is anchored past the end of the schedule, "
                "so it names an instant the run never reached",
                {"instant": instant, "position": position},
            )
        if instant < previous:
            _fail(
                "LOCK_LEDGER_UNORDERED",
                "the lock ledger steps backwards in the schedule, so it cannot "
                "be read as the order in which the resources were taken",
                {"instant": instant, "position": position, "previous": previous},
            )
        previous = instant
        resource = _text(entry.resource_id, f"lock_events[{position}].resource_id")
        if resource not in capacities:
            _fail(
                "RESOURCE_UNDECLARED",
                "the lock ledger names a resource no declared capacity covers, "
                "so how many holders it may carry at once is unknown",
                {"position": position, "resource_id": resource},
            )
        _text(entry.holder_id, f"lock_events[{position}].holder_id")
        if entry.action not in LOCK_ACTIONS:
            _fail(
                "LOCK_ACTION_UNDECLARED",
                "a lock ledger entry is neither a holder taking a resource nor "
                "a holder giving one back, which are the only two this gate "
                "knows how to account for",
                {"action": entry.action, "position": position},
            )
        ledger.append(entry)

    held: dict[str, dict[str, int]] = {name: {} for name in capacities}
    holders_at: list[dict[str, tuple[str, ...]]] = []
    faults: list[dict[str, Any]] = []
    overcommitted: list[dict[str, Any]] = []
    open_overcommit: dict[str, dict[str, Any]] = {}
    unheld: list[dict[str, Any]] = []
    cursor = 0

    for instant in range(len(events) + 1):
        while cursor < len(ledger) and ledger[cursor].instant == instant:
            entry = ledger[cursor]
            cursor += 1
            owners = held[entry.resource_id]
            position = {
                "action": entry.action,
                "holder_id": entry.holder_id,
                "instant": instant,
                "resource_id": entry.resource_id,
            }
            if entry.action == LOCK_ACQUIRE:
                if entry.holder_id in owners:
                    faults.append(position)
                    continue
                owners[entry.holder_id] = instant
                capacity = capacities[entry.resource_id]
                if len(owners) > capacity:
                    record = open_overcommit.get(entry.resource_id)
                    if record is None:
                        record = {
                            "capacity": capacity,
                            "from_instant": instant,
                            "holder_ids": set(owners),
                            "resource_id": entry.resource_id,
                            "to_instant": None,
                        }
                        open_overcommit[entry.resource_id] = record
                        overcommitted.append(record)
                    else:
                        record["holder_ids"].update(owners)
                continue
            if entry.holder_id not in owners:
                faults.append(position)
                continue
            del owners[entry.holder_id]
            record = open_overcommit.get(entry.resource_id)
            if record is not None and len(owners) <= capacities[entry.resource_id]:
                record["to_instant"] = instant
                del open_overcommit[entry.resource_id]

        holders_at.append(
            {name: tuple(sorted(owners)) for name, owners in held.items()}
        )

        if instant == len(events):
            break
        event = events[instant]
        if event.action not in PROGRESS_ACTIONS:
            continue
        for resource in requirements.get(event.lane, ()):
            if event.candidate_id not in held[resource]:
                unheld.append(
                    {
                        "candidate_id": event.candidate_id,
                        "instant": instant,
                        "lane": event.lane,
                        "resource_id": resource,
                    }
                )

    for record in overcommitted:
        record["holder_ids"] = sorted(record["holder_ids"])
        if record["to_instant"] is None:
            record["to_instant"] = len(events)

    retained = [
        {
            "holder_ids": sorted(owners),
            "resource_id": name,
            "since_instant": min(owners.values()),
        }
        for name, owners in sorted(held.items())
        if owners
    ]

    return {
        "holders_at": holders_at,
        "lock_sequence_faults": faults,
        "resource_capacities": dict(sorted(capacities.items())),
        "resource_overcommitments": overcommitted,
        "retained_locks": retained,
        "unheld_progress": unheld,
    }


def _wait_cycles(
    *,
    events: Sequence[LaneEvent],
    wait_edges: Sequence[WaitEdge],
    holders_at: Sequence[Mapping[str, tuple[str, ...]]],
    resource_capacities: Mapping[str, int],
) -> list[dict[str, Any]]:
    """Resolve declared waits against who actually held the resource.

    A cycle in the resulting graph is a deadlock: every holder in it is waiting
    on work another holder in it will not give back.  The cycle is found as a
    strongly connected component over sorted adjacency, so the same declaration
    always names the same participants in the same order.
    """

    edges: dict[str, set[str]] = {}
    resources: dict[tuple[str, str], set[str]] = {}
    for position, edge in enumerate(wait_edges):
        if not isinstance(edge, WaitEdge):
            _fail("INPUT_INVALID", f"wait_edges[{position}] is not a WaitEdge")
        instant = _whole(edge.instant, f"wait_edges[{position}].instant", minimum=0)
        if instant > len(events):
            _fail(
                "WAIT_INSTANT_OUT_OF_RANGE",
                "a declared wait is anchored past the end of the schedule, so "
                "it names an instant the run never reached",
                {"instant": instant, "position": position},
            )
        waiter = _text(edge.holder_id, f"wait_edges[{position}].holder_id")
        resource = _text(edge.resource_id, f"wait_edges[{position}].resource_id")
        if resource not in resource_capacities:
            _fail(
                "RESOURCE_UNDECLARED",
                "a declared wait names a resource no declared capacity covers, "
                "so who the waiter is queued behind cannot be established",
                {"position": position, "resource_id": resource},
            )
        for owner in holders_at[instant][resource]:
            if owner == waiter:
                continue
            edges.setdefault(waiter, set()).add(owner)
            resources.setdefault((waiter, owner), set()).add(resource)

    reachable = {owner for owners in edges.values() for owner in owners}
    order: list[str] = sorted({*edges, *reachable})
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    components: list[list[str]] = []

    for root in order:
        if root in index_of:
            continue
        work: list[tuple[str, list[str]]] = [(root, sorted(edges.get(root, ())))]
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, pending = work[-1]
            if pending:
                nxt = pending.pop(0)
                if nxt not in index_of:
                    index_of[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, sorted(edges.get(nxt, ()))))
                elif nxt in on_stack:
                    low[node] = min(low[node], index_of[nxt])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(sorted(component))

    cycles: list[dict[str, Any]] = []
    for component in sorted(components):
        if len(component) < 2:
            # A single holder cannot be waiting on itself: an edge from a
            # holder to itself is never built, so a one-member component is a
            # holder that merely appears in the graph, not a deadlock.
            continue
        members = set(component)
        cycles.append(
            {
                "holder_ids": component,
                "resource_ids": sorted(
                    {
                        resource
                        for (waiter, owner), names in resources.items()
                        if waiter in members and owner in members
                        for resource in names
                    }
                ),
            }
        )
    return cycles


def verify_integration(
    repository_root: str | Path,
    *,
    proposed: Sequence[str],
    events: Sequence[LaneEvent],
    lane_limits: Mapping[str, Mapping[str, Any]],
    admission_policy: str,
    progress_horizon: int,
    worker_assignments: Mapping[str, str],
    resource_capacities: Mapping[str, int] = NO_RESOURCES,
    lock_events: Sequence[LockEvent] = (),
    lock_requirements: Mapping[str, Sequence[str]] = NO_REQUIREMENTS,
    wait_edges: Sequence[WaitEdge] = (),
    refusal_ledger: Sequence[Mapping[str, Any]] = (),
    failure_ledger: Sequence[str] = (),
    cancelled: Sequence[str] = (),
    effect_receipts: Sequence[Mapping[str, Any]] = (),
    mutation_receipts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Gate one declared run for backpressure, stalls and resource locks.

    The sealed schedule verdict is computed once, in full, and carried in the
    report under its own key rather than merged into this one, so a reader can
    always tell which module refused what.  Nothing passed in is mutated, and
    the only clock is the event index, so the same declaration always produces
    the same report.
    """

    policy = _require_policy(admission_policy)
    horizon = _whole(progress_horizon, "progress_horizon", minimum=1)
    _require_schedule_length(events)
    for position, event in enumerate(events):
        if not isinstance(event, LaneEvent):
            _fail("INPUT_INVALID", f"events[{position}] is not a LaneEvent")

    schedule = verify_schedule(
        repository_root,
        proposed=proposed,
        events=list(events),
        lane_limits=lane_limits,
        failure_ledger=list(failure_ledger),
        cancelled=list(cancelled),
        effect_receipts=list(effect_receipts),
        mutation_receipts=list(mutation_receipts),
    )
    bounds = load_lane_bounds(lane_limits)
    states = _prefix_states(
        repository_root,
        proposed=proposed,
        events=events,
        lane_limits=lane_limits,
    )

    admission = _admission_findings(
        events=events,
        states=states,
        bounds=bounds,
        admission_policy=policy,
        refusal_ledger=refusal_ledger,
        failure_ledger=failure_ledger,
    )
    stalls = _stall_findings(
        events=events,
        states=states,
        progress_horizon=horizon,
        worker_assignments=_mapping(worker_assignments, "worker_assignments"),
    )
    locks = _lock_walk(
        events=events,
        lock_events=lock_events,
        resource_capacities=_mapping(resource_capacities, "resource_capacities"),
        lock_requirements=_mapping(lock_requirements, "lock_requirements"),
    )
    cycles = _wait_cycles(
        events=events,
        wait_edges=wait_edges,
        holders_at=locks["holders_at"],
        resource_capacities=locks["resource_capacities"],
    )

    report: dict[str, Any] = {
        "admission_policy": policy,
        "admission_policy_conflicts": admission["admission_policy_conflicts"],
        "counts": {
            "deferred_admissions": len(admission["deferred_admissions"]),
            "declared_locks": len(lock_events),
            "declared_waits": len(wait_edges),
            "resources": len(locks["resource_capacities"]),
        },
        "deferred_admissions": admission["deferred_admissions"],
        "lock_sequence_faults": locks["lock_sequence_faults"],
        "progress_horizon": horizon,
        "resource_capacities": locks["resource_capacities"],
        "resource_overcommitments": locks["resource_overcommitments"],
        "retained_locks": locks["retained_locks"],
        "schedule": schedule,
        "shed_admissions": admission["shed_admissions"],
        "stalled_lanes": stalls["stalled_lanes"],
        "unattributed_in_flight": stalls["unattributed_in_flight"],
        "unheld_progress": locks["unheld_progress"],
        "unreceipted_refusals": admission["unreceipted_refusals"],
        "unwarranted_refusals": admission["unwarranted_refusals"],
        "wait_cycles": cycles,
    }
    report["integrated"] = bool(schedule["valid"]) and not any(
        report[field] for field in FINDING_CODES
    )
    return report


#: What each unaccounted finding means, in the order a reader should be sent to
#: them.  A lock ledger describing an impossible sequence makes every later lock
#: statement meaningless, so it goes first; then the resource contention and the
#: deadlock, which are the reasons a lane stops; then the stall and the missing
#: worker, which are what stopping looks like from outside; and only then the
#: admission accounting, which is about work that never got far enough to stall.
#: Keys are report fields rather than wire vocabulary, so naming them declares
#: nothing the schemas own.
FINDING_CODES: Final = {
    "lock_sequence_faults": (
        "LOCK_SEQUENCE_IMPOSSIBLE",
        "a holder took a resource it already held or gave back one it did not, "
        "so the lock ledger describes a sequence no resource could have gone "
        "through and every later statement about that resource is unreliable",
    ),
    "resource_overcommitments": (
        "RESOURCE_OVERCOMMITTED",
        "more holders carried one resource at the same time than the capacity "
        "it declared allows, over the named interval, so mutual exclusion was "
        "asserted by the declaration and not enforced by the run",
    ),
    "unheld_progress": (
        "LOCK_REQUIREMENT_UNMET",
        "a candidate made progress in a lane without holding a resource that "
        "lane declared it requires, so the work ran outside the protection the "
        "run claims to have put around it",
    ),
    "wait_cycles": (
        "WAIT_CYCLE_DEADLOCKED",
        "the declared waits-for edges close a cycle, so every holder in it is "
        "waiting on a resource another holder in it will not give back and no "
        "participant can proceed without intervention",
    ),
    "retained_locks": (
        "LOCK_RETAINED_AT_END",
        "the schedule ended with a resource still held, so the next run would "
        "start against a resource this one never gave back and the leak would "
        "be attributed to whoever ran next",
    ),
    "stalled_lanes": (
        "LANE_PROGRESS_STALLED",
        "a lane carried in-flight work while the declared progress horizon of "
        "events passed elsewhere without it producing any, so the named "
        "candidates are stuck rather than merely slow",
    ),
    "unattributed_in_flight": (
        "WORKER_ATTRIBUTION_MISSING",
        "a candidate was in flight while no declared worker held it, so if it "
        "never finishes there is nobody the stall can be attributed to and no "
        "reassignment target either",
    ),
    "admission_policy_conflicts": (
        "ADMISSION_POLICY_CONTRADICTED",
        "the run declared one backpressure behaviour and the schedule shows "
        "the other, so the operator's model of what happens to work offered to "
        "a full lane is false in the direction that matters",
    ),
    "unreceipted_refusals": (
        "ADMISSION_REFUSAL_UNRECEIPTED",
        "work was turned away from a lane with nothing handed back naming it, "
        "so the run discarded the work and the record of having discarded it "
        "in the same step",
    ),
    "unwarranted_refusals": (
        "ADMISSION_REFUSAL_UNWARRANTED",
        "a refusal names an instant at which the lane was not at its bound, or "
        "names work the schedule shows that lane running anyway, so the "
        "accounting asserts a pressure the run did not actually have",
    ),
    "shed_admissions": (
        "ADMISSION_SILENTLY_SHED",
        "work offered to a lane already at its bound neither started later nor "
        "landed in any failure or refusal accounting, so it left the run with "
        "nothing at all recording that it did",
    ),
}


def require_integrated_run(report: Mapping[str, Any]) -> None:
    """Refuse an unaccounted run, naming the failure class that stopped it.

    The sealed scheduler's refusals are raised by the sealed scheduler, from the
    schedule report carried inside this one, so a schedule defect keeps its
    original code and sends a reader to the module that owns it.  They are
    checked after this gate's own findings on purpose: a lane that stalled or a
    resource that deadlocked is *why* the fan-in never completed, and reporting
    the incompleteness first would name the symptom and hide the cause.
    """

    for field, (code, message) in FINDING_CODES.items():
        findings = report.get(field)
        if findings:
            _fail(code, message, {field: findings})

    schedule = report.get("schedule")
    if not isinstance(schedule, Mapping):
        _fail(
            "SCHEDULE_VERDICT_ABSENT",
            "the report carries no schedule verdict, so the interleaving under "
            "the integration was never judged at all",
        )
    require_valid_schedule(schedule)

    if not report.get("integrated"):
        _fail(
            "INTEGRATION_UNACCOUNTED",
            "the run is not marked integrated and no finding explains why",
        )


def seal_integration_record(
    report: Mapping[str, Any], *, run_id: str
) -> dict[str, Any]:
    """Seal a re-derivable record for one gated run.

    The schedule side is not re-derived here: the sealed scheduler seals its own
    verdict and this record carries that hash, so the two records chain instead
    of offering two independent opinions about the same interleaving.  Nothing
    is minted and nothing is timestamped, so two runs over the same declaration
    produce byte-equal records.
    """

    identifier = _text(run_id, "run_id")
    for field in ("admission_policy", "progress_horizon", "resource_capacities"):
        if field not in report:
            _fail(
                "RECORD_INPUT_INCOMPLETE",
                "a record may only be sealed over a report this gate produced",
                {"missing": field},
            )
    schedule = report.get("schedule")
    if not isinstance(schedule, Mapping):
        _fail(
            "RECORD_INPUT_INCOMPLETE",
            "a record may only be sealed over a report this gate produced",
            {"missing": "schedule"},
        )

    record: dict[str, Any] = {
        "admission_policy": report["admission_policy"],
        "findings": {
            field: len(report.get(field) or ()) for field in sorted(FINDING_CODES)
        },
        "integrated": bool(report.get("integrated")),
        "progress_horizon": report["progress_horizon"],
        "resource_capacities": dict(report["resource_capacities"]),  # type: ignore[arg-type]
        "run_id": identifier,
        "schedule_hash": seal_schedule_verdict(schedule, schedule_id=identifier)[
            "verdict_hash"
        ],
    }
    record["integration_hash"] = hash_excluding(record, "integration_hash")
    return record


def integration_hash_matches(record: Mapping[str, Any]) -> bool:
    """True when a sealed record re-derives its own hash from its content."""

    sealed = _mapping(record, "integration record")
    return hash_excluding(sealed, "integration_hash") == sealed.get("integration_hash")
