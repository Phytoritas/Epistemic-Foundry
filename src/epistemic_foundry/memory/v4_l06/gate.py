"""Legal hold, deletion execution and retention sweep audit (L06).

L05 decides what a forget *may* do.  Nothing there watches what a runtime
actually *did*, and nothing there knows that an obligation to keep can outrank
an obligation to erase.  Three gates close that distance.

A legal hold is the one instrument that outranks every forget ground.  A
regulated erasure is an obligation to delete; a hold is an obligation to
preserve, placed by a named authority over named candidates or memory classes,
and while it stands the erasure waits.  So a plan whose erased or tombstoned
set touches a standing hold is refused with the hold named, whatever ground the
plan was granted under.  Lifting the hold takes the same recorded authority
shape that placed it and the same legal matter, and lifting a hold nobody
placed is refused rather than reported as freed memory.

A deletion cannot be re-derived after the fact, so the execution is verified
against the plan in both directions.  Memory destroyed that the plan never
authorised is an erasure no authority stands behind; a planned erasure that
never happened and carries no recorded reason leaves the store in a state
neither the plan nor anyone else describes.  The counts must add up exactly,
because "roughly the right number of rows" is how a deletion silently misses.

And a sweep of many plans over time is audited by rebuilding the memory they
left behind.  The reconstruction is L05's own `LineageMemory`: if the survivors
cannot be assembled into a walkable ancestry, that failure *is* the finding
rather than a precondition for looking for one.

Nothing here re-implements what it composes.  Memory classes come from the
memory policy, the protected entry classes from the archive module, and every
plan-level decision from L05 — whose refusals are re-raised as this gate's own
findings with the upstream code intact, never swallowed.

What this gate does not do: erase anything.  The physical delete against the
persistent store, its transaction and its effect receipt belong to the runtime
that owns that store (D05).  This module verifies the report that runtime
produces; it cannot observe the store itself.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

from ...domain.hashing import hash_excluding
from ...domain.ids import new_id
from ...epistemic_species_archive.archive import PROTECTED_ENTRY_CLASSES
from ..policy import MEMORY_CLASSES
from ..v4_l05 import EvolutionMemoryError, LineageMemory, require_executable_forget

#: Every way this gate refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "DELETION_INCOMPLETE": (
        "the plan authorised an outcome the execution did not carry out and "
        "recorded no reason for leaving it, so the memory now sits in neither "
        "the state the plan described nor a state anyone accounted for"
    ),
    "DELETION_UNPLANNED": (
        "the execution erased or tombstoned memory the plan never authorised, "
        "which is a deletion no recorded authority stands behind"
    ),
    "ERASED_ANCESTOR_REFERENCED": (
        "a surviving lineage record names an ancestor an executed plan erased, "
        "so the memory that remains can no longer walk its own ancestry"
    ),
    "ERASED_MEMORY_RETAINED": (
        "a candidate an executed plan erased still holds a lineage record or "
        "an archive entry, so the erasure was reported but never carried out"
    ),
    "EXECUTION_COUNTS_UNRECONCILED": (
        "the planned, executed and deferred outcome counts do not add up, so "
        "some candidate was silently added to or dropped from the deletion"
    ),
    "HOLD_AUTHORITY_MISMATCHED": (
        "the release names a different legal matter than the hold was placed "
        "under, and a preservation order may not be lifted by an unrelated "
        "authority that never carried the obligation"
    ),
    "HOLD_AUTHORITY_MISSING": (
        "placing or releasing a legal hold needs an authority id, a legal "
        "matter and an approver; an unattributed hold cannot be audited and an "
        "unattributed release cannot be answered for"
    ),
    "HOLD_DUPLICATED": (
        "the register was given two records under one hold id, so which scope "
        "and which authority actually stand cannot be decided"
    ),
    "HOLD_RELEASED_ALREADY": (
        "the hold this release names was already lifted, and recording a "
        "second lift would suggest a protection was standing when it was not"
    ),
    "HOLD_SCOPE_EMPTY": (
        "a legal hold that names neither a candidate nor a memory class holds "
        "nothing at all, and an empty hold reads as protection that is absent"
    ),
    "HOLD_UNKNOWN": (
        "the release names a hold the register does not hold, so there is "
        "nothing to lift and the caller would believe memory had been freed"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this gate requires, and continuing would "
        "record a verdict derived from something it never validated"
    ),
    "LEGAL_HOLD_ACTIVE": (
        "a legal hold stands over memory this forget would erase or tombstone, "
        "and a preservation order outranks every forget ground, a regulated "
        "erasure being executed under one included"
    ),
    "PLAN_HASH_MISMATCH": (
        "the forget plan does not re-derive its own hash, so the plan being "
        "executed is not the plan whose refusals and outcomes were decided"
    ),
    "RETENTION_SWEEP_BROKEN": (
        "the lineage memory left behind by the executed plans cannot be "
        "reconstructed at all, and a memory that cannot be rebuilt has already "
        "lost the ancestry the retention rules exist to protect"
    ),
    "TOMBSTONE_FACTS_LOST": (
        "a protected entry that was tombstoned no longer carries the class, "
        "reason and hash the tombstone exists to keep, so the only surviving "
        "trace that the knowledge existed is itself gone"
    ),
    "UPSTREAM_MEMORY_REFUSED": (
        "the composed L05 retention engine refused this input, and its finding "
        "is reported here with its own code rather than swallowed by the gate"
    ),
}

#: The authority shape a hold is placed and released under.  Both directions
#: use the same list: a release recorded more loosely than the placement would
#: make the weaker record the one that decides.
HOLD_AUTHORITY_FIELDS: tuple[str, ...] = (
    "approved_by",
    "hold_authority_id",
    "legal_matter_id",
)

#: The fields a placement digest covers.  A release adds its own fields and its
#: own digest, so the placement stays independently re-derivable afterwards.
HOLD_PLACEMENT_FIELDS: tuple[str, ...] = (
    "held_candidate_ids",
    "held_memory_classes",
    "hold_authority",
    "hold_id",
    "placed_at",
)

#: What a tombstone must still carry.  These are exactly the facts L05 keeps
#: when the payload goes; losing any of them loses the evidence that the
#: negative knowledge was ever paid for.
TOMBSTONE_FACT_FIELDS: tuple[str, ...] = (
    "archive_entry_id",
    "artifact_hash",
    "candidate_id",
    "entry_class",
    "generation",
    "lineage_id",
    "retention_reason",
)


class MemoryGateError(ValueError):
    """A hold, a deletion execution or a retention sweep was refused."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise MemoryGateError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise MemoryGateError(code, message, context)


