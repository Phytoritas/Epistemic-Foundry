# J02 primary-session separate contract review

Status: `SPEC_GAP (J02-SG001)`

Review mode: `PRIMARY_SESSION_SEPARATE_ADVERSARIAL_CONTRACT_REVIEW`

Assurance limitation: this review was conducted as a procedurally separate
primary-session pass. It is not actor-independent certification because the
product owner explicitly prohibited Fleet and subagents for this execution.

## Verdict

J01 is an evidence-sealed `PASS`, so J02 is dependency-ready. Dependency
readiness does not supply the missing progressive-reference semantics. J02
cannot implement or objectively pass its required checks within the current
authority chain.

## Findings

1. `MASTER_SPEC.md` names J02 but does not define an operative budget or
   reference-loading contract. The inherited architecture text only states
   that metadata is visible and detailed references load on demand.
2. No numeric host budget, accounting unit, tokenizer/version, included field
   set, canonical serialization, or over-budget failure behavior is defined.
   The J01 router merely preserves a caller-provided `context_budget_tokens`
   value; it neither computes nor enforces the J02 budget.
3. The installed skill tree has one `SKILL.md`, one agent metadata file, and no
   references. The blueprint skill tree has 29 `SKILL.md` files and no
   references, while `PACKAGE_MANIFEST.json` explicitly labels the blueprint
   `REFERENCE_BLUEPRINT_NOT_IMPLEMENTED`. Authority does not decide whether
   those child skills become installed skills, reference material, or remain
   blueprint-only.
4. No canonical reference inventory or mapping connects a routed skill,
   request, or state to needed references. No declaration format defines
   ordering, deduplication, transitive loading, missing files, cycles, or path
   traversal.
5. No loader/runtime owner or exact implementation path is assigned. J02's
   product write scope permits only `skills/**/references/**`; it cannot edit
   `SKILL.md`, the J01 router, a loader, metadata, or ordinary test paths.
6. `context_budget_test` and `reference_reachability_test` are names only in
   `development_manifest.yaml`. There are no authorized fixtures, test paths,
   exact expected values, or pass thresholds. Letting the implementation invent
   them would make the package author its own acceptance oracle.

## Classification

The correct outcome is `SPEC_GAP`, not `FAIL`: the required shared contract is
missing, so no valid implementation has been attempted. It is not `BLOCKED`:
no external prerequisite is unavailable. The J02 stop condition explicitly
requires `SPEC_GAP` when a shared contract, authority boundary, or acceptance
threshold is ambiguous.

## Required decision

A product-owner HumanDecision must define the exact metadata budget and
accounting, canonical installed skill/reference inventory, deterministic
reference-selection and reachability rules, loader/runtime owner and exact
write paths, and the complete fixtures and thresholds for both required
checks. It must also decide the disposition of all 29 blueprint child skills.

J02-0001 must remain immutable `SPEC_GAP` history. Do not create arbitrary
references or thresholds, weaken the metadata-only J01 boundary, or skip to a
later package while this earliest package remains unresolved.
