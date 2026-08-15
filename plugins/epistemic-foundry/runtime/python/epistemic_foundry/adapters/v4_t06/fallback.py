"""Declared fallback and the terminal domain-neutral core (T06).

EF4-I63 makes the external backend optional, and `shinka_adapter.isolation`
already answers "can the Foundry run without it?" with an unconditional yes.
This module is what that yes costs: if the backend can be absent, then every
path that would have used it has to end somewhere that is always there, and
the step from one to the other has to be visible afterwards.

* *The chain is declared before it is needed.*  A fallback discovered at the
  moment of failure is an improvisation; a declared chain can be inspected,
  and every member of it is individually qualified through its own T06
  qualification chain rather than inheriting the primary's standing.
* *The terminal member is the core, and it is always available.*  It runs no
  backend and declares no capabilities, so reaching it can never be a refusal
  and can never be a widening.  A chain that does not end there could run out
  of members, which would turn "the backend is optional" back into a claim
  nobody can execute.
* *Degrading is recorded, never inferred.*  Each step names the member it left
  and the standing and refusal code it left on.  `assert_fallback_recorded`
  then checks a routing record against its own chain, because a record that
  says it served from the third member while claiming no step ever happened is
  the shape a silent downgrade takes.
* *A fallback may only ever narrow.*  A substitute holding a capability the
  primary did not hold — network, an authority, a wider sandbox — is refused
  outright rather than selected, at declaration against the primary and at
  routing against what the request actually asked for.

The core still serves; what it cannot do is recorded as withheld rather than
quietly dropped.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..v4_t05 import assert_hash_rederives
from ..v4_t05.findings import (
    require_identifier,
    require_identifiers,
    require_mapping,
    seal,
)
from .findings import _fail
from .qualification_lifecycle import (
    STANDING_SERVING,
    standing,
    usable_statuses,
    verified_chain,
)

#: The terminal member every declared chain ends in: the Foundry itself, with
#: no external backend behind it.
NATIVE_CORE_MEMBER_ID = "foundry-native-core"

#: The refusal a member is skipped under.  Named here so a routing record and
#: the exception a direct call would have raised carry the same code.
FALLBACK_TRIGGER_CODE = "QUALIFICATION_NOT_SERVING"

#: The fields a declared member carries.
MEMBER_FIELDS: tuple[str, ...] = (
    "backend_manifest_id",
    "capabilities",
    "member_id",
    "qualification_chain",
    "runs_backend",
)


def native_core_member(*, member_id: str = NATIVE_CORE_MEMBER_ID) -> dict[str, Any]:
    """The domain-neutral core as a chain member.

    Its capability set is empty by construction rather than by argument.  A
    core that could be declared with capabilities would be able to widen the
    chain it terminates, and the one member that must always be safe to reach
    would become the one member worth attacking.
    """
    return {
        "backend_manifest_id": None,
        "capabilities": [],
        "member_id": require_identifier(member_id, "member_id"),
        "qualification_chain": None,
        "runs_backend": False,
    }


def backend_member(
    *,
    member_id: str,
    chain: Mapping[str, Any],
    capabilities: Sequence[str],
) -> dict[str, Any]:
    """A chain member served by an externally qualified backend."""
    verified = verified_chain(chain)
    head = verified["records"][-1]
    if head["status"] not in usable_statuses():
        _fail(
            "FALLBACK_MEMBER_UNQUALIFIED",
            "a chain member's verdict never permitted serving",
            {
                "member_id": member_id,
                "status": head["status"],
                "usable": list(usable_statuses()),
            },
        )
    return {
        "backend_manifest_id": verified["backend_manifest_id"],
        "capabilities": sorted(set(require_identifiers(capabilities, "capabilities"))),
        "member_id": require_identifier(member_id, "member_id"),
        "qualification_chain": verified,
        "runs_backend": True,
    }


def _read_member(entry: object, position: int) -> dict[str, Any]:
    member = dict(require_mapping(entry, f"members[{position}]"))
    missing = [field for field in MEMBER_FIELDS if field not in member]
    if missing:
        _fail(
            "FALLBACK_CHAIN_MALFORMED",
            f"members[{position}] is missing fields a chain member carries",
            {"missing": missing, "position": position},
        )
    member["capabilities"] = list(
        require_identifiers(member["capabilities"], f"members[{position}].capabilities")
    )
    member["member_id"] = require_identifier(
        member["member_id"], f"members[{position}].member_id"
    )
    if member["runs_backend"] is True:
        chain = verified_chain(member["qualification_chain"])
        member["backend_manifest_id"] = require_identifier(
            member["backend_manifest_id"],
            f"members[{position}].backend_manifest_id",
        )
        if member["backend_manifest_id"] != chain["backend_manifest_id"]:
            _fail(
                "BACKEND_IDENTITY_MISMATCH",
                f"members[{position}] describes another backend",
                {
                    "backend_manifest_id": member["backend_manifest_id"],
                    "position": position,
                },
            )
        head = chain["records"][-1]
        if head["status"] not in usable_statuses():
            _fail(
                "FALLBACK_MEMBER_UNQUALIFIED",
                f"members[{position}] holds a verdict that never permitted serving",
                {"member_id": member["member_id"], "status": head["status"]},
            )
        member["qualification_chain"] = chain
    elif member["runs_backend"] is False:
        if member["qualification_chain"] is not None:
            _fail(
                "FALLBACK_CHAIN_MALFORMED",
                f"members[{position}] runs no backend but carries a qualification",
                {"member_id": member["member_id"], "position": position},
            )
        if member["capabilities"]:
            _fail(
                "FALLBACK_CAPABILITY_WIDENED",
                f"members[{position}] is the core and may declare no capability",
                {"capabilities": member["capabilities"], "position": position},
            )
    else:
        _fail(
            "FALLBACK_CHAIN_MALFORMED",
            f"members[{position}] does not say whether it runs a backend",
            {"position": position, "runs_backend": member["runs_backend"]},
        )
    return member


def declare_fallback_chain(
    *, chain_id: str, members: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Declare an ordered fallback path ending in the domain-neutral core.

    The whole chain is refused rather than trimmed when a member is wrong.  A
    chain that quietly dropped its unqualified member would still report
    success while the operator believed that member was a live fallback.
    """
    if isinstance(members, (str, bytes)) or not isinstance(members, (list, tuple)):
        _fail(
            "FALLBACK_CHAIN_MALFORMED",
            "members must be an ordered array",
            {"chain_id": chain_id},
        )
    declared = [_read_member(entry, position) for position, entry in enumerate(members)]
    if not declared:
        _fail(
            "FALLBACK_CHAIN_MALFORMED",
            "a fallback chain must declare at least the core",
            {"chain_id": chain_id},
        )
    identifiers = [member["member_id"] for member in declared]
    repeated = sorted({name for name in identifiers if identifiers.count(name) > 1})
    if repeated:
        _fail(
            "FALLBACK_CHAIN_MALFORMED",
            "a member may appear in the chain only once",
            {"repeated": repeated},
        )
    terminal = [
        position
        for position, member in enumerate(declared)
        if member["runs_backend"] is False
    ]
    if terminal != [len(declared) - 1]:
        _fail(
            "FALLBACK_CHAIN_MALFORMED",
            "the chain must end in the core and hold no other coreless member",
            {"core_positions": terminal, "length": len(declared)},
        )
    primary = declared[0]
    allowed = set(primary["capabilities"])
    widened = {
        member["member_id"]: sorted(set(member["capabilities"]) - allowed)
        for member in declared[1:]
        if set(member["capabilities"]) - allowed
    }
    if widened:
        _fail(
            "FALLBACK_CAPABILITY_WIDENED",
            "a fallback member holds capabilities the primary does not",
            {"gained": widened, "primary_capabilities": sorted(allowed)},
        )
    return seal(
        {
            "chain_id": require_identifier(chain_id, "chain_id"),
            "length": len(declared),
            "members": declared,
            "primary_capabilities": sorted(allowed),
            "primary_member_id": primary["member_id"],
            "terminal_member_id": declared[-1]["member_id"],
        },
        "chain_hash",
    )


