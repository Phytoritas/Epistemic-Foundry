---
name: foundry-evolve-setup
description: "Create a typed EvolutionRunSpec, seed genomes, evaluator/holdout manifests, quality-diversity axes, budgets, and stop rules. Use before a new evolution run."
metadata:
  architecture-version: "4.0.0"
  status: "REFERENCE_BLUEPRINT"
---

# Evolution setup

Produce no running code until the user objective has a canonical claim family, scope, predictions, falsifiers, evidence boundary, allowed population types, evaluation cascade, hidden holdout policy, statistical family, budget, and stop conditions. Missing evaluator validity or holdout authority returns SPEC_GAP/BLOCKED.
