"""Executable candidate sandbox (EF4-I64).

Contract sources: `schemas/capability-lease.schema.json`,
`schemas/action-intent.schema.json` and `schemas/effect-receipt.schema.json`.

"Candidate code executes only under declared capabilities, resource quotas,
network policy, effect receipts and evaluator/holdout isolation."

Evolution generates code, and generated code is untrusted by construction: the
process that wrote it optimizes a score, and reading the hidden holdout or
disabling a check is often the cheapest way to raise that score. So execution is
gated on five separate conditions rather than one trust decision:

* *Declared capabilities.* Anything not leased is denied. An undeclared
  capability is not a small omission; it is the capability the candidate wanted
  without saying so.
* *Resource quotas.* Absent quotas deny rather than default. An unbounded run is
  indistinguishable from a hang and cannot be reconciled against a budget.
* *Network policy.* Egress is denied unless a lease scopes it, because a network
  path is simultaneously an exfiltration path for the holdout and an import path
  for content the evaluator never qualified.
* *Effect receipts.* Execution that produced effects with no receipt is
  `UNKNOWN`, never `SUCCEEDED`. An unreceipted effect cannot be rolled back or
  reconciled.
* *Evaluator/holdout isolation.* A candidate that can reach the evaluator bundle
  or the hidden holdout can score itself, which is the authority inversion the
  constitution forbids.

The refusal is fail-closed throughout: every unknown is denial, and
`plan_candidate_execution` returns the full blocker list so a caller fixes the
profile in one pass instead of discovering one condition per attempt.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding, sha256_of_payload
from ..domain.ids import new_id
from ..domain.time import utc_now_iso

#: Resource dimensions a candidate sandbox must bound. Absence of any one of
#: these is a denial, not a default.
REQUIRED_QUOTAS: tuple[str, ...] = (
    "wall_clock_seconds",
    "cpu_seconds",
    "memory_bytes",
    "disk_write_bytes",
    "process_count",
)

#: Capabilities that would let a candidate reach its own judge. Leasing any of
#: these to candidate code inverts the verifier firewall.
FORBIDDEN_CANDIDATE_CAPABILITIES: frozenset[str] = frozenset(
    {
        "evaluator_bundle_write",
        "evaluator_bundle_read",
        "holdout_read",
        "holdout_write",
        "gate_override",
        "promotion_write",
        "ledger_write",
        "policy_write",
    }
)

#: Network policies, ordered from most to least restrictive. `DENY_ALL` is the
#: default because an unstated policy is not a permissive one.
NETWORK_POLICIES: tuple[str, ...] = ("DENY_ALL", "ALLOWLIST", "ALLOW_ALL")


class SandboxRefused(PermissionError):
    """Candidate execution was refused by the sandbox contract."""


def build_sandbox_profile(
    *,
    profile_name: str,
    declared_capabilities: Sequence[str],
    quotas: Mapping[str, int],
    network_policy: str,
    network_allowlist: Sequence[str] = (),
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Seal a sandbox profile, refusing anything it cannot bound.

    An `ALLOWLIST` policy with an empty allowlist is refused rather than silently
    behaving like `DENY_ALL`: the two are different intentions, and a caller who
    meant to allow specific hosts should learn that the list did not arrive.
    Conversely `ALLOW_ALL` is representable but carries no allowlist, so a caller
    cannot claim a restricted profile while permitting everything.
    """
    if network_policy not in NETWORK_POLICIES:
        raise SandboxRefused(
            f"network policy {network_policy!r} is not declared; expected one of "
            f"{NETWORK_POLICIES}"
        )
    missing_quotas = [name for name in REQUIRED_QUOTAS if name not in quotas]
    if missing_quotas:
        raise SandboxRefused(
            f"sandbox profile leaves {missing_quotas} unbounded; an unbounded candidate run "
            "cannot be distinguished from a hang or reconciled against a budget"
        )
    for name in REQUIRED_QUOTAS:
        value = quotas[name]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise SandboxRefused(
                f"quota {name} is {value!r}; every quota must be a positive integer bound"
            )

    forbidden = sorted(set(declared_capabilities) & FORBIDDEN_CANDIDATE_CAPABILITIES)
    if forbidden:
        raise SandboxRefused(
            f"sandbox profile declares {forbidden}, which would let candidate code reach its "
            "own evaluator or the hidden holdout"
        )
    if network_policy == "ALLOWLIST" and not network_allowlist:
        raise SandboxRefused(
            "ALLOWLIST network policy carries an empty allowlist; treating that as DENY_ALL "
            "would hide a missing configuration behind correct-looking behaviour"
        )
    if network_policy != "ALLOWLIST" and network_allowlist:
        raise SandboxRefused(
            f"network policy {network_policy} carries an allowlist that it would ignore"
        )

    profile: dict[str, Any] = {
        "profile_id": profile_id or new_id("SBX"),
        "profile_name": profile_name,
        "declared_capabilities": sorted(set(declared_capabilities)),
        "quotas": {name: int(quotas[name]) for name in REQUIRED_QUOTAS},
        "network_policy": network_policy,
        "network_allowlist": sorted(set(network_allowlist)),
    }
    profile["profile_hash"] = sha256_of_payload(
        {key: value for key, value in profile.items() if key != "profile_hash"}
    )
    return profile