def _declared_chain(fallback_chain: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(require_mapping(fallback_chain, "fallback_chain"))
    assert_hash_rederives(value, "chain_hash", "fallback_chain")
    members = value.get("members")
    if not isinstance(members, list) or not members:
        _fail(
            "FALLBACK_CHAIN_MALFORMED",
            "the declared chain holds no members",
            {"chain_id": value.get("chain_id")},
        )
    rebuilt = declare_fallback_chain(
        chain_id=require_identifier(value.get("chain_id"), "chain_id"),
        members=members,
    )
    if rebuilt != value:
        _fail(
            "FALLBACK_CHAIN_MALFORMED",
            "the supplied fallback chain is not the exact canonical declaration",
            {
                "chain_id": value.get("chain_id"),
                "recorded_chain_hash": value.get("chain_hash"),
                "rebuilt_chain_hash": rebuilt.get("chain_hash"),
            },
        )
    return rebuilt


def route_request(
    *,
    request_id: str,
    fallback_chain: Mapping[str, Any],
    requested_capabilities: Sequence[str],
    as_of: str,
) -> dict[str, Any]:
    """Route one request along the declared chain and record every step down.

    A member is skipped only for a standing reason — expired, revoked,
    deactivated, replaced, or a verdict that never permitted serving — and the
    reason is written into the record before the next member is tried.  A
    member that would widen the request's capabilities is not skipped: it is
    refused, because silently passing over a widening would leave the caller
    served by something further down the chain with no sign that the chain
    itself was misdeclared.
    """
    declared = _declared_chain(fallback_chain)
    wanted = set(require_identifiers(requested_capabilities, "requested_capabilities"))
    identifier = require_identifier(request_id, "request_id")
    moment = require_identifier(as_of, "as_of")

    events: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    for member in declared["members"]:
        gained = sorted(set(member["capabilities"]) - wanted)
        if gained:
            _fail(
                "FALLBACK_CAPABILITY_WIDENED",
                "a chain member holds capabilities the request did not ask for",
                {
                    "gained": gained,
                    "member_id": member["member_id"],
                    "requested_capabilities": sorted(wanted),
                },
            )
        if member["runs_backend"] is False:
            selected = member
            break
        found = standing(chain=member["qualification_chain"], as_of=moment)
        if found == STANDING_SERVING:
            selected = member
            break
        events.append(
            {
                "from_member_id": member["member_id"],
                "trigger_refusal_code": FALLBACK_TRIGGER_CODE,
                "trigger_standing": found,
                "trigger_status": member["qualification_chain"]["records"][-1][
                    "status"
                ],
            }
        )
    if selected is None:  # pragma: no cover - the terminal core always selects
        _fail(
            "FALLBACK_CHAIN_MALFORMED",
            "the chain ran out of members without reaching the core",
            {"chain_id": declared["chain_id"]},
        )
    chosen: dict[str, Any] = selected  # type: ignore[assignment]
    for position, event in enumerate(events):
        event["to_member_id"] = (
            events[position + 1]["from_member_id"]
            if position + 1 < len(events)
            else chosen["member_id"]
        )
    return seal(
        {
            "as_of": moment,
            "capabilities_withheld": sorted(wanted - set(chosen["capabilities"])),
            "fallback_events": events,
            "fallback_chain_hash": declared["chain_hash"],
            "fallback_chain_id": declared["chain_id"],
            "primary_member_id": declared["primary_member_id"],
            "request_id": identifier,
            "requested_capabilities": sorted(wanted),
            "selected_backend_manifest_id": chosen["backend_manifest_id"],
            "selected_capabilities": list(chosen["capabilities"]),
            "selected_member_id": chosen["member_id"],
            "served_by_backend": chosen["runs_backend"],
        },
        "routing_hash",
    )


def assert_fallback_recorded(
    *, audit_id: str, routing: Mapping[str, Any], fallback_chain: Mapping[str, Any]
) -> dict[str, Any]:
    """Check a routing record against its chain: every step down is present.

    Read as an audit rather than as a replay.  It does not re-decide which
    member should have served — standings move — it checks that the record's
    own account of how it reached its member is complete and in order.
    """
    declared = _declared_chain(fallback_chain)
    record = dict(require_mapping(routing, "routing"))
    assert_hash_rederives(record, "routing_hash", "routing")
    if record.get("fallback_chain_hash") != declared["chain_hash"]:
        _fail(
            "FALLBACK_UNRECORDED",
            "the routing record was not produced against this chain",
            {
                "chain_hash": declared["chain_hash"],
                "recorded": record.get("fallback_chain_hash"),
            },
        )
    order = [member["member_id"] for member in declared["members"]]
    selected = require_identifier(
        record.get("selected_member_id"), "selected_member_id"
    )
    if selected not in order:
        _fail(
            "FALLBACK_UNRECORDED",
            "the routing record names a member the chain does not declare",
            {"declared": order, "selected_member_id": selected},
        )
    skipped = order[: order.index(selected)]
    supplied = record.get("fallback_events")
    if not isinstance(supplied, list):
        _fail(
            "FALLBACK_UNRECORDED",
            "the routing record carries no fallback event list",
            {"request_id": record.get("request_id")},
        )
    events = [
        dict(require_mapping(entry, f"fallback_events[{position}]"))
        for position, entry in enumerate(supplied)  # type: ignore[arg-type]
    ]
    if [event.get("from_member_id") for event in events] != skipped:
        _fail(
            "FALLBACK_UNRECORDED",
            "the recorded steps do not account for the members that were passed",
            {
                "recorded": [event.get("from_member_id") for event in events],
                "skipped": skipped,
            },
        )
    for position, entry in enumerate(events):
        require_identifier(
            entry.get("trigger_standing"),
            f"fallback_events[{position}].trigger_standing",
        )
        require_identifier(
            entry.get("trigger_refusal_code"),
            f"fallback_events[{position}].trigger_refusal_code",
        )
        expected = skipped[position + 1] if position + 1 < len(skipped) else selected
        if entry.get("to_member_id") != expected:
            _fail(
                "FALLBACK_UNRECORDED",
                f"fallback_events[{position}] does not name the member it moved to",
                {"expected": expected, "named": entry.get("to_member_id")},
            )
    return seal(
        {
            "audit_id": require_identifier(audit_id, "audit_id"),
            "fallback_chain_id": declared["chain_id"],
            "recorded_steps": len(events),
            "request_id": require_identifier(record.get("request_id"), "request_id"),
            "routing_hash": record["routing_hash"],
            "selected_member_id": selected,
            "skipped_member_ids": list(skipped),
        },
        "audit_hash",
    )
