# O03 standalone cluster authority follow-up

Continue the O03 review in the same Epistemic Foundry conversation. Return
exactly one of `AUTHORIZED_LOCAL_REPAIR`, `SPEC_GAP`, or `NO_BLOCKER`, followed
by only the decisive contract reasoning and smallest safe change. Do not ask
to run tests.

Your prior answer required the authoritative cluster-validation path to
reconstruct dependency components from validated evidence units and exact
dependency edges, then compare the supplied cluster set exactly. The current
O03 implementation now does that inside `validate_evidence_pack`, which
rebuilds the pack and all clusters from its bound inputs.

One exported boundary remains different:

- `validate_evidence_dependency_cluster(payload)` accepts only one supplied
  cluster record. It validates the closed schema, vocabularies, ordering,
  numerical relationships, and self-hash, but cannot prove that the record is
  the deterministic connected component of source evidence units.
- R01's `reasoning/induction/contracts.py::independence_weights(pack, clusters)`
  imports this public O03 function and supplies only the Evidence Pack plus
  cluster records. It then uses `support_count_adjusted / support_count_raw`
  as scientific independence weights. It has no evidence-unit records,
  declared dependency links, run ID, or reconstruction inputs.
- O03 solely owns
  `python/epistemic_foundry/retrieval/evidence_pack/**`; R01 is outside that
  write scope. The canonical cluster schema carries no source-unit snapshot
  hash or reconstruction receipt. The Evidence Pack contains only cluster
  membership arrays, not the source inputs required to rederive edges.

Please decide the exact boundary:

1. Is it authorized within O03 alone to rename/reclassify the existing
   one-record function as shape/self-hash validation and add a new
   reconstruction validator that requires all units, links, run ID, and
   created_at, while leaving R01 unchanged until its owner adopts that API?
2. May O03 change the exported function signature in place even though that
   deterministically breaks the existing R01 caller outside O03 scope?
3. Or is authoritative standalone consumption by R01 a `SPEC_GAP` requiring a
   shared API/caller decision, while O03 may still retain the shape validator
   as explicitly non-authoritative and keep `validate_evidence_pack` as its
   only authoritative admission path?

Do not invent a cluster receipt, new schema field, source resolver, or O01
scope-partition semantics. State whether the current O03-local work can be
completed truthfully and what exact public naming/documentation/export change,
if any, is permitted without editing R01.
