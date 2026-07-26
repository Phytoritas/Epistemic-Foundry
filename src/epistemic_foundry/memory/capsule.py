"""Canonical context capsules for compaction and resume (EF4-I20).

Contract source: `schemas/context-capsule.schema.json`.

"Compaction and resume context is rebuilt from hash-bound canonical artifacts
with exclusions and freshness." Each of those words carries a refusal:

* *hash-bound*: a summary is bound to the digest of the artifact it summarizes.
  A capsule rebuilt from a summary whose source has since changed would resume a
  session on a description of a state that no longer exists, which is worse than
  resuming with no context because the stale summary reads as current.
* *exclusions*: an artifact that was deliberately withheld is named in
  `excluded_artifact_ids`, so a later reader can tell "not relevant" from "never
  existed". A silent omission is indistinguishable from a coverage gap.
* *freshness*: an expired capsule is refused rather than used with a warning.
  `expires_at` is nullable in the schema, and a null value means "no expiry
  declared", which is treated as unusable for resume rather than eternal.

A capsule is never its own authority: it carries artifact identities and bound
summaries, never verdicts, gate results, or promotion state.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding, is_schema_digest, sha256_of_payload
from ..domain.ids import new_id
from ..domain.status import ForgePhase
from ..domain.time import utc_now_iso

#: FORGE phases a capsule may be built for. Derived from `domain.status.ForgePhase`
#: rather than restated, so the capsule phase vocabulary cannot drift away from the
#: session phase vocabulary it has to agree with.
CAPSULE_PHASES: tuple[str, ...] = tuple(str(phase) for phase in ForgePhase)


class CapsuleRefused(ValueError):
    """A capsule cannot be built as requested."""


class CapsuleStale(RuntimeError):
    """A capsule is expired, foreign to the run, or bound to changed artifacts."""


def build_context_capsule(
    *,
    session_id: str,
    phase: str,
    purpose: str,
    run_spec_hash: str,
    policy_hash: str,
    artifact_hashes: Mapping[str, str],
    summaries: Mapping[str, str],
    excluded_artifact_ids: Sequence[str],
    open_blockers: Sequence[str],
    allowed_capabilities: Sequence[str],
    token_budget: int,
    expires_at: str | None,
    capsule_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Seal a capsule whose every summary is bound to its artifact's digest.

    `artifact_ids` is derived from `artifact_hashes` rather than accepted
    separately. Taking both would permit a capsule listing an artifact it holds no
    digest for, and that artifact is exactly the one whose staleness could not
    later be detected.
    """
    if phase not in CAPSULE_PHASES:
        raise CapsuleRefused(
            f"phase {phase!r} is not a FORGE phase; expected one of {CAPSULE_PHASES}"
        )
    if not purpose.strip():
        raise CapsuleRefused(
            "a capsule needs a stated purpose; an unexplained context bundle cannot be "
            "audited for what it was allowed to carry"
        )
    for label, digest in (("run_spec_hash", run_spec_hash), ("policy_hash", policy_hash)):
        if not is_schema_digest(digest):
            raise CapsuleRefused(f"{label} must be a sha256 digest, got {digest!r}")

    if not artifact_hashes:
        raise CapsuleRefused(
            "a capsule must bind at least one canonical artifact; a capsule built only "
            "from prose has nothing to verify freshness against"
        )
    for artifact_id, digest in artifact_hashes.items():
        if not is_schema_digest(digest):
            raise CapsuleRefused(
                f"artifact {artifact_id} carries {digest!r}, which is not a sha256 digest; "
                "an unbound artifact cannot be checked for staleness"
            )

    excluded = list(dict.fromkeys(excluded_artifact_ids))
    overlap = sorted(set(excluded) & set(artifact_hashes))
    if overlap:
        raise CapsuleRefused(
            f"artifacts {overlap} are both included and excluded; a capsule cannot record "
            "two different decisions about the same artifact"
        )

    unknown_summaries = sorted(set(summaries) - set(artifact_hashes))
    if unknown_summaries:
        raise CapsuleRefused(
            f"summaries reference artifacts the capsule does not carry: {unknown_summaries}; "
            "an unbound summary is the stale-context failure this invariant forbids"
        )

    summary_records = [
        {
            "artifact_id": artifact_id,
            "summary": summaries[artifact_id],
            "source_hash": artifact_hashes[artifact_id],
            "summary_hash": sha256_of_payload(summaries[artifact_id]),
        }
        for artifact_id in sorted(summaries)
    ]

    capsule: dict[str, Any] = {
        "capsule_id": capsule_id or new_id("CAP"),
        "session_id": session_id,
        "phase": phase,
        "purpose": purpose,
        "run_spec_hash": run_spec_hash,
        "policy_hash": policy_hash,
        "artifact_ids": sorted(artifact_hashes),
        "summaries": summary_records,
        "open_blockers": list(open_blockers),
        "excluded_artifact_ids": excluded,
        "allowed_capabilities": sorted(set(allowed_capabilities)),
        "token_budget": token_budget,
        "created_at": created_at or utc_now_iso(),
        "expires_at": expires_at,
    }
    capsule["capsule_hash"] = hash_excluding(capsule, "capsule_hash")
    validate_artifact("context-capsule", capsule)
    return capsule


