"""Skill supply chain and role dispatch boundaries.

* EF4-I21: third-party skills are quarantined, inspected, permissioned, pinned,
  and approved before activation. An unpinned skill can change under the
  approval that authorized it, which makes the approval meaningless.
* EF4-I25: every subagent dispatch resolves a RoleSpec with tool ACL, evidence
  ACL, write scope, budget, and expected count. A dispatch without an expected
  count cannot be reconciled, so a silently dropped worker looks like success.
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

__all__ = [
    "DispatchRefused",
    "SkillActivationRefused",
    "build_role_dispatch_plan",
    "build_skill_lockfile",
    "reconcile_dispatch",
    "require_activation_allowed",
]
