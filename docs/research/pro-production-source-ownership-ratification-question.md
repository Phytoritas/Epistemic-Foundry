# Production-source ownership ratification — executable decision

We are continuing the Epistemic Foundry v4 implementation against the current
working tree. Your prior recommendation was to establish complete tracked
production-source ownership before canonicalization.

Current local facts:

- `MASTER_SPEC.md` defines 64 invariants and does not yet contain EF4-I65.
- `manifests/development_manifest.yaml` has no top-level production-source
  ownership rule, and A01 does not currently own that manifest.
- A deterministic current-tree census found many tracked Python files under
  `src/epistemic_foundry/` with no matching work-package `write_scope`.
- Earlier review classified 76 files as having a defensible existing owner and
  39 as unresolved; a fresh current-tree census is running now.
- Four immediate assignments are already well supported:
  `memory/policy.py -> L01`, `retrieval/lexical_index.py -> O02`,
  `retrieval/lanes.py -> O02`, and exact file `domain/hashing.py -> C03`.
- Historical PASS reports cover only the files/claims they actually resolved;
  they do not prove every path listed in a package's `write_scope` exists or was
  implemented.
- A05 also exposed an ambiguity: some `write_scope` entries name absent paths,
  while its implemented responsibilities were consolidated in differently
  named files. The repository does not presently say whether `write_scope` is
  a maximal authorization boundary or a mandatory deliverable list.

We need one executable authority decision for this turn, not a general essay.

Please answer:

1. Freeze the exact normative wording for EF4-I65 and for
   `production_source_ownership_rule`.
2. Decide whether `write_scope` is (a) an authorization boundary, (b) a
   mandatory deliverable set, or (c) two separately named concepts. State how
   absent exact paths and absent `/**` roots must be interpreted.
3. Decide whether we should now ratify all defensible existing-owner mappings
   while explicitly leaving truly ambiguous files as `SPEC_GAP`, with the
   ownership gate intentionally failing; or whether the authority edit itself
   must wait until every file is assigned. Do not call a partial mapping
   complete closure.
4. State whether a cohesive subsystem directory may be assigned to an existing
   package when its responsibility is already named, or whether every one of
   the remaining ambiguous files requires a new owner decision.
5. Give the smallest deterministic B01 checker contract, including the exact
   production-source universe, scope matching rules, untracked/symlink/generated
   treatment, zero-owner and multiple-owner outcomes, and whether it should be
   a separate Python checker under `packages/repo-checks/` rather than extending
   the already-large JavaScript import lexer.
6. State how the new ownership mappings affect historical package PASS: which
   claims remain historical, and what cannot be extended to newly assigned
   paths without new work.

Constraints:

- Preserve authority order; do not invent a catch-all maintenance package.
- Do not change record schemas, hash bytes, runtime behavior, or canonicalization
  in this slice.
- The implementation should add no audit artifact or new PASS claim.
- Prefer an explicit fail-closed intermediate state over a misleading closure.

Return one recommended patch shape with exact file responsibilities and any
condition that must remain `SPEC_GAP`.
