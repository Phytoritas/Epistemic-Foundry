# P01 current-delta adversarial review

Review only the current attached P01 source and its narrow regression source against the attached CouncilBrief schema, role registry, MASTER_SPEC, and development manifest. This is a new delta review, not a resend of any prior question.

The current patch intends to do exactly two bounded things before `seal_dispatch()` makes ACL or blindness decisions:

1. validate every CouncilBrief field that the canonical schema or P01 semantic contract requires, require canonical SemVer and SHA-256 syntax, then recompute `brief_hash` over the exact unnormalized supplied brief;
2. parse role IDs and `evidence_acl` entries as actual non-empty strings, reject duplicates, and never authorize through `str()` coercion.

The patch intentionally does not claim that ContextManifest self-hash proves authority. ContextManifest still lacks exact role-registry snapshot identity and immutable evidence-corpus/class binding; that remains a separate package-level gap.

Return only material findings:

- Any correctness or compatibility defect introduced by the current patch.
- Any path by which a modified brief can still reach ACL/blindness decisions without exact self-hash verification.
- Any CouncilBrief schema field still not validated before hash comparison.
- Whether the new role-registry parsing changes legitimate current registry behavior.
- Whether the patch improperly claims or partially invents ContextManifest authority.

Conclude `NO_BLOCKER` or list concrete blockers with the smallest P01-owned correction. Do not treat unrun tests or missing evidence artifacts as code defects, and do not approve the whole P01 package.