def stale_artifact_ids(
    capsule: Mapping[str, Any], current_hashes: Mapping[str, str]
) -> list[str]:
    """Artifacts whose current digest differs from the bound one, or vanished.

    A missing artifact counts as stale rather than unchanged. Resuming against a
    deleted artifact using its remembered summary is how a session keeps
    reasoning about evidence that is no longer there.
    """
    stale: list[str] = []
    for record in capsule.get("summaries", []):
        artifact_id = str(record.get("artifact_id"))
        bound = str(record.get("source_hash"))
        current = current_hashes.get(artifact_id)
        if current is None or current != bound:
            stale.append(artifact_id)
    for artifact_id in capsule.get("artifact_ids", []):
        if artifact_id not in current_hashes and str(artifact_id) not in stale:
            stale.append(str(artifact_id))
    return sorted(set(stale))


def capsule_is_fresh(capsule: Mapping[str, Any], *, now: str) -> bool:
    """True only when the capsule declares an expiry that has not passed.

    A capsule with `expires_at: null` returns False. The schema permits null so a
    capsule can be recorded without an expiry, but an undeclared freshness window
    cannot be checked, and an uncheckable window is not a fresh one.
    """
    expires_at = capsule.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at:
        return False
    return now < expires_at


def require_rebuildable(
    capsule: Mapping[str, Any],
    *,
    current_hashes: Mapping[str, str],
    now: str,
    expected_run_spec_hash: str,
    expected_policy_hash: str,
) -> None:
    """Refuse a resume from an expired, drifted, or foreign-run capsule.

    The RunSpec and policy digests are compared because a capsule taken from one
    run cannot rehydrate another: its allowed capabilities and exclusions were
    decided under a policy that may no longer apply. Every failure raises rather
    than returning a flag, so a caller cannot proceed by ignoring a boolean.
    """
    if not capsule_is_fresh(capsule, now=now):
        raise CapsuleStale(
            f"capsule {capsule.get('capsule_id')} has no usable freshness window at {now}; "
            "an expired or undated capsule cannot rebuild a resume context"
        )
    if str(capsule.get("run_spec_hash")) != expected_run_spec_hash:
        raise CapsuleStale(
            f"capsule {capsule.get('capsule_id')} was built under a different RunSpec; "
            "its exclusions and capabilities were decided for another run"
        )
    if str(capsule.get("policy_hash")) != expected_policy_hash:
        raise CapsuleStale(
            f"capsule {capsule.get('capsule_id')} was built under a different policy; "
            "reusing it would apply superseded access decisions"
        )
    stale = stale_artifact_ids(capsule, current_hashes)
    if stale:
        raise CapsuleStale(
            f"capsule {capsule.get('capsule_id')} is bound to changed or missing artifacts "
            f"{stale}; rebuilding would resume on a summary of a state that no longer exists"
        )
