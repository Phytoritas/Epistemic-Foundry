# Skill Vault quarantine boundary

`src/skill-vault.mjs` implements the S03 security boundary around third-party
skills. Candidate files enter as inert bytes, receive a normalized tree hash,
and remain `QUARANTINED`, non-executable, non-active, and non-authoritative.
The deterministic static scan inventories executable and linked content and
reports conservative risk signals; it does not claim exhaustive malware
detection or production sandbox coverage.

Candidate-provided signature metadata remains an untrusted claim. The
privileged review issuer must attest the signature status separately. An
approval binds the exact source, revision, content hash, attested signature
status, reviewed license, permissions, scan inventory, and external reviewer
identities. Critical scan findings and failed signatures cannot be approved.
The resulting object has the exact canonical
`schemas/skill-lockfile.schema.json` field shape. In lockfile version 1,
`lock_hash` is SHA-256 over the UTF-8 canonical JSON of all lockfile fields
except `lock_hash`, with object keys sorted, arrays already normalized, and the
domain `epistemic-foundry.skill-lockfile.v1` separated by a NUL byte.

The module does not fetch, write, install, import, evaluate, or execute remote
content. A trusted adapter may attest that exact locked bytes were installed in
a disabled state and that isolated conformance passed. Only then can the guard
issue a runtime-private, explicit activation authorization. That authorization
still performs no effect; later effect/receipt integration remains separate.

`createSkillVaultBoundary()` creates a private authority compartment. Kernel
bootstrap code must retain its `issuer` and expose only the required `guard`
methods. Objects from another compartment, copied objects, and JSON-round-trip
objects do not carry authority. A serialized SkillLockfile can be integrity
checked, but this S03 primitive deliberately cannot rehydrate approval
authority without a future trusted Ledger/provenance adapter.

Required checks:

```text
node --test packages/skill-vault/src/malicious-skill-fixture.test.mjs
node --test packages/skill-vault/src/skill-lockfile.test.mjs
```
