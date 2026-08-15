"""Evolution memory: lineage, negative-result retention, forget and export.

The archive decides what may be *evicted for capacity* and the memory policy
decides what may be *recalled*.  Neither answers the question this module
exists for: when something must actually be forgotten — a regulated erasure, a
withdrawn consent, a purged workspace — what survives, and what may an export
carry out of the workspace?

Three rules do the work.  Negative knowledge is never erased for capacity: a
null, counterexample, failed replication, minority lineage or unsafe result may
be reduced to a tombstone that keeps the class, the reason and the hash, but
the fact that it existed does not disappear.  A forget may not orphan a
lineage: erasing a candidate that later candidates descend from would leave a
memory that cannot walk its own ancestry, so that candidate is tombstoned
instead.  And an export may not be survivorship-biased: carrying the winners
out while leaving the negative results behind produces a record that reads
better than the search actually was.

Nothing here re-implements what it composes.  The entry-class vocabulary and
its protected/evictable partition come from the archive module and the
canonical schema, and export scope is delegated to the memory policy's own
enforcement point.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...contracts import default_registry, validate_artifact
from ...domain.hashing import hash_excluding
from ...domain.ids import new_id
from ...epistemic_species_archive.archive import (
    EVICTABLE_ENTRY_CLASSES,
    PROTECTED_ENTRY_CLASSES,
)
from ..policy import MemoryScopeViolation, require_recall_permitted

#: Every way this module refuses, and why that refusal exists.
FINDING_CODES: dict[str, str] = {
    "CANDIDATE_UNKNOWN": (
        "a forget request named a candidate the archive entries do not hold, so "
        "the request cannot be planned against real memory"
    ),
    "ENTRY_CLASS_UNKNOWN": (
        "an archive entry carries a class outside the canonical vocabulary, and "
        "an unclassified entry cannot be protected or released"
    ),
    "EXPORT_SCOPE_DENIED": (
        "the memory policy refused the export scope; the policy is the "
        "enforcement point and an export cannot route around it"
    ),
    "EXPORT_SURVIVORSHIP_BIASED": (
        "the export carries fit results while dropping the negative knowledge "
        "beside them, which reads better than the search actually was"
    ),
    "FORGET_AUTHORITY_MISSING": (
        "a forget request arrived without a declared ground and approver, and "
        "erasure without recorded authority cannot be audited afterwards"
    ),
    "INPUT_INVALID": (
        "an input is not the shape this module requires, and continuing would "
        "record a plan derived from something it never validated"
    ),
    "LINEAGE_BROKEN": (
        "the lineage memory cannot be walked: a record names an ancestor the "
        "memory does not hold, or the ancestry closes into a cycle"
    ),
    "LINEAGE_ORPHANED": (
        "erasing this candidate would leave descendants whose ancestry cannot "
        "be walked, so the entry is tombstoned rather than removed"
    ),
    "PROTECTED_MEMORY_ERASED": (
        "capacity pressure cannot erase negative, null, unsafe or minority "
        "memory; that knowledge was already paid for once"
    ),
    "VOCABULARY_DRIFT": (
        "the protected and evictable partition no longer covers the canonical "
        "entry classes exactly, so a class would be silently unhandled"
    ),
}

#: Grounds a forget may be requested on.  This module owns the vocabulary, so
#: it is data rather than a literal scattered across the checks.  `CAPACITY` is
#: the fitness-driven ground, and it is the one that may never erase protected
#: memory; the others are external obligations that outrank retention.
FORGET_GROUNDS: tuple[str, ...] = (
    "capacity_pressure",
    "consent_withdrawal",
    "regulated_erasure",
    "workspace_purge",
)
CAPACITY_GROUND = FORGET_GROUNDS[0]

#: Outcomes a planned forget can have for one candidate.
FORGET_OUTCOMES: tuple[str, ...] = ("erased", "refused", "tombstoned")


class EvolutionMemoryError(ValueError):
    """A retention, forget or export request would damage the record."""

    def __init__(
        self, code: str, message: str, context: Mapping[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def _fail(code: str, message: str, context: Mapping[str, Any] | None = None) -> None:
    if code not in FINDING_CODES:
        raise EvolutionMemoryError(
            "INPUT_INVALID", f"undeclared finding code {code}", {"code": code}
        )
    raise EvolutionMemoryError(code, message, context)


def entry_class_vocabulary() -> tuple[str, ...]:
    """The archive entry classes, read from the schema that declares them.

    The partition is checked on every use rather than trusted: a class added to
    the schema but not sorted into protected or evictable would otherwise be
    handled by whichever branch happened to catch it.
    """
    document = default_registry().document("epistemic-archive-entry")
    declared = tuple(document["properties"]["entry_class"]["enum"])
    overlap = PROTECTED_ENTRY_CLASSES & EVICTABLE_ENTRY_CLASSES
    partition = PROTECTED_ENTRY_CLASSES | EVICTABLE_ENTRY_CLASSES
    if overlap or set(declared) != partition:
        _fail(
            "VOCABULARY_DRIFT",
            "the archive class partition does not cover the canonical vocabulary",
            {
                "declared": list(declared),
                "evictable": sorted(EVICTABLE_ENTRY_CLASSES),
                "overlap": sorted(overlap),
                "protected": sorted(PROTECTED_ENTRY_CLASSES),
            },
        )
    return declared


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INPUT_INVALID", f"{label} must be a mapping", {"label": label})
    return value  # type: ignore[return-value]


class LineageMemory:
    """The ancestry the archive entries are attached to.

    A memory that holds a candidate but not the parent it names cannot answer
    "what did this descend from", so an incomplete ancestry is refused at
    construction rather than discovered during a forget.
    """

    def __init__(self, records: Sequence[Mapping[str, Any]]) -> None:
        by_candidate: dict[str, dict[str, Any]] = {}
        for index, candidate_record in enumerate(records):
            record = dict(_require_mapping(candidate_record, f"lineage[{index}]"))
            validate_artifact("candidate-lineage", record)
            candidate_id = str(record["candidate_id"])
            if candidate_id in by_candidate:
                _fail(
                    "INPUT_INVALID",
                    f"lineage memory holds {candidate_id} twice",
                    {"candidate_id": candidate_id},
                )
            by_candidate[candidate_id] = record
        children: dict[str, set[str]] = {candidate: set() for candidate in by_candidate}
        for candidate_id, record in by_candidate.items():
            unknown = sorted(
                str(parent)
                for parent in record["parent_ids"]
                if str(parent) not in by_candidate
            )
            if unknown:
                _fail(
                    "LINEAGE_BROKEN",
                    f"{candidate_id} names ancestors the memory does not hold",
                    {"candidate_id": candidate_id, "unknown_parents": unknown},
                )
            for parent in record["parent_ids"]:
                children[str(parent)].add(candidate_id)
        self._records = by_candidate
        self._children = {key: tuple(sorted(value)) for key, value in children.items()}
        for candidate_id in by_candidate:
            # `refuse_origin` rather than a callback-identity comparison: a
            # bound method is a fresh object on every attribute access, so an
            # `is` check against `self._parents` would never fire.
            self._walk(candidate_id, self._parents, candidate_id, refuse_origin=True)

    def _parents(self, candidate_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(str(parent) for parent in self._records[candidate_id]["parent_ids"])
        )

    def _walk(
        self,
        start: str,
        step: Any,
        origin: str,
        *,
        refuse_origin: bool = False,
    ) -> tuple[str, ...]:
        seen: set[str] = set()
        frontier = list(step(start))
        while frontier:
            current = frontier.pop()
            if current == origin and refuse_origin:
                _fail(
                    "LINEAGE_BROKEN",
                    f"{origin} is its own ancestor",
                    {"candidate_id": origin},
                )
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(step(current))
        return tuple(sorted(seen))

    def candidates(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def record(self, candidate_id: str) -> Mapping[str, Any]:
        if candidate_id not in self._records:
            _fail(
                "CANDIDATE_UNKNOWN",
                f"lineage memory does not hold {candidate_id}",
                {"candidate_id": candidate_id},
            )
        return dict(self._records[candidate_id])

    def parents_of(self, candidate_id: str) -> tuple[str, ...]:
        self.record(candidate_id)
        return self._parents(candidate_id)

    def ancestors_of(self, candidate_id: str) -> tuple[str, ...]:
        self.record(candidate_id)
        return self._walk(candidate_id, self._parents, candidate_id)

    def children_of(self, candidate_id: str) -> tuple[str, ...]:
        self.record(candidate_id)
        return self._children[candidate_id]

    def descendants_of(self, candidate_id: str) -> tuple[str, ...]:
        self.record(candidate_id)
        return self._walk(candidate_id, self.children_of, candidate_id)

    def generation_of(self, candidate_id: str) -> int:
        return int(self.record(candidate_id)["generation"])


def _authority(authority: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(_require_mapping(authority, "authority"))
    ground = record.get("ground")
    approver = str(record.get("approved_by") or "").strip()
    identifier = str(record.get("authority_id") or "").strip()
    if ground not in FORGET_GROUNDS or not approver or not identifier:
        _fail(
            "FORGET_AUTHORITY_MISSING",
            "a forget needs an authority id, a declared ground and an approver",
            {"declared_grounds": list(FORGET_GROUNDS), "given": record},
        )
    return {"approved_by": approver, "authority_id": identifier, "ground": str(ground)}


def _entry_index(entries: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    vocabulary = set(entry_class_vocabulary())
    index: dict[str, dict[str, Any]] = {}
    for position, candidate_entry in enumerate(entries):
        entry = dict(_require_mapping(candidate_entry, f"entries[{position}]"))
        validate_artifact("epistemic-archive-entry", entry)
        entry_class = str(entry["entry_class"])
        if entry_class not in vocabulary:
            _fail(
                "ENTRY_CLASS_UNKNOWN",
                f"entry {entry['archive_entry_id']} carries class {entry_class}",
                {"entry_class": entry_class, "vocabulary": sorted(vocabulary)},
            )
        candidate_id = str(entry["candidate_id"])
        if candidate_id in index:
            _fail(
                "INPUT_INVALID",
                f"two archive entries claim candidate {candidate_id}",
                {"candidate_id": candidate_id},
            )
        index[candidate_id] = entry
    return index


def _require_lineage_holds(
    index: Mapping[str, Mapping[str, Any]], lineage: LineageMemory
) -> None:
    """An archive entry whose candidate has no ancestry is a broken memory."""
    held = set(lineage.candidates())
    missing = sorted(set(index) - held)
    if missing:
        _fail(
            "LINEAGE_BROKEN",
            "archive entries name candidates the lineage memory does not hold",
            {"missing_lineage": missing},
        )
    for candidate_id, entry in index.items():
        record = lineage.record(candidate_id)
        if entry["lineage_id"] != record["lineage_id"]:
            _fail(
                "LINEAGE_BROKEN",
                f"archive entry and lineage memory disagree for {candidate_id}",
                {
                    "archive_lineage_id": entry["lineage_id"],
                    "candidate_id": candidate_id,
                    "record_lineage_id": record["lineage_id"],
                },
            )


def plan_forget(
    *,
    entries: Sequence[Mapping[str, Any]],
    lineage: LineageMemory,
    candidate_ids: Sequence[str],
    authority: Mapping[str, Any],
    requested_at: str,
    plan_id: str | None = None,
) -> dict[str, Any]:
    """Decide, for each named candidate, what a forget may actually do.

    The plan is produced whole: a caller sees every refusal at once rather than
    fixing them one at a time and re-running against a memory that has already
    been partly erased.
    """
    granted = _authority(authority)
    index = _entry_index(entries)
    _require_lineage_holds(index, lineage)
    if isinstance(candidate_ids, (str, bytes, bytearray, Mapping)) or not isinstance(
        candidate_ids, Sequence
    ):
        _fail(
            "INPUT_INVALID",
            "candidate_ids must be a sequence of identifiers",
            {"submitted_type": type(candidate_ids).__name__},
        )
    requested_items: list[str] = []
    for position, candidate_id in enumerate(candidate_ids):
        if not isinstance(candidate_id, str) or not candidate_id:
            _fail(
                "INPUT_INVALID",
                f"candidate_ids[{position}] must be a non-empty string",
                {"position": position},
            )
        requested_items.append(candidate_id)
    requested = list(dict.fromkeys(requested_items))
    if not requested:
        _fail("INPUT_INVALID", "a forget must name at least one candidate")

    tombstoned: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    erasure_candidates: list[str] = []
    for candidate_id in requested:
        entry = index.get(candidate_id)
        if entry is None:
            refusals.append(
                {
                    "candidate_id": candidate_id,
                    "code": "CANDIDATE_UNKNOWN",
                    "reason": FINDING_CODES["CANDIDATE_UNKNOWN"],
                }
            )
            continue
        entry_class = str(entry["entry_class"])
        if entry_class in PROTECTED_ENTRY_CLASSES:
            if granted["ground"] == CAPACITY_GROUND:
                refusals.append(
                    {
                        "candidate_id": candidate_id,
                        "code": "PROTECTED_MEMORY_ERASED",
                        "entry_class": entry_class,
                        "reason": FINDING_CODES["PROTECTED_MEMORY_ERASED"],
                    }
                )
                continue
            tombstoned.append(_tombstone(entry, lineage, "PROTECTED_MEMORY_ERASED"))
            continue
        erasure_candidates.append(candidate_id)

    # Erasure removes the lineage record too, and a tombstone keeps its own
    # record whose ancestry must stay walkable.  So a candidate may be erased
    # only if every descendant is itself erased — not merely requested, since a
    # requested descendant can end up refused or tombstoned.  Removing one
    # candidate can only strand more ancestors, so this iterates to fixpoint.
    erasable = set(erasure_candidates)
    while True:
        stranded = {
            candidate_id
            for candidate_id in erasable
            if any(
                descendant not in erasable
                for descendant in lineage.descendants_of(candidate_id)
            )
        }
        if not stranded:
            break
        erasable -= stranded
    for candidate_id in erasure_candidates:
        if candidate_id in erasable:
            continue
        tombstoned.append(
            {
                **_tombstone(index[candidate_id], lineage, "LINEAGE_ORPHANED"),
                "retained_descendants": [
                    descendant
                    for descendant in lineage.descendants_of(candidate_id)
                    if descendant not in erasable
                ],
            }
        )
    erased = sorted(erasable)

    plan: dict[str, Any] = {
        "authority": granted,
        "counts": {
            "erased": len(erased),
            "refused": len(refusals),
            "requested": len(requested),
            "tombstoned": len(tombstoned),
        },
        "erased": sorted(erased),
        "plan_id": plan_id or new_id("EFP"),
        "refusals": sorted(refusals, key=lambda row: row["candidate_id"]),
        "requested": requested,
        "requested_at": requested_at,
        "tombstoned": sorted(tombstoned, key=lambda row: row["candidate_id"]),
    }
    plan["plan_hash"] = hash_excluding(plan, "plan_hash")
    return plan


def _tombstone(
    entry: Mapping[str, Any], lineage: LineageMemory, code: str
) -> dict[str, Any]:
    """What is kept when the payload goes: the fact, the reason and the hash."""
    return {
        "archive_entry_id": str(entry["archive_entry_id"]),
        "artifact_hash": str(entry["artifact_hash"]),
        "candidate_id": str(entry["candidate_id"]),
        "code": code,
        "entry_class": str(entry["entry_class"]),
        "generation": lineage.generation_of(str(entry["candidate_id"])),
        "lineage_id": str(entry["lineage_id"]),
        "reason": FINDING_CODES[code],
        "retention_reason": str(entry["retention_reason"]),
    }


def require_executable_forget(plan: Mapping[str, Any]) -> None:
    """Raise unless every candidate in the plan can be acted on."""
    refusals = list(_require_mapping(plan, "plan").get("refusals") or [])
    if refusals:
        first = refusals[0]
        _fail(
            str(first["code"]),
            f"{first['candidate_id']} cannot be forgotten as requested",
            {"refusals": refusals},
        )


def build_export_manifest(
    *,
    entries: Sequence[Mapping[str, Any]],
    lineage: LineageMemory,
    policy: Mapping[str, Any],
    workspace_id: str,
    memory_classes: Sequence[str],
    purpose: str,
    consent_id: str | None,
    exported_at: str,
    included_classes: Sequence[str] | None = None,
    target_workspace_id: str | None = None,
    age_days: int = 0,
    manifest_id: str | None = None,
) -> dict[str, Any]:
    """Describe an export of evolution memory, or refuse to describe one.

    Scope is delegated to the memory policy's own enforcement point, so an
    export cannot honour classes while ignoring consent or workspace. What this
    adds is the shape of the record: an export that keeps the fit results and
    drops the negative ones beside them is refused, and every ancestor the
    export does not carry is named rather than left implicit.
    """
    index = _entry_index(entries)
    _require_lineage_holds(index, lineage)
    try:
        require_recall_permitted(
            policy,
            workspace_id=workspace_id,
            requested_classes=list(memory_classes),
            purpose=purpose,
            consent_id=consent_id,
            age_days=age_days,
            target_workspace_id=target_workspace_id,
        )
    except MemoryScopeViolation as error:
        _fail(
            "EXPORT_SCOPE_DENIED",
            str(error),
            {"policy_id": policy.get("policy_id"), "workspace_id": workspace_id},
        )

    # The policy's class rules carry each class's external-sync disposition and
    # redaction profile.  This module records them rather than interpreting
    # them: the disposition vocabulary belongs to the policy owner, and acting
    # on an ordering the schema does not declare would be guesswork.  A class
    # with no rule at all has no recorded disposition, so it is refused.
    rules = {str(rule["class"]): dict(rule) for rule in policy["class_rules"]}
    ungoverned = sorted(set(map(str, memory_classes)) - set(rules))
    if ungoverned:
        _fail(
            "EXPORT_SCOPE_DENIED",
            "the policy declares no class rule for every exported memory class",
            {"policy_id": policy.get("policy_id"), "ungoverned_classes": ungoverned},
        )

    vocabulary = entry_class_vocabulary()
    selected = (
        set(vocabulary) if included_classes is None else set(map(str, included_classes))
    )
    unknown = sorted(selected - set(vocabulary))
    if unknown:
        _fail(
            "ENTRY_CLASS_UNKNOWN",
            "the export names classes outside the canonical vocabulary",
            {"unknown": unknown, "vocabulary": list(vocabulary)},
        )
    present = {str(entry["entry_class"]) for entry in index.values()}
    dropped_protected = sorted((present & PROTECTED_ENTRY_CLASSES) - selected)
    kept_evictable = sorted((present & EVICTABLE_ENTRY_CLASSES) & selected)
    if dropped_protected and kept_evictable:
        _fail(
            "EXPORT_SURVIVORSHIP_BIASED",
            "an export that keeps results must keep the negative knowledge beside them",
            {"dropped_protected": dropped_protected, "kept_evictable": kept_evictable},
        )

    exported = sorted(
        (
            {
                "artifact_hash": str(entry["artifact_hash"]),
                "candidate_id": candidate_id,
                "entry_class": str(entry["entry_class"]),
                "lineage_id": str(entry["lineage_id"]),
                "retention_reason": str(entry["retention_reason"]),
            }
            for candidate_id, entry in index.items()
            if str(entry["entry_class"]) in selected
        ),
        key=lambda row: row["candidate_id"],
    )
    carried = {row["candidate_id"] for row in exported}
    external_ancestors = sorted(
        {
            ancestor
            for candidate_id in carried
            for ancestor in lineage.ancestors_of(candidate_id)
            if ancestor not in carried
        }
    )

    manifest: dict[str, Any] = {
        "class_rules_applied": [
            rules[memory_class]
            for memory_class in sorted(set(map(str, memory_classes)))
        ],
        "exported_at": exported_at,
        "exported_entries": exported,
        "exported_class_counts": {
            entry_class: sum(1 for row in exported if row["entry_class"] == entry_class)
            for entry_class in sorted(selected)
        },
        # Named rather than implied: an importer can tell what ancestry the
        # export does not carry instead of assuming the lineage is complete.
        "external_ancestors": external_ancestors,
        "included_classes": sorted(selected),
        "manifest_id": manifest_id or new_id("EEM"),
        "memory_classes": sorted(set(map(str, memory_classes))),
        "policy_hash": str(policy["policy_hash"]),
        "purpose": purpose,
        "source_workspace_id": str(policy["workspace_id"]),
        "target_workspace_id": target_workspace_id or workspace_id,
    }
    manifest["manifest_hash"] = hash_excluding(manifest, "manifest_hash")
    return manifest
