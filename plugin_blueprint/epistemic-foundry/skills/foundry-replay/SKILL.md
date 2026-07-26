---
name: foundry-replay
description: "Replay a run, compare strict reducer state or semantic outputs, and propagate staleness after source, policy, ontology, parser, prompt, or model changes. Do not overwrite prior artifacts."
metadata:
  architecture-version: "4.0.0"
  status: "REFERENCE_BLUEPRINT"
---

# Replay and reassessment

Resolve exact RunSpec, corpus, policy, prompts, adapters, models, tools, seeds, and receipts. Run strict replay where deterministic and semantic comparison otherwise. Mark dependent artifacts stale and create new revisions.