def _upstream_finding(error: EvolutionMemoryError, action: str) -> dict[str, Any]:
    """L05's refusal, recorded whole so nothing about it has to be re-guessed."""
    return {
        "action": action,
        "upstream_code": error.code,
        "upstream_context": dict(error.context),
        "upstream_message": str(error),
    }


@contextmanager
def _upstream(action: str) -> Iterator[None]:
    """Re-raise an L05 refusal as this gate's finding, with its code intact."""
    try:
        yield
    except EvolutionMemoryError as error:
        raise MemoryGateError(
            "UPSTREAM_MEMORY_REFUSED",
            f"the retention engine refused {action}: {error}",
            _upstream_finding(error, action),
        ) from error


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


def _require_id(value: object, label: str) -> str:
    identifier = str(value if value is not None else "").strip()
    if not identifier:
        _fail("INPUT_INVALID", f"{label} must be a non-empty id", {"label": label})
    return identifier


def _unique_ids(values: object, label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail("INPUT_INVALID", f"{label} must be a sequence of ids", {"label": label})
    cleaned: list[str] = []
    for position, value in enumerate(values):  # type: ignore[arg-type]
        identifier = _require_id(value, f"{label}[{position}]")
        if identifier in cleaned:
            _fail(
                "INPUT_INVALID",
                f"{label} names {identifier} twice",
                {"duplicate": identifier, "label": label},
            )
        cleaned.append(identifier)
    return tuple(cleaned)


def _hold_authority(authority: object, label: str) -> dict[str, str]:
    record = _require_mapping(authority, label)
    granted = {
        field: str(record.get(field) or "").strip() for field in HOLD_AUTHORITY_FIELDS
    }
    missing = sorted(field for field, value in granted.items() if not value)
    if missing:
        _fail(
            "HOLD_AUTHORITY_MISSING",
            f"{label} does not record {missing}",
            {
                "label": label,
                "missing": missing,
                "required_fields": list(HOLD_AUTHORITY_FIELDS),
            },
        )
    return granted


def hold_placement_hash(hold: Mapping[str, Any]) -> str:
    """Re-derive a hold's placement digest from exactly the fields it covers."""
    record = _require_mapping(hold, "hold_record")
    missing = sorted(field for field in HOLD_PLACEMENT_FIELDS if field not in record)
    if missing:
        _fail(
            "INPUT_INVALID",
            f"a hold record is missing {missing}",
            {"missing": missing, "required_fields": list(HOLD_PLACEMENT_FIELDS)},
        )
    placement = {field: record[field] for field in HOLD_PLACEMENT_FIELDS}
    return hash_excluding(placement, "hold_hash")


def place_legal_hold(
    *,
    hold_id: str,
    authority: Mapping[str, Any],
    placed_at: str,
    candidate_ids: Sequence[str] = (),
    memory_classes: Sequence[str] = (),
) -> dict[str, Any]:
    """Record a preservation order over candidates and/or memory classes.

    Scope is caller-supplied because only the caller knows which matter reaches
    which memory.  What is not caller-supplied is whether the scope may be
    empty: a hold naming nothing would pass every later intersection test while
    protecting nothing, which is worse than no hold at all.
    """
    granted = _hold_authority(authority, "authority")
    identifier = _require_id(hold_id, "hold_id")
    held_candidates = _unique_ids(candidate_ids, "candidate_ids")
    held_classes = _unique_ids(memory_classes, "memory_classes")
    unknown = sorted(set(held_classes) - set(MEMORY_CLASSES))
    if unknown:
        _fail(
            "INPUT_INVALID",
            "the hold names memory classes the policy cannot express",
            {"declared": list(MEMORY_CLASSES), "unknown": unknown},
        )
    if not held_candidates and not held_classes:
        _fail(
            "HOLD_SCOPE_EMPTY",
            f"hold {identifier} names neither a candidate nor a memory class",
            {"hold_id": identifier},
        )
    record: dict[str, Any] = {
        "held_candidate_ids": sorted(held_candidates),
        "held_memory_classes": sorted(held_classes),
        "hold_authority": granted,
        "hold_id": identifier,
        "placed_at": str(placed_at),
    }
    record["hold_hash"] = hold_placement_hash(record)
    return record


class LegalHoldRegister:
    """The holds standing over a workspace's memory at one point in time.

    The register verifies each record's placement digest on construction rather
    than trusting it, because a hold that has been edited after the fact is the
    one thing that could quietly widen or narrow what a deletion may touch.
    """

    def __init__(self, records: Sequence[Mapping[str, Any]] = ()) -> None:
        by_id: dict[str, dict[str, Any]] = {}
        for index, given in enumerate(records):
            record = dict(_require_mapping(given, f"holds[{index}]"))
            identifier = _require_id(record.get("hold_id"), f"holds[{index}].hold_id")
            if identifier in by_id:
                _fail(
                    "HOLD_DUPLICATED",
                    f"the register was given hold {identifier} twice",
                    {"hold_id": identifier},
                )
            declared = str(record.get("hold_hash") or "")
            derived = hold_placement_hash(record)
            if declared != derived:
                _fail(
                    "INPUT_INVALID",
                    f"hold {identifier} does not re-derive its placement hash",
                    {"declared": declared, "derived": derived, "hold_id": identifier},
                )
            _hold_authority(record.get("hold_authority"), f"holds[{index}].authority")
            by_id[identifier] = record
        self._holds = by_id

    def hold_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._holds))

    def hold(self, hold_id: str) -> Mapping[str, Any]:
        identifier = _require_id(hold_id, "hold_id")
        if identifier not in self._holds:
            _fail(
                "HOLD_UNKNOWN",
                f"the register does not hold {identifier}",
                {"hold_id": identifier, "known": list(self.hold_ids())},
            )
        return dict(self._holds[identifier])

    def standing(self) -> tuple[dict[str, Any], ...]:
        """The holds that have not been released, in id order."""
        return tuple(
            dict(record)
            for _, record in sorted(self._holds.items())
            if not str(record.get("released_at") or "").strip()
        )

    def standing_ids(self) -> tuple[str, ...]:
        return tuple(str(record["hold_id"]) for record in self.standing())

    def _declared_classes(
        self, targets: Sequence[str], candidate_classes: object
    ) -> dict[str, str]:
        given = _require_mapping(
            candidate_classes if candidate_classes is not None else {},
            "candidate_classes",
        )
        mapped: dict[str, str] = {}
        for key, value in given.items():
            memory_class = _require_id(value, f"candidate_classes[{key}]")
            if memory_class not in MEMORY_CLASSES:
                _fail(
                    "INPUT_INVALID",
                    f"candidate_classes[{key}] names a class the policy lacks",
                    {"declared": list(MEMORY_CLASSES), "given": memory_class},
                )
            mapped[str(key)] = memory_class
        if any(record["held_memory_classes"] for record in self.standing()):
            # Fail closed: a class-scoped hold cannot be evaluated against
            # memory whose class nobody declared, and assuming it falls outside
            # the hold is exactly the assumption that erases held memory.
            undeclared = sorted(set(targets) - set(mapped))
            if undeclared:
                _fail(
                    "INPUT_INVALID",
                    "a class-scoped hold stands but these candidates declare "
                    "no memory class",
                    {"undeclared": undeclared},
                )
        return mapped

    def covering(
        self,
        *,
        candidate_ids: Sequence[str],
        candidate_classes: Mapping[str, str] | None = None,
    ) -> dict[str, tuple[str, ...]]:
        """Which standing holds reach which of the named candidates."""
        targets = _unique_ids(candidate_ids, "candidate_ids")
        classes = self._declared_classes(targets, candidate_classes)
        found: dict[str, tuple[str, ...]] = {}
        for record in self.standing():
            held_ids = set(record["held_candidate_ids"])
            held_classes = set(record["held_memory_classes"])
            covered = tuple(
                sorted(
                    target
                    for target in targets
                    if target in held_ids or classes.get(target) in held_classes
                )
            )
            if covered:
                found[str(record["hold_id"])] = covered
        return found


