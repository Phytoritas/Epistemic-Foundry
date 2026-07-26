---
name: foundry-plugin-dev
description: "Build, test, audit, package, migrate, or release the Epistemic Foundry plugin from this specification. Use for repository implementation work; do not self-approve or claim production readiness without release gates."
metadata:
  architecture-version: "4.0.0"
  status: "REFERENCE_BLUEPRINT"
---

# Plugin development

Follow the A–Z development manifest and exact write scope. Use disjoint worktrees for parallel writes. Generate contracts, run required checks, obtain independent review, and emit a WorkPackageReport. Stop with SPEC_GAP or BLOCKED rather than inventing missing contracts or infrastructure.
