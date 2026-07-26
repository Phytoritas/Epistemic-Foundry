---
name: foundry-evolution-replay
description: "Replay an evolution cycle or candidate lineage from a checkpoint, distinguishing strict, semantic, and provider-nondeterministic equivalence."
metadata:
  architecture-version: "4.0.0"
  status: "REFERENCE_BLUEPRINT"
---

# Evolution replay

Verify run spec, evaluator, holdout, candidate, archive, operator bandit, prompt, provider, environment, seed and artifact hashes. Never claim byte-identical replay for provider-nondeterministic generation. Re-execution creates a new run and linkage, not overwritten history.
