"""E06 concurrent candidate effect and idempotency integration gate.

E05 reconciles one run's ledgers after the fact: it is handed a settled set of
effect and mutation receipts and proves they account for each other.  What it
cannot see is how that set came to be.  Two evolution lanes retrying the same
candidate action, or committing over a target one of them never re-read, can
hand E05 a ledger that reconciles perfectly and is still wrong — the duplicate
was minted twice under one key, or one lane's write silently replaced another's.

So this gate closes the integration E05 left open.  Concurrency is modelled as
explicit interleavings rather than threads: the caller declares the candidate
actions and one or more sequences of ``begin``/``effect``/``commit`` events
drawn from several lanes, and the gate replays each sequence deterministically.
There is no clock, no scheduler and no randomness here, so a run either always
refuses an interleaving or always admits it.

Three disciplines are enforced.  An idempotency key binds one payload and one
effect receipt: a retry under the same key with the same payload is collapsed
onto the receipt already bound, the same key carrying a different payload is
``IDEMPOTENCY_KEY_REUSED``, and the same key carrying a second receipt is
``DOUBLE_MINT``.  A commit may only advance a target from the revision the
action actually read, so a write over a revision another lane already replaced
is ``LOST_UPDATE`` naming the pair, and a write over a target whose previous
effect was never observed is ``UNOBSERVED_STATE_ADVANCED`` rather than an
optimistic guess.  Finally, every interleaving the gate admits must settle to
the same ledger; two admitted interleavings that disagree are the concurrency
bug itself, refused as ``INTERLEAVING_DIVERGENT`` naming the diverging pair.

The settled ledger is then handed to the sealed E05 engine rather than
re-checked here, and E05's own verdict is carried inside this gate's report.
The effect-status vocabulary is imported from the module that declares it
(``application/mcp_mutating/ports.py``) and its committed/unobserved projection
is read rather than restated, so this module holds no canonical schema enum
value as a string literal (EF4-I22).  Inputs are copied, never mutated, and
every returned record carries a digest re-derivable from its own content.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from ...application.mcp_mutating.ports import (
    EFFECT_STATUSES,
    STATUS_PROJECTION,
    UNRESOLVED_STATUS,
)
from ...domain.hashing import hash_excluding, sha256_of_payload
from ...domain.ids import new_id
from ..v4_e05 import (
    EffectReconciliationError,
    reconcile_effect_ledger,
    require_effect_reconciliation,
)

#: Every way this gate refuses, and why that refusal exists.  A refusal that
#: names no reason here cannot be raised: `_fail` checks membership first, so a
#: code invented at a call site fails as an input error instead of escaping as
#: an unexplained string.
FINDING_CODES: Final[dict[str, str]] = {
    "ACTION_DUPLICATED": (
        "two candidate action records claim the same action id, so an event "
        "naming that id could be replayed against either of them"
    ),
    "ACTION_UNKNOWN": (
        "an interleaving event names a candidate action the gate was never "
        "given, so the event cannot be replayed against anything real"
    ),
    "ACTION_UNREPLAYED": (
        "an interleaving leaves a declared candidate action out entirely, and "
        "sequences covering different work cannot be compared for agreement"
    ),
    "DOUBLE_MINT": (
        "one idempotency key is bound to two distinct effect receipts, which "
        "is the duplicated external effect the key exists to prevent"
    ),
    "DUPLICATE_EFFECT_SUPPRESSED": (
        "a retry arrived under a key already bound to the same payload, so it "
        "was collapsed onto the existing receipt instead of minting a second"
    ),
    "GATE_INCOMPLETE": (
        "the gate report is not marked reconciled and no finding recorded in "
        "it explains which discipline stopped the run"
    ),
    "GATE_UNRECONCILED": (
        "the settled effect ledger was refused by the sealed E05 candidate "
        "reconciliation, so concurrency held but the run's accounting did not"
    ),
    "IDEMPOTENCY_KEY_REUSED": (
        "one idempotency key was presented with two different payloads, so a "
        "second semantic request would be silently answered by the first"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and replaying it would "
        "record a settlement derived from something never validated"
    ),
    "INTERLEAVINGS_MISSING": (
        "no interleaving was declared, so nothing about concurrent behaviour "
        "was actually exercised and a pass here would mean nothing"
    ),
    "INTERLEAVING_DIVERGENT": (
        "two interleavings the gate admitted settled to different ledgers, so "
        "the effect ledger depends on scheduling and is not serializable"
    ),
    "INTERLEAVING_DUPLICATED": (
        "two declared interleavings share one interleaving id, so a divergence "
        "between them could not be attributed to either sequence"
    ),
    "KEY_RECEIPT_UNBOUND": (
        "an action's effect receipt carries a different idempotency key than "
        "the action itself, so the receipt is evidence for another request"
    ),
    "LANE_BUSY": (
        "a lane began a second candidate action before committing the one it "
        "was already running, which no single lane can actually do"
    ),
    "LANE_UNCLOSED": (
        "an interleaving ends with a lane still running an action, so the "
        "settlement would describe a state no lane ever reached"
    ),
    "LOST_UPDATE": (
        "an action committed over a target revision another action had already "
        "replaced, so the earlier write is silently discarded"
    ),
    "NO_INTERLEAVING_ADMITTED": (
        "every declared interleaving was refused, so the gate proved no "
        "agreement between schedules and cannot report a settled ledger"
    ),
    "PHASE_OUT_OF_ORDER": (
        "a lane's events do not follow begin then effect then commit for one "
        "action, so the sequence describes no execution the runtime can have"
    ),
    "PHASE_UNDECLARED": (
        "an interleaving event names a lane phase outside the declared "
        "vocabulary, so what the runtime was doing at that point is unstated"
    ),
    "REVISION_UNDECLARED": (
        "a candidate action targets a resource whose starting revision was "
        "never declared, so no read it claims to have made can be placed"
    ),
    "STALE_BASE_REVISION": (
        "an action declares a base revision the target never held in this "
        "interleaving, so the read it claims to have made never happened"
    ),
    "STATUS_UNDECLARED": (
        "an effect receipt carries a status outside the declared effect-status "
        "vocabulary, so whether the effect landed cannot be projected"
    ),
    "UNOBSERVED_STATE_ADVANCED": (
        "a later action advanced a target whose previous effect was never "
        "observed, turning an open obligation into an assumption"
    ),
}

#: The lane phases one candidate action passes through, in order.  This gate
#: owns the vocabulary — it names execution positions, not a wire contract — so
#: it is data here rather than a literal repeated at every comparison.
LANE_PHASES: Final[tuple[str, str, str]] = ("begin", "effect", "commit")
BEGIN, EFFECT, COMMIT = LANE_PHASES

#: Fields a candidate action must carry.  These are field names, not wire
#: values, so naming them here declares no vocabulary.
_ACTION_FIELDS: Final = (
    "action_id",
    "base_revision",
    "candidate_id",
    "effect_receipt",
    "idempotency_key",
    "new_revision",
    "payload",
    "target_ref",
)
#: Fields the gate reads off an effect receipt minted by the ledger.
_RECEIPT_FIELDS: Final = ("receipt_id", "idempotency_key", "status")
#: Fields one interleaving event must carry.
_EVENT_FIELDS: Final = ("action_id", "lane", "phase")


class ConcurrentEffectError(Exception):
    """Typed refusal carrying the code, message and offending context."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context: dict[str, Any] = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise ConcurrentEffectError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise ConcurrentEffectError(code, message, context)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return dict(value)  # type: ignore[arg-type]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INPUT_INVALID", f"{label} must be a non-empty string", {"label": label})
    return str(value)