def release_legal_hold(
    *,
    register: LegalHoldRegister,
    hold_id: str,
    authority: Mapping[str, Any],
    released_at: str,
) -> dict[str, Any]:
    """Lift a standing hold under the same authority shape that placed it.

    The legal matter must match as well as the shape.  A hold placed for one
    matter and lifted by the approver of another is a preservation order
    ending for a reason nobody in the original matter ever gave.
    """
    granted = _hold_authority(authority, "release_authority")
    placed = register.hold(hold_id)
    if str(placed.get("released_at") or "").strip():
        _fail(
            "HOLD_RELEASED_ALREADY",
            f"hold {placed['hold_id']} was already released",
            {
                "hold_id": str(placed["hold_id"]),
                "released_at": str(placed["released_at"]),
            },
        )
    matter = str(placed["hold_authority"]["legal_matter_id"])
    if granted["legal_matter_id"] != matter:
        _fail(
            "HOLD_AUTHORITY_MISMATCHED",
            f"hold {placed['hold_id']} was placed under a different matter",
            {
                "hold_id": str(placed["hold_id"]),
                "placed_under": matter,
                "released_under": granted["legal_matter_id"],
            },
        )
    released: dict[str, Any] = {
        **placed,
        "release_authority": granted,
        "released_at": str(released_at),
    }
    released["release_hash"] = hash_excluding(released, "release_hash")
    return released


