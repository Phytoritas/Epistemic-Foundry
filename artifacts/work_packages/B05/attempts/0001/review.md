# B05-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The write-scope conflict was resolved on the record, not around it.
  The manifest grants build/v4_b05/** while .gitignore ignores build/,
  so HD-EF4-B05-SCOPE-20260801-001 reads the deliverable as generated,
  reproducible build output: the generator and tests are tracked in
  this attempt directory, the output is re-derived byte-identically
  from five tracked inputs, and .gitignore, pyproject.toml and uv.lock
  are never edited.
- Pinning is proved, not asserted. The build backend must be pinned
  exactly, all twenty locked external packages must carry sha256
  artifact hashes, the lock's Python floor must equal the project's,
  every declared dependency and group entry must resolve in the lock,
  and the canonical registry must carry the sealed B04 counts of 127
  schemas plus one OpenAPI document.
- The Shinka feature cannot be talked on. It is emitted DISABLED and
  UNQUALIFIED, every EF4-I63 authority flag is false, and verification
  refuses an edited profile with the code that names the attempt —
  enablement, qualification overclaim, authority grant, or a smuggled
  install extra — because no sealed B06/T06 qualification exists. A
  shinka dependency in pyproject or the lock is refused at derivation
  time.
- The pin candidate is recorded at its true strength. backend_name and
  license come from the canonical schema consts; the repository, the
  v0.0.7 tag and the short commit come from the research manifest,
  which itself says a byte-complete audit was not available; and every
  blocked manifest field names the reason it cannot be pinned yet.
  Every disabled feature is grounded in a recorded observation string.
- Receipts caught a real drift during this attempt: the first emitted
  manifest recorded the generator hash from before a formatter pass,
  and verification refused with GENERATOR_DRIFT until the output was
  re-emitted from the final generator. The receipt did its job.
- Determinism is the crash/resume story: a deleted or corrupted output
  is refused with a typed code and then repaired byte-identically by
  re-emitting, so partial state can never masquerade as a build.
- Residual limitations: the ShinkaEvolve pin is a public observation,
  not a verified clone; the locked wheel hashes are trusted as the pin
  authority and no wheel rebuild was performed, which the B06
  reproducible-build gate owns; enablement and qualification belong to
  B06 and T06; and this review is not external actor-independent
  certification.
