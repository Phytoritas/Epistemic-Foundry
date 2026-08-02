---
name: foundry
description: "Route research and evidence-synthesis requests. Use for claim validation; do not use for ordinary editing or casual questions."
metadata:
  architecture-version: "4.0.0"
  status: "ACTIVE"
  allow_implicit_invocation: true
  sensitive: false
  side_effecting: false
---

# Epistemic Foundry parent router

This parent skill routes requests; it does not own state, approval, promotion, or execution authority. Its always-visible surface is limited to name, description, activation policy, bounded trigger phrases, exclusions, and a content hash.

Use the deterministic parent router to select the minimum applicable skill. Load a selected child skill only after the metadata-only `SkillRoutingDecision` has been sealed. Do not preload child bodies or references into the routing context.

Implicit invocation is limited to a single unambiguous bundled skill whose metadata explicitly permits it. Sensitive, side-effecting, administrative, and remote skills are explicit-only. Missing activation policy means implicit invocation is denied. Remote skills additionally require the exact S03 approval, lock, conformance, and activation authorization boundary.

Do not invoke for ordinary editing, rewriting, proofreading, translation, or casual questions. Abstain when triggers are absent, excluded, or tied. Never treat a routing decision as permission to mutate FORGE state, issue approval, perform an effect, or claim completion.

After routing, preserve the Foundry constitution: source-anchored Claims, coverage before confidence, visible counter/null evidence, typed inference modes, no majority promotion, and receipt-bound completion.
