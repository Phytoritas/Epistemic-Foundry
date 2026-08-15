"""Skill quarantine and activation gating (EF4-I21).

Contract source: `schemas/skill-lockfile.schema.json`.

Five conditions must all hold before a third-party skill activates: it is
inspected, permissioned, pinned to an exact digest, approved, and not
quarantined. `require_activation_allowed` checks them together and reports every
failure, because a skill that satisfies four of five is not partially safe.

The pin is the condition most easily skipped and the most consequential: an
unpinned skill can change after the approval that authorized it, so the approval
would attest to code that no longer runs.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..contracts import validate_artifact
from ..domain.hashing import hash_excluding, is_schema_digest
from ..domain.time import utc_now_iso


class SkillActivationRefused(PermissionError):
    """A skill does not satisfy the activation contract."""


#: Fields a lockfile skill entry must carry, per `skill-lockfile.schema.json`.
#: `signature_status` and `approved_by_ids` are the two that make the pin
#: accountable: a digest with no signature state and no named approver records
#: what the code is but not that anyone vouched for it.
REQUIRED_LOCK_FIELDS: tuple[str, ...] = (
    "skill_id",
    "source",
    "revision",
    "content_hash",
    "signature_status",
    "license",
    "permissions",
    "review_status",
    "approved_by_ids",
)

#: Review states that permit activation.
ACTIVATABLE_REVIEW_STATES: frozenset[str] = frozenset({"APPROVED"})


#: Vetting flags the runtime tracks outside the lockfile. The lockfile schema is
#: closed (`additionalProperties: false`), so quarantine and inspection state is
#: supplied to the gate but stripped before sealing.
RUNTIME_ONLY_FIELDS: tuple[str, ...] = ("inspected", "quarantined", "approved", "name", "digest")


def activation_blockers(skill: Mapping[str, Any]) -> list[str]:
    """Every reason this skill may not activate."""
    blockers: list[str] = []
    name = str(skill.get("name") or skill.get("skill_id") or "<unnamed>")

    if skill.get("quarantined"):
        blockers.append(f"{name} is quarantined")
    if not skill.get("inspected"):
        blockers.append(f"{name} has not been inspected")
    review_status = skill.get("review_status")
    approved = skill.get("approved")
    if review_status is not None:
        if str(review_status) not in ACTIVATABLE_REVIEW_STATES:
            blockers.append(f"{name} review_status is {review_status}, not APPROVED")
        if not skill.get("approved_by_ids"):
            blockers.append(
                f"{name} records no approver; a review with no named approver leaves nobody "
                "accountable for the activation"
            )
    elif not approved:
        blockers.append(f"{name} has not been approved")

    digest = skill.get("content_hash") or skill.get("digest")
    if not digest:
        blockers.append(
            f"{name} is unpinned; an unpinned skill can change after the approval that "
            "authorized it"
        )
    elif not is_schema_digest(str(digest)):
        blockers.append(f"{name} digest {digest!r} is not a sha256 pin")

    permissions = skill.get("permissions")
    if permissions is None:
        blockers.append(
            f"{name} has no permission set; absent permissions are not the same as none, "
            "so activation is refused rather than assumed unprivileged"
        )
    return blockers


def require_activation_allowed(skill: Mapping[str, Any]) -> None:
    """Raise `SkillActivationRefused` listing every blocker."""
    blockers = activation_blockers(skill)
    if blockers:
        raise SkillActivationRefused("; ".join(blockers))


def build_skill_lockfile(
    *,
    workspace_id: str,
    skills: Sequence[Mapping[str, Any]],
    policy_hash: str,
    lock_version: int = 1,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Seal a skill lockfile, refusing any entry that could not activate.

    The lockfile is the activation authority, so writing an unpinned or
    unapproved entry into it would launder the very condition the lock exists to
    guarantee.
    """
    problems: list[str] = []
    for skill in skills:
        problems.extend(activation_blockers(skill))
        missing = [field for field in REQUIRED_LOCK_FIELDS if field not in skill]
        if missing:
            problems.append(
                f"{skill.get('skill_id', '<unnamed>')} lockfile entry is missing {missing}"
            )
    if problems:
        raise SkillActivationRefused(
            "refusing to seal a lockfile containing non-activatable skills: " + "; ".join(problems)
        )

    lockfile: dict[str, Any] = {
        "lock_version": int(lock_version),
        "workspace_id": workspace_id,
        "skills": [
            {key: value for key, value in skill.items() if key not in RUNTIME_ONLY_FIELDS}
            for skill in skills
        ],
        "generated_at": generated_at or utc_now_iso(),
        "policy_hash": policy_hash,
    }
    lockfile["lock_hash"] = hash_excluding(lockfile, "lock_hash")
    validate_artifact("skill-lockfile", lockfile)
    return lockfile
