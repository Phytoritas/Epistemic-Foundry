---
name: foundry-evolution-replay
description: "Replay an evolution cycle or lineage from a checkpoint under strict, semantic, or provider-nondeterministic equivalence."
metadata:
  architecture-version: "4.0.0"
  status: "ACTIVE"
---

# Evolution replay

Verify run spec, evaluator, holdout, candidate, archive, operator bandit, prompt, provider, environment, seed and artifact hashes. Never claim byte-identical replay for provider-nondeterministic generation. Re-execution creates a new run and linkage, not overwritten history.