def build_capability_lease(
    *,
    principal_id: str,
    capabilities: Sequence[str],
    resource_scopes: Sequence[str],
    issued_at: str,
    expires_at: str,
    fencing_token: int,
    policy_hash: str,
    approval_ids: Sequence[str],
    lease_id: str | None = None,
) -> dict[str, Any]:
    """Lease capabilities to a candidate, always as `principal_type: agent`.

    The principal type is fixed rather than accepted. A candidate leasing itself
    `service` or `human` standing would inherit the broader capability set those
    principals are permitted, and the whole point of the lease is that candidate
    code holds the narrowest standing in the system.

    `fencing_token` is a positive integer per the schema, not an opaque string: it
    is a monotonic fence, so a stale holder that wakes up after its lease was
    superseded presents a lower token and is rejected by the resource rather than
    racing the current holder.

    `revoked` starts False with an explicit `null` reason, so "not revoked" is
    distinguishable from "revocation state never recorded".
    """
    forbidden = sorted(set(capabilities) & FORBIDDEN_CANDIDATE_CAPABILITIES)
    if forbidden:
        raise SandboxRefused(
            f"refusing to lease {forbidden} to candidate {principal_id}: a candidate that can "
            "reach the evaluator or holdout can score itself"
        )
    if not capabilities:
        raise SandboxRefused(
            "a lease must name at least one capability; an empty lease is a construction bug "
            "rather than a read-only grant"
        )
    if expires_at <= issued_at:
        raise SandboxRefused(
            f"lease expires at {expires_at} which is not after {issued_at}; an unexpiring or "
            "already-expired lease cannot bound an execution"
        )
    if isinstance(fencing_token, bool) or not isinstance(fencing_token, int) or fencing_token < 1:
        raise SandboxRefused(
            f"fencing token {fencing_token!r} is not a positive integer; without a monotonic "
            "fence a superseded lease holder cannot be told apart from the current one"
        )

    lease: dict[str, Any] = {
        "lease_id": lease_id or new_id("LSE"),
        "principal_id": principal_id,
        "principal_type": "agent",
        "capabilities": sorted(set(capabilities)),
        "resource_scopes": sorted(set(resource_scopes)),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "fencing_token": fencing_token,
        "policy_hash": policy_hash,
        "approval_ids": list(approval_ids),
        "revoked": False,
        "revocation_reason": None,
    }
    lease["lease_hash"] = hash_excluding(lease, "lease_hash")
    validate_artifact("capability-lease", lease)
    return lease


