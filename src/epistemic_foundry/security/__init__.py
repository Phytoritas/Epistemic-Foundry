"""Skill supply chain and role dispatch boundaries.

* EF4-I21: third-party skills are quarantined, inspected, permissioned, pinned,
  and approved before activation. An unpinned skill can change under the
  approval that authorized it, which makes the approval meaningless.
* EF4-I25: every subagent dispatch resolves a RoleSpec with tool ACL, evidence
  ACL, write scope, budget, and expected count. A dispatch without an expected
  count cannot be reconciled, so a silently dropped worker looks like success.
* EF4-I64: candidate code executes only under declared capabilities, resource
  quotas, network policy, effect receipts, and evaluator/holdout isolation. Every
  unknown in that list is a denial, because generated code is untrusted by
  construction.
"""

from __future__ import annotations

from .skills import (
    SkillActivationRefused,
    build_skill_lockfile,
    require_activation_allowed,
)
from .dispatch import (
    DispatchRefused,
    build_role_dispatch_plan,
    reconcile_dispatch,
)
from .sandbox import (
    FORBIDDEN_CANDIDATE_CAPABILITIES,
    REQUIRED_QUOTAS,
    SandboxRefused,
    build_capability_lease,
    build_execution_receipt,
    build_sandbox_profile,
    execution_blockers,
    execution_is_accounted,
    require_execution_permitted,
)

__all__ = [
    "DispatchRefused",
    "FORBIDDEN_CANDIDATE_CAPABILITIES",
    "REQUIRED_QUOTAS",
    "SandboxRefused",
    "SkillActivationRefused",
    "build_capability_lease",
    "build_execution_receipt",
    "build_role_dispatch_plan",
    "build_sandbox_profile",
    "build_skill_lockfile",
    "execution_blockers",
    "execution_is_accounted",
    "reconcile_dispatch",
    "require_activation_allowed",
    "require_execution_permitted",
]