def verify_plan_hash(plan: Mapping[str, Any]) -> str:
    """Raise unless the forget plan re-derives the hash it publishes."""
    record = dict(_require_mapping(plan, "plan"))
    declared = str(record.get("plan_hash") or "")
    derived = hash_excluding(record, "plan_hash")
    if declared != derived:
        _fail(
            "PLAN_HASH_MISMATCH",
            "the forget plan does not re-derive its own hash",
            {
                "declared": declared,
                "derived": derived,
                "plan_id": str(record.get("plan_id") or ""),
            },
        )
    return derived


def _planned_outcomes(plan: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """The candidates the plan authorised, split by outcome."""
    erased = _unique_ids(plan.get("erased"), "plan.erased")
    rows = plan.get("tombstoned")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        _fail("INPUT_INVALID", "plan.tombstoned must be a sequence of rows")
    tombstoned = _unique_ids(
        [
            _require_mapping(row, f"plan.tombstoned[{index}]").get("candidate_id")
            for index, row in enumerate(rows)  # type: ignore[arg-type]
        ],
        "plan.tombstoned",
    )
    overlap = sorted(set(erased) & set(tombstoned))
    if overlap:
        _fail(
            "EXECUTION_COUNTS_UNRECONCILED",
            "the plan gives these candidates two outcomes at once",
            {"overlap": overlap, "plan_id": str(plan.get("plan_id") or "")},
        )
    counts = _require_mapping(plan.get("counts"), "plan.counts")
    stated: dict[str, int] = {}
    for field in ("erased", "tombstoned"):
        given = counts.get(field)
        if not isinstance(given, int) or isinstance(given, bool):
            _fail(
                "INPUT_INVALID",
                f"plan.counts.{field} must be an integer",
                {"field": field, "given": repr(given)},
            )
        stated[field] = int(given)  # type: ignore[arg-type]
    listed = {"erased": len(erased), "tombstoned": len(tombstoned)}
    if stated != listed:
        _fail(
            "EXECUTION_COUNTS_UNRECONCILED",
            "the plan's stated counts do not match the outcomes it lists",
            {"listed": listed, "stated": stated},
        )
    return {"erased": erased, "tombstoned": tombstoned}


def require_forget_permitted(
    *,
    plan: Mapping[str, Any],
    register: LegalHoldRegister,
    candidate_classes: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Raise unless no standing hold reaches what this plan would remove.

    The plan's ground is recorded in the refusal context rather than consulted:
    a hold outranks every ground, so there is no ground to check against.
    """
    record = _require_mapping(plan, "plan")
    outcomes = _planned_outcomes(record)
    targeted = sorted(set(outcomes["erased"]) | set(outcomes["tombstoned"]))
    if not targeted:
        return register.standing_ids()
    conflicts = register.covering(
        candidate_ids=targeted, candidate_classes=candidate_classes
    )
    if conflicts:
        named = sorted(conflicts)[0]
        authority = record.get("authority")
        ground = ""
        if isinstance(authority, Mapping):
            ground = str(authority.get("ground") or "")
        _fail(
            "LEGAL_HOLD_ACTIVE",
            f"legal hold {named} stands over memory this forget would remove",
            {
                "conflicts": {
                    key: list(value) for key, value in sorted(conflicts.items())
                },
                "forget_ground": ground,
                "hold_id": named,
                "plan_id": str(record.get("plan_id") or ""),
            },
        )
    return register.standing_ids()


def _deferrals(rows: object, planned: set[str]) -> dict[str, str]:
    """Candidates the execution left alone *with* a recorded reason."""
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        _fail("INPUT_INVALID", "execution.not_executed must be a sequence of rows")
    deferred: dict[str, str] = {}
    for index, row in enumerate(rows):  # type: ignore[arg-type]
        record = _require_mapping(row, f"execution.not_executed[{index}]")
        candidate = _require_id(
            record.get("candidate_id"), f"execution.not_executed[{index}].candidate_id"
        )
        if candidate in deferred:
            _fail(
                "INPUT_INVALID",
                f"execution.not_executed names {candidate} twice",
                {"duplicate": candidate},
            )
        if candidate not in planned:
            _fail(
                "INPUT_INVALID",
                f"execution.not_executed names {candidate}, which was not planned",
                {"candidate_id": candidate, "planned": sorted(planned)},
            )
        # An empty reason is not a shape error: it is precisely the state
        # DELETION_INCOMPLETE exists to name, so the row is dropped here and
        # the candidate falls through to that finding.
        reason = str(record.get("reason") or "").strip()
        if reason:
            deferred[candidate] = reason
    return deferred


def verify_deletion_execution(
    *,
    plan: Mapping[str, Any],
    execution: Mapping[str, Any],
    verified_at: str,
    register: LegalHoldRegister | None = None,
    candidate_classes: Mapping[str, str] | None = None,
    receipt_id: str | None = None,
) -> dict[str, Any]:
    """Verify what a runtime did against what the plan authorised.

    Divergence is refused in both directions, and the destructive direction is
    reported first: something erased without authority cannot be undone by
    finishing the rest of the plan.
    """
    plan_record = dict(_require_mapping(plan, "plan"))
    plan_hash = verify_plan_hash(plan_record)
    outcomes = _planned_outcomes(plan_record)
    with _upstream("the plan being executed"):
        require_executable_forget(plan_record)
    holds_checked: tuple[str, ...] = ()
    if register is not None:
        holds_checked = require_forget_permitted(
            plan=plan_record, register=register, candidate_classes=candidate_classes
        )

    report = _require_mapping(execution, "execution")
    executed_at = _require_id(report.get("executed_at"), "execution.executed_at")
    done_erased = _unique_ids(report.get("erased") or (), "execution.erased")
    done_tombstoned = _unique_ids(
        report.get("tombstoned") or (), "execution.tombstoned"
    )
    planned_erased = set(outcomes["erased"])
    planned_tombstoned = set(outcomes["tombstoned"])
    planned = planned_erased | planned_tombstoned
    both = sorted(set(done_erased) & set(done_tombstoned))
    if both:
        _fail(
            "INPUT_INVALID",
            "the execution reports these candidates under two outcomes",
            {"overlap": both},
        )
    deferred = _deferrals(report.get("not_executed") or (), planned)
    acted = set(done_erased) | set(done_tombstoned)
    contradicted = sorted(acted & set(deferred))
    if contradicted:
        _fail(
            "INPUT_INVALID",
            "the execution both acted on and deferred these candidates",
            {"contradicted": contradicted},
        )

    unplanned = sorted(
        (set(done_erased) - planned_erased)
        | (set(done_tombstoned) - planned_tombstoned)
    )
    if unplanned:
        _fail(
            "DELETION_UNPLANNED",
            "the execution removed memory the plan did not authorise",
            {
                "erased_without_plan": sorted(set(done_erased) - planned_erased),
                "plan_id": str(plan_record.get("plan_id") or ""),
                "tombstoned_without_plan": sorted(
                    set(done_tombstoned) - planned_tombstoned
                ),
                "unplanned": unplanned,
            },
        )
    incomplete = sorted(planned - acted - set(deferred))
    if incomplete:
        _fail(
            "DELETION_INCOMPLETE",
            "the plan authorised outcomes the execution neither carried out "
            "nor gave a reason for leaving",
            {
                "incomplete": incomplete,
                "plan_id": str(plan_record.get("plan_id") or ""),
                "unfinished_erasures": sorted(set(incomplete) & planned_erased),
                "unfinished_tombstones": sorted(set(incomplete) & planned_tombstoned),
            },
        )
    if len(acted) + len(deferred) != len(planned):
        _fail(
            "EXECUTION_COUNTS_UNRECONCILED",
            "the executed, deferred and planned counts do not add up",
            {
                "acted": len(acted),
                "deferred": len(deferred),
                "planned": len(planned),
            },
        )

    receipt: dict[str, Any] = {
        "counts": {
            "deferred": len(deferred),
            "erased": len(done_erased),
            "planned": len(planned),
            "tombstoned": len(done_tombstoned),
        },
        "deferred": [
            {"candidate_id": key, "reason": value}
            for key, value in sorted(deferred.items())
        ],
        "erased": sorted(done_erased),
        "executed_at": executed_at,
        "hold_ids_checked": list(holds_checked),
        "plan_hash": plan_hash,
        "plan_id": str(plan_record.get("plan_id") or ""),
        "receipt_id": receipt_id or new_id("EDX"),
        "tombstoned": sorted(done_tombstoned),
        "verified_at": str(verified_at),
    }
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    return receipt


def _finding(code: str, **fields: Any) -> dict[str, Any]:
    return {"code": code, "reason": FINDING_CODES[code], **fields}


def _sweep_history(
    plans: Sequence[Mapping[str, Any]], findings: list[dict[str, Any]]
) -> tuple[set[str], dict[str, dict[str, Any]], list[str]]:
    """What the executed plans, taken together, claim to have done."""
    erased: set[str] = set()
    tombstones: dict[str, dict[str, Any]] = {}
    hashes: list[str] = []
    for index, given in enumerate(plans):
        plan = dict(_require_mapping(given, f"executed_plans[{index}]"))
        declared = str(plan.get("plan_hash") or "")
        derived = hash_excluding(plan, "plan_hash")
        hashes.append(declared)
        if declared != derived:
            findings.append(
                _finding(
                    "PLAN_HASH_MISMATCH",
                    declared=declared,
                    derived=derived,
                    plan_id=str(plan.get("plan_id") or ""),
                )
            )
        outcomes = _planned_outcomes(plan)
        erased.update(outcomes["erased"])
        for row in plan["tombstoned"]:
            record = dict(_require_mapping(row, "plan.tombstoned[]"))
            candidate = _require_id(record.get("candidate_id"), "candidate_id")
            existing = tombstones.get(candidate)
            if existing is not None and existing != record:
                _fail(
                    "INPUT_INVALID",
                    f"two plans tombstone {candidate} with different facts",
                    {"candidate_id": candidate},
                )
            tombstones[candidate] = record
    return erased, tombstones, hashes


def _tombstone_findings(
    planned: Mapping[str, Mapping[str, Any]], retained: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Every protected tombstone must still carry the facts it was made of."""
    kept: dict[str, Mapping[str, Any]] = {}
    for index, given in enumerate(retained):
        record = _require_mapping(given, f"tombstones[{index}]")
        candidate = _require_id(
            record.get("candidate_id"), f"tombstones[{index}].candidate_id"
        )
        if candidate in kept:
            _fail(
                "INPUT_INVALID",
                f"the tombstone ledger holds {candidate} twice",
                {"candidate_id": candidate},
            )
        kept[candidate] = record
    findings: list[dict[str, Any]] = []
    for candidate in sorted(planned):
        row = planned[candidate]
        if str(row.get("entry_class") or "") not in PROTECTED_ENTRY_CLASSES:
            continue
        surviving = kept.get(candidate)
        if surviving is None:
            findings.append(
                _finding(
                    "TOMBSTONE_FACTS_LOST",
                    candidate_id=candidate,
                    lost_fields=list(TOMBSTONE_FACT_FIELDS),
                )
            )
            continue
        lost = sorted(
            field
            for field in TOMBSTONE_FACT_FIELDS
            if surviving.get(field) != row.get(field)
        )
        if lost:
            findings.append(
                _finding(
                    "TOMBSTONE_FACTS_LOST", candidate_id=candidate, lost_fields=lost
                )
            )
    return findings


def audit_retention_sweep(
    *,
    entries: Sequence[Mapping[str, Any]],
    lineage_records: Sequence[Mapping[str, Any]],
    executed_plans: Sequence[Mapping[str, Any]],
    tombstones: Sequence[Mapping[str, Any]],
    audited_at: str,
    audit_id: str | None = None,
) -> dict[str, Any]:
    """Rebuild the memory a series of executed plans left behind.

    The report is produced whole rather than raising at the first problem: an
    operator fixing a sweep needs to see everything that broke, not the first
    thing that broke.  `require_clean_sweep` is what turns it into a refusal.
    """
    findings: list[dict[str, Any]] = []
    erased, planned_tombstones, plan_hashes = _sweep_history(executed_plans, findings)

    # L05's own construction is the checker.  If the survivors cannot be
    # assembled into a walkable ancestry, that failure is the finding.
    reconstructed = True
    try:
        memory = LineageMemory(lineage_records)
        surviving_lineage = set(memory.candidates())
    except EvolutionMemoryError as error:
        reconstructed = False
        surviving_lineage = set()
        findings.append(
            _finding(
                "RETENTION_SWEEP_BROKEN",
                **_upstream_finding(error, "the surviving lineage memory"),
            )
        )

    held_entries: set[str] = set()
    for index, given in enumerate(entries):
        entry = _require_mapping(given, f"entries[{index}]")
        held_entries.add(
            _require_id(entry.get("candidate_id"), f"entries[{index}].candidate_id")
        )
    surviving = surviving_lineage | held_entries
    for candidate in sorted(erased & surviving):
        findings.append(
            _finding(
                "ERASED_MEMORY_RETAINED",
                candidate_id=candidate,
                in_archive=candidate in held_entries,
                in_lineage=candidate in surviving_lineage,
            )
        )
    if reconstructed:
        for candidate in memory.candidates():
            for ancestor in memory.ancestors_of(candidate):
                if ancestor in erased:
                    findings.append(
                        _finding(
                            "ERASED_ANCESTOR_REFERENCED",
                            ancestor_id=ancestor,
                            candidate_id=candidate,
                        )
                    )
    findings.extend(_tombstone_findings(planned_tombstones, tombstones))

    protected = sorted(
        candidate
        for candidate, row in planned_tombstones.items()
        if str(row.get("entry_class") or "") in PROTECTED_ENTRY_CLASSES
    )
    report: dict[str, Any] = {
        "audit_id": audit_id or new_id("ERS"),
        "audited_at": str(audited_at),
        "counts": {
            "erased": len(erased),
            "findings": len(findings),
            "protected_tombstones": len(protected),
            "surviving": len(surviving),
            "tombstoned": len(planned_tombstones),
        },
        "erased_candidates": sorted(erased),
        "findings": sorted(
            findings,
            key=lambda row: (
                str(row["code"]),
                str(row.get("candidate_id") or ""),
                str(row.get("ancestor_id") or ""),
            ),
        ),
        "lineage_reconstructed": reconstructed,
        "plan_hashes": sorted(plan_hashes),
        "protected_tombstones": protected,
        "surviving_candidates": sorted(surviving),
    }
    report["audit_hash"] = hash_excluding(report, "audit_hash")
    return report


def require_clean_sweep(report: Mapping[str, Any]) -> None:
    """Raise unless the retention sweep audit found nothing."""
    findings = list(_require_mapping(report, "report").get("findings") or [])
    if findings:
        first = _require_mapping(findings[0], "report.findings[0]")
        _fail(
            str(first["code"]),
            f"the retention sweep left {len(findings)} unresolved finding(s)",
            {"audit_id": str(report.get("audit_id") or ""), "findings": findings},
        )