def execution_blockers(
    *,
    profile: Mapping[str, Any],
    lease: Mapping[str, Any],
    requested_capabilities: Sequence[str],
    now: str,
    evaluator_bundle_id: str,
    holdout_manifest_id: str,
    reachable_resource_ids: Sequence[str],
) -> list[str]:
    """Every reason this candidate execution is refused.

    Reachability is checked against the resources the runner can actually see
    rather than against what the candidate declared it would touch. A candidate's
    own declaration is not evidence about its behaviour, which is why the evaluator
    and holdout ids are compared to the reachable set here.
    """
    blockers: list[str] = []

    if bool(lease.get("revoked")):
        blockers.append(f"lease {lease.get('lease_id')} is revoked")
    expires_at = str(lease.get("expires_at", ""))
    if not expires_at or now >= expires_at:
        blockers.append(f"lease {lease.get('lease_id')} is not valid at {now}")

    leased = set(lease.get("capabilities", []))
    declared = set(profile.get("declared_capabilities", []))
    requested = set(requested_capabilities)

    undeclared = sorted(requested - declared)
    if undeclared:
        blockers.append(f"capabilities {undeclared} are not declared by the sandbox profile")
    unleased = sorted(requested - leased)
    if unleased:
        blockers.append(f"capabilities {unleased} are not leased to this candidate")
    forbidden = sorted(requested & FORBIDDEN_CANDIDATE_CAPABILITIES)
    if forbidden:
        blockers.append(f"capabilities {forbidden} would breach evaluator/holdout isolation")

    reachable = set(reachable_resource_ids)
    if evaluator_bundle_id in reachable:
        blockers.append(
            f"evaluator bundle {evaluator_bundle_id} is reachable from the sandbox; the "
            "candidate could alter what judges it"
        )
    if holdout_manifest_id in reachable:
        blockers.append(
            f"hidden holdout {holdout_manifest_id} is reachable from the sandbox; the "
            "candidate could read the test it is measured on"
        )

    if str(profile.get("network_policy")) == "ALLOW_ALL" and "network" in requested:
        blockers.append(
            "unrestricted egress is requested; an open network path exfiltrates the holdout "
            "and imports unqualified content"
        )
    if "network" in requested and str(profile.get("network_policy")) == "DENY_ALL":
        blockers.append("network access is requested under a DENY_ALL policy")

    missing_quotas = [name for name in REQUIRED_QUOTAS if name not in profile.get("quotas", {})]
    if missing_quotas:
        blockers.append(f"sandbox profile leaves {missing_quotas} unbounded")

    return blockers


def require_execution_permitted(**kwargs: Any) -> None:
    """Raise `SandboxRefused` listing every blocker at once."""
    blockers = execution_blockers(**kwargs)
    if blockers:
        raise SandboxRefused(
            "refusing candidate execution: " + "; ".join(blockers)
        )


def build_execution_receipt(
    *,
    intent_id: str,
    run_id: str,
    external_operation_id: str,
    idempotency_key: str,
    started_at: str,
    finished_at: str,
    exit_code: int | None,
    quota_exceeded: bool,
    result_artifact_ids: Sequence[str],
    error_artifact_ids: Sequence[str],
    observed_state_hash: str,
    receipt_id: str | None = None,
) -> dict[str, Any]:
    """Record what the candidate execution actually did.

    `status` is derived, never supplied. A missing exit code yields `UNKNOWN`
    rather than `FAILED`: a run whose outcome was never observed may well have had
    effects, and calling that a clean failure would let a caller skip
    reconciliation. `reconciliation_required` is therefore True for exactly the
    `UNKNOWN` case.
    """
    if exit_code is None:
        status = "UNKNOWN"
    elif quota_exceeded:
        # A quota kill is a failure of the run, not of the candidate's claim.
        status = "FAILED"
    elif exit_code == 0:
        status = "SUCCEEDED"
    else:
        status = "FAILED"

    receipt: dict[str, Any] = {
        "receipt_id": receipt_id or new_id("ERC"),
        "intent_id": intent_id,
        "run_id": run_id,
        "external_operation_id": external_operation_id,
        "status": status,
        "result_artifact_ids": list(result_artifact_ids),
        "error_artifact_ids": list(error_artifact_ids),
        "observed_state_hash": observed_state_hash,
        "idempotency_key": idempotency_key,
        "started_at": started_at,
        "finished_at": finished_at,
        "reconciliation_required": status == "UNKNOWN",
    }
    receipt["receipt_hash"] = hash_excluding(receipt, "receipt_hash")
    validate_artifact("effect-receipt", receipt)
    return receipt


def execution_is_accounted(receipt: Mapping[str, Any]) -> bool:
    """True when the execution's outcome is known and needs no reconciliation."""
    return (
        str(receipt.get("status")) in {"SUCCEEDED", "FAILED", "ROLLED_BACK", "NOT_EXECUTED"}
        and not bool(receipt.get("reconciliation_required"))
    )
