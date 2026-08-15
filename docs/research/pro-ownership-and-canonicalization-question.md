# Epistemic Foundry v4 — two structural blockers, and which to ratify first

Authority order is `MASTER_SPEC.md` > `manifests/development_manifest.yaml` >
`manifests/acceptance_matrix.yaml` > `manifests/product_invariants.yaml` >
`schemas/*.schema.json` and `workflows/*.workflow.yaml` >
`manifests/role_registry.yaml`. Do not propose a path that bypasses it, and do
not treat work-package PASS reports as proof of runtime reachability — all 156
packages currently record PASS while the defects below were reproduced against
production entry points.

## What was fixed since the last question (context, not the ask)

One defect class was mapped exhaustively rather than found one at a time. Of the
188 `*_hash` schema properties, 96 are self-checksums (the writer seals the
record with that one field omitted, via `hash_excluding`) and 92 are foreign
references. Of 151 Python production modules touching those fields, 114 already
re-derive correctly.

Sixteen readers did not, and were repaired in their owning packages: the three
Parliament record types and the Aporia graph in the web console; `ForgeSession`
and `ReplayReport` in F06; search-lane receipt identity in K06; the
`SelectiveInferenceReport` in both Q05 and, separately, Q06; `PhaseArtifactSet`
and `ArtifactReceipt` in A05; `ChallengeResult`, `ReplicationResult` and
`ReplicationPlan` in P05; `StageEvaluationResult` in V05; `EffectReceipt` and
`PromotionDecision` in C03; drift classification in W04; and checkpoint
projections in W02. A duplicated identity-derivation algorithm was also
consolidated: O05 now exports the rule publicly and K06/O06 call it instead of
carrying byte-identical copies.

A05's G01–G13 were additionally switched from silent pass-through to explicit
fail-closed `SPEC_GAP`, per your prior recommendation.

## The two blockers

### 1. Ownership: 115 of 235 Python files under `src/` belong to no work package

This is not dead code. Every one of those files is on an execution path reached
by an owned v4 package, the installed CLI, or the root test suite.
`domain/hashing.py` alone is imported directly by 55 owned modules;
`contracts/__init__.py` by 45.

Two confirmed defects are currently unfixable because of this:

- `memory/policy.py` — `require_recall_permitted` applies only
  `default_retention_days` and ignores `class_rules[].retention_days`. Verified:
  a 200-day-old EPHEMERAL memory whose class rule says 1 day is accepted. The
  canonical schema requires the per-class field, and the JS twin
  (`memory-policy.mjs`) honors it correctly — so the Python side is the deviant
  one.
- `retrieval/lexical_index.py` — `read_index_stats()` returns a stored
  `corpus_snapshot_hash` without re-deriving it from the indexed documents. The
  build path does verify; the ordinary query path does not, so an inaccurate
  searched-scope can be sealed into a lane receipt. `retrieval/lanes.py` has the
  companion gap: `reconcile_lanes()` aggregates candidates and receipts without
  re-deriving either.

Git history argues against "intentionally frozen pre-v4 legacy":
`domain/hashing.py` first appears in the v4 kernel-core commit and
`memory/policy.py` in the commit implementing EF4-I18/I19. Neither MASTER_SPEC
nor the migration doc describes freezing or relocating the Python tree.

A read-only census proposed the minimal ratification: assign
`memory/policy.py` (+ its test) to L01, whose own title is "Memory classes,
consent and retention policy"; assign `domain/hashing.py` to C03, which already
owns hash-bound Python runtime files. It explicitly declined to place the
remaining 113.

### 2. Canonicalization: the two canonical JSON implementations disagree on numbers

`src/epistemic_foundry/domain/hashing.py` uses Python `json.dumps`;
`web/src/app/record-hash.mjs` uses `JSON.stringify`. Verified divergences:

    1.0   -> Python {"x":1.0}   JS {"x":1}
    0.0   -> Python {"x":0.0}   JS {"x":0}
    1e16  -> Python {"x":1e+16} JS {"x":10000000000000000}
    1e-7  -> Python {"x":1e-07} JS {"x":1e-7}
    -0.0  -> Python {"x":-0.0}  JS {"x":0}
    0.6   -> both {"x":0.6}     (agree)

End-to-end: an ArgumentGraph with `edges[0].confidence = 1.0`, sealed by Python
as `sha256:d37ab74d…`, re-derives in JS as `sha256:f7359b05…`. So today's JS
hardening rejects an honest Python-produced record. `confidence` is a real 0..1
field and 1.0 is its natural boundary value, so this is a live producer path.

As an interim measure the two web views now distinguish this case: they still
refuse, but report it as an unratified cross-language canonicalization
divergence rather than as tampering. That is diagnosis, not a fix.

Complicating the obvious answer: a census found roughly 64 canonicalization
implementations across the repo in at least six number-policy camps. Repository
docs specify RFC 8785 JCS (`docs/forge_protocol.md:90`,
`docs/retrieval_contract.md:30,57`,
`docs/v4_a05/evolution_authority_and_promotion_charter.md:138`), which mandates
ECMAScript number formatting — i.e. JS conforms and `hashing.py` does not. But
those docs rank below schemas, `argument-graph.schema.json` pins no
canonicalization rule at all, and `MASTER_SPEC.md:1295` states historical hashes
are never rewritten. Most `examples/*.json` (162 of 169 self-hash fields) already
carry placeholder digests that never re-derived, so little would *newly* break —
but nine raw-byte pins in `PACKAGE_MANIFEST.json` would.

There is also a subtlety: under JCS, Python `int` 1 and `float` 1.0 serialize
identically, merging two preimages that are currently distinct.

## The question

Which of these two should be ratified first, and in what exact form?

Please be concrete about:

1. **Which one, and why it dominates.** Judge by how much genuinely
   dependency-ready work each unlocks per unit of contract change. Note that
   ownership blocks a growing queue of small, well-understood repairs, while
   canonicalization currently causes an active false-rejection of valid data.
2. **Ownership, if you pick it.** Is the proposed L01/C03 assignment right, or
   does the `domain/`+`contracts/` cluster (8 files, 45+ owned importers) need a
   different home? Should the remaining 113 be assigned in one census or left
   until each is needed? Is a new maintenance package justified, or is that
   worse than targeted assignment?
3. **Canonicalization, if you pick it.** Does JCS actually govern, given that
   the specifying documents rank below schemas? If Python adopts JCS, how should
   the int/float merge and the never-rewrite-history rule be reconciled — a
   canonicalization version field, a migration window, or something else? And
   what happens to the other ~62 implementations?
4. **Sequencing.** If one must precede the other, say which and why. Note that
   the canonicalization fix would land in `domain/hashing.py`, which is one of
   the unowned files — so the two may not be independent.
5. **What stays blocked.** Name what remains unresolved after your recommended
   decision ships, including whether the previously recommended
   `NodeAttemptEffectTerminalProof` should still come before or after this.

One recommendation only. Prefer refusing over inventing a contract the authority
order does not support.