def _require_fields(
    record: Mapping[str, Any], fields: Sequence[str], label: str
) -> None:
    missing = sorted(name for name in fields if name not in record)
    if missing:
        _fail(
            "INPUT_INVALID",
            f"{label} is missing required fields",
            {"label": label, "missing": missing},
        )


def fingerprint_payload(payload: Any) -> str:
    """The semantic fingerprint an idempotency key is bound to.

    Two requests are the same request when their canonical payloads hash the
    same, so the comparison is made on a digest rather than on object identity
    or on a caller-supplied label that could be reused by accident.
    """

    try:
        return sha256_of_payload(payload)
    except (TypeError, ValueError) as error:
        _fail(
            "INPUT_INVALID",
            f"a payload must be canonically serializable: {error}",
        )
        raise  # pragma: no cover - _fail always raises


def _refusal(
    code: str, pair: Sequence[str], context: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """One discipline violation, naming the pair it happened between.

    ``conflicting_pair`` is ordered by replay position — the action already
    holding the ground first, the one that collided with it second — because
    the order is what tells a reader which write was lost.
    """

    if code not in FINDING_CODES:
        _fail("INPUT_INVALID", f"undeclared finding code {code}", {"code": code})
    return {
        "code": code,
        "conflicting_pair": [str(item) for item in pair],
        "context": dict(context or {}),
        "reason": FINDING_CODES[code],
    }


def normalize_actions(
    actions: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Validate the candidate actions and project each one's landing state.

    Whether an effect landed is read from the declaring module's projection
    rather than decided here: it is tri-state, and an unobserved effect must
    never be flattened into "nothing happened".
    """

    normalized: dict[str, dict[str, Any]] = {}
    for position, entry in enumerate(actions):
        label = f"actions[{position}]"
        record = _mapping(entry, label)
        _require_fields(record, _ACTION_FIELDS, label)
        action_id = _text(record["action_id"], f"{label}.action_id")
        if action_id in normalized:
            _fail(
                "ACTION_DUPLICATED",
                f"two action records claim {action_id}",
                {"action_id": action_id},
            )
        receipt = _mapping(record["effect_receipt"], f"{label}.effect_receipt")
        _require_fields(receipt, _RECEIPT_FIELDS, f"{label}.effect_receipt")
        status = _text(receipt["status"], f"{label}.effect_receipt.status")
        if status not in STATUS_PROJECTION:
            _fail(
                "STATUS_UNDECLARED",
                "an effect receipt carries an undeclared status",
                {"declared": list(EFFECT_STATUSES), "status": status},
            )
        key = _text(record["idempotency_key"], f"{label}.idempotency_key")
        receipt_key = _text(
            receipt["idempotency_key"], f"{label}.effect_receipt.idempotency_key"
        )
        if receipt_key != key:
            _fail(
                "KEY_RECEIPT_UNBOUND",
                f"{action_id} presents a receipt bound to another key",
                {"action_key": key, "action_id": action_id, "receipt_key": receipt_key},
            )
        landed, _ = STATUS_PROJECTION[status]
        normalized[action_id] = {
            "action_id": action_id,
            "base_revision": _text(record["base_revision"], f"{label}.base_revision"),
            "candidate_id": _text(record["candidate_id"], f"{label}.candidate_id"),
            "effect_receipt": receipt,
            "effect_receipt_id": _text(
                receipt["receipt_id"], f"{label}.effect_receipt.receipt_id"
            ),
            "idempotency_key": key,
            # Tri-state: True landed, False did not, None never observed.
            "landed": landed,
            "new_revision": _text(record["new_revision"], f"{label}.new_revision"),
            "payload_fingerprint": fingerprint_payload(record["payload"]),
            "status": status,
            "target_ref": _text(record["target_ref"], f"{label}.target_ref"),
        }
    if not normalized:
        _fail("INPUT_INVALID", "the gate needs at least one candidate action")
    return normalized


def _starting_revisions(
    initial_revisions: Mapping[str, Any], actions: Mapping[str, Mapping[str, Any]]
) -> dict[str, str]:
    """Read the starting revision of every target the actions touch.

    Declared rather than inferred from whichever action happened to run first:
    an inferred start would make the settled ledger depend on the schedule
    before a single event was replayed.
    """

    declared = _mapping(initial_revisions, "initial_revisions")
    revisions = {
        _text(target, "initial_revisions key"): _text(
            revision, f"initial_revisions[{target}]"
        )
        for target, revision in declared.items()
    }
    touched = {str(action["target_ref"]) for action in actions.values()}
    missing = sorted(touched - set(revisions))
    if missing:
        _fail(
            "REVISION_UNDECLARED",
            "some targets have no declared starting revision",
            {"missing": missing},
        )
    return revisions


def _bind_effect(
    action: Mapping[str, Any], bindings: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any] | None, bool]:
    """Bind this action's effect to its idempotency key, or refuse.

    Returns the refusal (if any) and whether the action was collapsed onto a
    receipt already bound.  A collapse is the correct outcome of a retry, so it
    is reported as a notice rather than as a failure.

    The binding — not the action — carries whether the effect landed, because
    the key is what the external world deduplicated on.  Recording it per action
    would make the ledger say which attempt won the race, and which attempt won
    a race between identical retries is precisely what must not matter.
    """

    key = str(action["idempotency_key"])
    action_id = str(action["action_id"])
    bound = bindings.get(key)
    if bound is None:
        bindings[key] = {
            "action_ids": [action_id],
            "effect_receipt_id": str(action["effect_receipt_id"]),
            "landed": action["landed"],
            "payload_fingerprint": str(action["payload_fingerprint"]),
        }
        return None, False
    first = str(bound["action_ids"][0])
    if bound["payload_fingerprint"] != action["payload_fingerprint"]:
        return (
            _refusal(
                "IDEMPOTENCY_KEY_REUSED",
                (first, action_id),
                {
                    "bound_fingerprint": bound["payload_fingerprint"],
                    "idempotency_key": key,
                    "arriving_fingerprint": action["payload_fingerprint"],
                },
            ),
            False,
        )
    if bound["effect_receipt_id"] != action["effect_receipt_id"]:
        return (
            _refusal(
                "DOUBLE_MINT",
                (str(bound["effect_receipt_id"]), str(action["effect_receipt_id"])),
                {"action_ids": [first, action_id], "idempotency_key": key},
            ),
            False,
        )
    bound["action_ids"].append(action_id)
    return None, True


def _commit_effect(
    action: Mapping[str, Any],
    *,
    revisions: dict[str, str],
    last_committer: dict[str, str],
    unobserved: Mapping[str, str],
    committed_keys: set[str],
) -> dict[str, Any] | None:
    """Advance the target this action wrote, or refuse the write."""

    target = str(action["target_ref"])
    action_id = str(action["action_id"])
    blocker = unobserved.get(target)
    # An effect that provably did not land wrote nothing, so it neither
    # advances an unobserved target nor loses anyone's update.  An unobserved
    # effect is *not* excused here: stacking a second unobserved write on a
    # target whose state is already unknown is the hazard, not a side note.
    if action["landed"] is False:
        return None
    if blocker is not None and blocker != action_id:
        return _refusal(
            "UNOBSERVED_STATE_ADVANCED",
            (blocker, action_id),
            {"status": UNRESOLVED_STATUS, "target_ref": target},
        )
    if action["landed"] is None:
        # The obligation stays open; a revision this run never observed may not
        # be written into the ledger as though it had been.
        return None
    if revisions[target] != action["base_revision"]:
        winner = last_committer.get(target)
        if winner is None:
            return _refusal(
                "STALE_BASE_REVISION",
                (),
                {
                    "action_id": action_id,
                    "declared_base": action["base_revision"],
                    "target_ref": target,
                    "target_revision": revisions[target],
                },
            )
        return _refusal(
            "LOST_UPDATE",
            (winner, action_id),
            {
                "declared_base": action["base_revision"],
                "target_ref": target,
                "target_revision": revisions[target],
            },
        )
    revisions[target] = str(action["new_revision"])
    last_committer[target] = action_id
    committed_keys.add(str(action["idempotency_key"]))
    return None


def settle_interleaving(
    *,
    actions: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    initial_revisions: Mapping[str, Any],
    interleaving_id: str | None = None,
) -> dict[str, Any]:
    """Replay one declared interleaving and report the ledger it settles to.

    A malformed interleaving raises: an event naming no action, a phase out of
    order or a lane running two actions at once is an authoring error, and
    silently marking it "not admitted" would hide it among genuine concurrency
    findings.  What the settlement may report instead are the discipline
    violations — reuse, double mint, lost update, unobserved advance — which are
    the outcomes this gate exists to distinguish.

    Replay stops at the first violation.  The ledger is then a partial state and
    the settlement is not admitted, so it takes no part in the agreement check.

    The settled ledger is keyed by idempotency key rather than by action id, so
    two schedules that differ only in which identical retry reached the runtime
    first settle to the same record — which is the whole claim a retry makes.
    """

    normalized = normalize_actions(actions)
    revisions = _starting_revisions(initial_revisions, normalized)

    open_lane: dict[str, str] = {}
    phases_seen: dict[str, set[str]] = {}
    bindings: dict[str, dict[str, Any]] = {}
    collapsed: set[str] = set()
    committed_keys: set[str] = set()
    unobserved: dict[str, str] = {}
    last_committer: dict[str, str] = {}
    notices: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []

    for position, entry in enumerate(events):
        label = f"events[{position}]"
        record = _mapping(entry, label)
        _require_fields(record, _EVENT_FIELDS, label)
        lane = _text(record["lane"], f"{label}.lane")
        phase = _text(record["phase"], f"{label}.phase")
        action_id = _text(record["action_id"], f"{label}.action_id")
        if phase not in LANE_PHASES:
            _fail(
                "PHASE_UNDECLARED",
                f"{label} names an undeclared lane phase",
                {"declared": list(LANE_PHASES), "phase": phase},
            )
        if action_id not in normalized:
            _fail(
                "ACTION_UNKNOWN",
                f"{label} names an action the gate was not given",
                {"action_id": action_id},
            )
        action = normalized[action_id]

        if phase == BEGIN:
            if lane in open_lane:
                _fail(
                    "LANE_BUSY",
                    f"lane {lane} is already running {open_lane[lane]}",
                    {"arriving": action_id, "lane": lane, "open": open_lane[lane]},
                )
            if action_id in phases_seen:
                _fail(
                    "PHASE_OUT_OF_ORDER",
                    f"{action_id} begins more than once",
                    {"action_id": action_id, "phase": phase},
                )
            open_lane[lane] = action_id
            phases_seen[action_id] = {phase}
            continue

        if open_lane.get(lane) != action_id:
            _fail(
                "PHASE_OUT_OF_ORDER",
                f"lane {lane} is not running {action_id}",
                {"action_id": action_id, "lane": lane, "phase": phase},
            )
        reached = phases_seen[action_id]
        previous = LANE_PHASES[LANE_PHASES.index(phase) - 1]
        if previous not in reached or phase in reached:
            _fail(
                "PHASE_OUT_OF_ORDER",
                f"{action_id} reached {phase} out of sequence",
                {"action_id": action_id, "phase": phase, "reached": sorted(reached)},
            )
        reached.add(phase)

        if phase == EFFECT:
            refusal, suppressed = _bind_effect(action, bindings)
            if refusal is not None:
                refusals.append(refusal)
                break
            if suppressed:
                collapsed.add(action_id)
                notices.append(
                    _refusal(
                        "DUPLICATE_EFFECT_SUPPRESSED",
                        (
                            str(bindings[action["idempotency_key"]]["action_ids"][0]),
                            action_id,
                        ),
                        {"idempotency_key": action["idempotency_key"]},
                    )
                )
            elif action["landed"] is None:
                unobserved.setdefault(str(action["target_ref"]), action_id)
            continue

        del open_lane[lane]
        if action_id in collapsed:
            # A retry re-commits nothing: the receipt it collapsed onto already
            # accounts for whatever the first attempt did to the target.
            continue
        refusal = _commit_effect(
            action,
            revisions=revisions,
            last_committer=last_committer,
            unobserved=unobserved,
            committed_keys=committed_keys,
        )
        if refusal is not None:
            refusals.append(refusal)
            break

    if not refusals:
        if open_lane:
            _fail(
                "LANE_UNCLOSED",
                "an interleaving ends with a lane still running an action",
                {"open_lanes": dict(sorted(open_lane.items()))},
            )
        unreplayed = sorted(set(normalized) - set(phases_seen))
        if unreplayed:
            _fail(
                "ACTION_UNREPLAYED",
                "an interleaving leaves declared actions out entirely",
                {"unreplayed": unreplayed},
            )

    ledger: dict[str, Any] = {
        "bindings": {
            key: {
                "action_ids": sorted(bound["action_ids"]),
                "effect_receipt_id": bound["effect_receipt_id"],
                "landed": bound["landed"],
                "payload_fingerprint": bound["payload_fingerprint"],
            }
            for key, bound in sorted(bindings.items())
        },
        "committed_keys": sorted(committed_keys),
        "revisions": dict(sorted(revisions.items())),
        # Every bound key falls in exactly one of these three, so an effect can
        # never be silently absent from the accounting: it landed, it provably
        # did not, or its outcome was never observed and stays an obligation.
        "unlanded_keys": sorted(
            key for key, bound in bindings.items() if bound["landed"] is False
        ),
        "unobserved_keys": sorted(
            key for key, bound in bindings.items() if bound["landed"] is None
        ),
    }
    settlement: dict[str, Any] = {
        "admitted": not refusals,
        "interleaving_id": interleaving_id or new_id("EIL"),
        "ledger": ledger,
        "ledger_hash": sha256_of_payload(ledger),
        "notices": notices,
        "refusals": refusals,
    }
    settlement["settlement_hash"] = hash_excluding(settlement, "settlement_hash")
    return settlement


def check_serializability(
    *,
    actions: Sequence[Mapping[str, Any]],
    interleavings: Sequence[Mapping[str, Any]],
    initial_revisions: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay every declared interleaving and require the admitted ones to agree.

    Agreement is the whole claim: a ledger that depends on which lane happened
    to run first is not a ledger, it is a race whose winner was recorded.  So
    the admitted settlements are compared by digest and the first disagreeing
    pair is named, in declaration order, rather than reported as a count.
    """

    if not interleavings:
        _fail("INTERLEAVINGS_MISSING", "the gate was given no interleaving to replay")

    settlements: list[dict[str, Any]] = []
    declared: set[str] = set()
    for position, entry in enumerate(interleavings):
        label = f"interleavings[{position}]"
        record = _mapping(entry, label)
        _require_fields(record, ("events", "interleaving_id"), label)
        interleaving_id = _text(record["interleaving_id"], f"{label}.interleaving_id")
        if interleaving_id in declared:
            _fail(
                "INTERLEAVING_DUPLICATED",
                f"two interleavings claim {interleaving_id}",
                {"interleaving_id": interleaving_id},
            )
        declared.add(interleaving_id)
        events = record["events"]
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
            _fail("INPUT_INVALID", f"{label}.events must be a sequence")
        settlements.append(
            settle_interleaving(
                actions=actions,
                events=list(events),  # type: ignore[arg-type]
                initial_revisions=initial_revisions,
                interleaving_id=interleaving_id,
            )
        )

    admitted = [entry for entry in settlements if entry["admitted"]]
    divergent: list[str] = []
    agreed_hash: str | None = None
    if admitted:
        agreed_hash = str(admitted[0]["ledger_hash"])
        for entry in admitted[1:]:
            if entry["ledger_hash"] != agreed_hash:
                divergent = [
                    str(admitted[0]["interleaving_id"]),
                    str(entry["interleaving_id"]),
                ]
                agreed_hash = None
                break

    report: dict[str, Any] = {
        "admitted_interleaving_ids": [
            str(entry["interleaving_id"]) for entry in admitted
        ],
        "agreed_ledger_hash": agreed_hash,
        "divergent_pair": divergent,
        "refused": [
            {
                "codes": [str(refusal["code"]) for refusal in entry["refusals"]],
                "interleaving_id": str(entry["interleaving_id"]),
            }
            for entry in settlements
            if not entry["admitted"]
        ],
        "serializable": bool(admitted) and not divergent,
        "settlements": settlements,
    }
    report["concurrency_hash"] = hash_excluding(report, "concurrency_hash")
    return report


def run_concurrency_gate(
    *,
    actions: Sequence[Mapping[str, Any]],
    interleavings: Sequence[Mapping[str, Any]],
    initial_revisions: Mapping[str, Any],
    proposed: Sequence[str],
    generated: Sequence[str],
    evaluated: Sequence[str],
    persisted: Sequence[str],
    terminal_failed: Sequence[str] = (),
    terminal_cancelled: Sequence[str] = (),
    mutation_receipts: Sequence[Mapping[str, Any]] = (),
    gate_id: str | None = None,
) -> dict[str, Any]:
    """Prove the effect surface holds under retry and concurrency, then reconcile.

    The concurrency check comes first because it decides *which* receipts the
    run actually produced: without it, a duplicate mint or a lost update would
    be handed to E05 as settled fact and reconcile perfectly.  Only the receipts
    surviving the agreed ledger — exactly one per idempotency key — are passed
    on, and E05's own verdict is carried here rather than re-derived, so this
    gate never becomes a second opinion on candidate accounting.
    """

    concurrency = check_serializability(
        actions=actions,
        interleavings=interleavings,
        initial_revisions=initial_revisions,
    )
    whole_gate_admissible = bool(
        concurrency["serializable"] and not concurrency["refused"]
    )
    receipts_by_id = {
        action["effect_receipt_id"]: action["effect_receipt"]
        for action in normalize_actions(actions).values()
    }

    settled_receipts: list[dict[str, Any]] = []
    reconciliation: dict[str, Any] | None = None
    refusal: dict[str, Any] | None = None
    if whole_gate_admissible:
        agreed = next(
            entry
            for entry in concurrency["settlements"]
            if entry["ledger_hash"] == concurrency["agreed_ledger_hash"]
        )
        settled_receipts = [
            receipts_by_id[str(bound["effect_receipt_id"])]
            for bound in agreed["ledger"]["bindings"].values()
        ]
        try:
            reconciliation = reconcile_effect_ledger(
                proposed=proposed,
                generated=generated,
                evaluated=evaluated,
                persisted=persisted,
                failed=terminal_failed,
                cancelled=terminal_cancelled,
                effect_receipts=settled_receipts,
                mutation_receipts=mutation_receipts,
            )
            require_effect_reconciliation(reconciliation)
        except EffectReconciliationError as error:
            # E05's code is carried, not restated: this gate reports that the
            # sealed engine refused and where to read why.
            refusal = {
                "code": error.code,
                "context": dict(error.context),
                "message": str(error),
            }

    report: dict[str, Any] = {
        "concurrency": concurrency,
        "effect_reconciliation": reconciliation,
        "effect_reconciliation_refusal": refusal,
        "gate_id": gate_id or new_id("ECG"),
        "settled_effect_receipt_ids": sorted(
            str(receipt["receipt_id"]) for receipt in settled_receipts
        ),
    }
    report["reconciled"] = bool(
        whole_gate_admissible
        and refusal is None
        and reconciliation is not None
        and reconciliation["reconciled"]
    )
    report["gate_hash"] = hash_excluding(report, "gate_hash")
    return report


def require_concurrent_effect_gate(report: Mapping[str, Any]) -> None:
    """Refuse a run whose effect surface did not hold, naming what stopped it.

    Any refused interleaving refuses the run.  The caller declares the schedules
    the runtime could actually produce, so one of them violating the discipline
    is that violation happening, not a hypothetical the other schedules excuse.

    Order matters here.  A refused interleaving is reported before a divergence,
    because a schedule the gate never admitted cannot be expected to agree with
    one it did; and both are reported before the E05 verdict, because candidate
    accounting over a ledger that was never settled would name a consequence.
    """

    concurrency = report.get("concurrency")
    if not isinstance(concurrency, Mapping):
        _fail("INPUT_INVALID", "a gate report must carry its concurrency check")
        return  # pragma: no cover - _fail always raises

    for entry in concurrency.get("settlements") or ():
        for refusal in entry.get("refusals") or ():
            _fail(
                str(refusal["code"]),
                str(refusal["reason"]),
                {
                    "conflicting_pair": refusal.get("conflicting_pair"),
                    "context": refusal.get("context"),
                    "interleaving_id": entry.get("interleaving_id"),
                },
            )
    if not concurrency.get("admitted_interleaving_ids"):
        _fail(
            "NO_INTERLEAVING_ADMITTED",
            FINDING_CODES["NO_INTERLEAVING_ADMITTED"],
            {"refused": concurrency.get("refused")},
        )
    if concurrency.get("divergent_pair"):
        _fail(
            "INTERLEAVING_DIVERGENT",
            FINDING_CODES["INTERLEAVING_DIVERGENT"],
            {"divergent_pair": concurrency["divergent_pair"]},
        )
    refusal = report.get("effect_reconciliation_refusal")
    if refusal:
        _fail(
            "GATE_UNRECONCILED",
            FINDING_CODES["GATE_UNRECONCILED"],
            {"effect_reconciliation_refusal": dict(refusal)},
        )
    if not report.get("reconciled"):
        _fail("GATE_INCOMPLETE", FINDING_CODES["GATE_INCOMPLETE"])
