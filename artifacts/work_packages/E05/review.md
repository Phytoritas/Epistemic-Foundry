# E05 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# E05-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The engine adds the reconciliation nobody was doing. The chamber
  already accounts for candidate identities and the ledger already
  mints receipts, but nothing checked the two against each other, and
  that is exactly where a side effect hides: eight candidates
  persisted, nine effect receipts, and no one notices the ninth
  belongs to nothing. Six distinct failure classes are reported by
  name rather than collapsed into an unreconciled count.
- Nothing is reimplemented. Candidate accounting comes from
  evolution_chamber.reconciliation, receipts from noetic_ledger and
  evolution_chamber.mutation, and the effect-status vocabulary is
  imported with get_args from the module that declares it. The tests
  mint every receipt through those builders, so what the engine agrees
  with is the ledger rather than the test author.
- EF4-I22 is enforced on this module by the repository's own gate,
  which runs as a named check here rather than only inside the full
  suite. It caught a real violation during this attempt: the report
  carried a 'proposed' count whose key is a canonical enum value. The
  count was already present in the composed candidate report, so the
  duplicate was removed rather than the module being registered as a
  declaring owner it is not.
- The status-to-disposition table is data, not Python literals, and is
  verified on every use to cover the imported vocabulary exactly. A
  status added to the contract fails loudly as DISPOSITION_DRIFT
  instead of falling through to a permissive default.
- Three engine corrections came from the adversarial tests. An
  unmapped status was reported as a flag inconsistency until the
  status check was moved first; an effect referenced by an orphan
  mutation was double-reported as an orphan effect until binding was
  widened to any referencing mutation; and a broken fan-out reported a
  ledger consequence before its cause until the candidate check was
  ordered first. Each made the refusal name the right failure.
- One file outside the manifest grant was authorized and recorded:
  src/epistemic_foundry/effects/__init__.py. Verified empirically that
  without it find_packages returns nothing for this engine while
  find_namespace_packages finds it, so the module would import from a
  checkout but be absent from the wheel. A named packaging-discovery
  check now proves it stays discoverable, reading the discovery mode
  from pyproject rather than assuming it.
- Residual limitations: this reconciles ledgers that are handed to it,
  it does not collect them from a running system — wiring it into the
  EVOLVE loop belongs to F05; UNKNOWN effects are reported as
  unresolved rather than resolved, because resolving them needs the
  external system this engine deliberately does not touch; and this
  review is not external actor-independent certification.
