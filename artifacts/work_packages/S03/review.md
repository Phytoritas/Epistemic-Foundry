# S03 review record

Status: `PASS`

Review mode: `USER_EXPLICIT_INDEPENDENT_APPROVAL`

The user is external to the package author and explicitly stated in the active
goal that all independent reviews are approved (`독립 검토는 모두 승인한다`).
That external human authority decision is recorded here as approval of S03 for
the exact revisions listed below after the objective checks were rerun on
2026-07-27. The approval is limited to this dependency checkpoint and becomes
stale if any reviewed hash changes, any cited command record is invalidated, or
a later security finding contradicts the reviewed evidence.

The technical review below was performed by the primary author under the
user's no-subagent constraint. This record does not claim that a separate agent
or `contract_reviewer` performed another technical audit. It distinguishes the
author-produced technical evidence from the user's independent external
approval decision.

Reviewed implementation hashes:

- `packages/skill-vault/src/skill-vault.mjs`: `f3308719bfdfc400c25fce95fa2c089c99a73192e0c48dc35a936ff6025564b3`
- `packages/skill-vault/src/malicious-skill-fixture.test.mjs`: `135b5c56730d2e8f1bde0122220ee41553746995f9dd9bbc385a0fbaf6f0f83e`
- `packages/skill-vault/src/skill-lockfile.test.mjs`: `c4d75c2f065596b8a01a18d38b1c833e76d5695ac499f59939791f03a9dd0120`
- `packages/skill-vault/README.md`: `6907fcb559b70176f31deb07c3a10710e83d8e51f10bd3d7722dc863255244a1`

Resolved author-review findings:

- `S03-RF001` — The first review path copied candidate-supplied signature
  metadata into the lockfile. A remote candidate could therefore describe its
  own signature as verified. Candidate metadata is now explicitly a claim;
  the privileged review issuer must attest `signatureStatus` separately, and
  a failed status cannot be approved.
- `S03-RF002` — Serialized lockfile validation initially sorted permission and
  approver arrays before checking them, hiding non-canonical input order. The
  validator now checks the input order first. All canonical ordering and hash
  serialization use UTF-8 byte comparison rather than locale collation.
- `S03-RF003` — Activation originally constrained requested permissions only
  to the lockfile. It now also requires every requested permission to have
  appeared in the passing conformance observation, preventing activation of a
  locked but untested capability.
- `S03-RF004` — Executable inventory initially depended on a caller-provided
  executable flag. Script/executable extensions and shebangs are now
  inventoried independently and infer `process_execute` permission even when
  the flag is absent.
- `S03-RF005` — The first hostile fixture exposed a PowerShell `$env:` scan
  boundary error, and failed signature metadata was not an independent scan
  finding. The expression and critical finding were corrected, and both paths
  have regressions.

Author review confirmed:

1. Candidate material enters as copied inert bytes. The module contains no
   fetch, filesystem mutation, dynamic import, evaluation, process launch,
   environment read, network request, or candidate execution primitive.
2. Candidate records, scans, reviews, lockfiles, disabled installations,
   conformance reports, and activation authorizations use private per-boundary
   brands. Copied, serialized, Proxy-wrapped, accessor-bearing, and foreign
   objects cannot acquire runtime authority.
3. Portable relative paths reject traversal, absolute or mixed separators,
   reserved Windows aliases, ambiguous components, and case/normalization
   collisions. Symlinks are recorded without traversal and are critical.
4. Normalized tree hashing includes every path, kind, executable indicator,
   byte sequence, and symlink target with length framing and domain separation.
   Inventory and SkillLockfile hashes use separate domains.
5. Static scanning inventories executable/script-shaped content and reports
   install hooks, dynamic evaluation, process, network, secret/environment,
   filesystem, obfuscation, binary, symlink, and self-authority signals. It is
   conservative inspection, not claimed as exhaustive malware detection.
6. Approval binds the exact source, revision, content hash, scan inventory,
   separately attested signature status, license, permissions, rationale, and
   external reviewer identities. Critical findings and failed signatures block
   approval; inferred permissions cannot be omitted.
7. SkillLockfile output uses only the fields and enum values in
   `schemas/skill-lockfile.schema.json`. Entries, permissions, and approver IDs
   are unique and canonical. `lock_hash` covers every field except itself with
   a documented v1 domain-separated canonical JSON rule.
8. Serialized lockfiles can be integrity-checked but are explicitly
   non-authoritative. S03 does not rehydrate approval authority without a
   future trusted Ledger/provenance adapter.
9. Installation is permitted only for an approved exact hash and remains
   disabled. Name collisions are visible and block passing conformance.
   Passing conformance requires no undeclared capability, explicit-only
   invocation, and verified uninstall behavior.
10. Activation requires a matching lockfile, disabled installation, passing
    conformance, current policy hash, exact subject identity, and a permission
    set contained in both the lock and conformance observation. The branded
    authorization performs no activation effect.
11. Both required suites pass with 21 tests. Coverage is 93.39% lines, 79.30%
    branches, and 100% functions; the integrated S01–S03 suite has 56 passing
    tests.
12. Workspace structure/boundary checks, all 789 Python tests, and the
    11-artifact byte-identical double build pass. The reproducible Skill Vault
    tarball contains the implementation, tests, and documentation.

Open implementation-scope findings: none found by the author.

Resolved independent-approval finding:

- `S03-RB001` — Resolved by the user's explicit external human approval,
  bound to the exact hashes above and fresh command evidence `S03-C015` through
  `S03-C019`. The author did not self-approve. This approval is automatically
  invalidated by source drift or a regression in the cited checks.

Scope limits retained for later packages:

- This S03 primitive does not fetch from a catalog, verify a cryptographic
  signature, install files, run a sandbox, activate a skill, write a lockfile,
  append Ledger events, or issue effect receipts. Trusted adapters must perform
  and receipt those effects using the branded decisions.
- Static signals are defense in depth, not an exhaustive malware detector.
  Production catalog and package variations, isolated dynamic analysis, and
  uninstall behavior remain external evidence and S04/Z02 integration work.
- The canonical schema leaves permission strings open. S03 pins exact reviewed
  strings but does not invent a shared permission vocabulary.
- The package remains a private scaffold with no public export map; API
  stabilization and integration are later work-package scope.
