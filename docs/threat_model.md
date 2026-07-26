# Threat model

## Protected assets

- original source bytes and source locators,
- Claim/Evidence integrity,
- policy and capability authority,
- secrets and private corpus access,
- human approvals,
- action/effect records,
- release and provenance manifests,
- evaluation holdouts.

## Adversaries and failure sources

- malicious or instruction-bearing PDFs and supplementary archives,
- poisoned metadata or citations,
- compromised external index or tool response,
- prompt injection through source text,
- model fabrication and citation laundering,
- stale or duplicated workers,
- shared-write race conditions,
- unauthorized side effects,
- dependency or build compromise,
- accidental leakage of holdout labels or confidential documents,
- overprivileged provider adapters.

## Controls

1. content-addressed immutable storage,
2. SourceIntegrityReport and quarantine,
3. untrusted-data delimiters and ContextAssemblyManifest,
4. schema validation and strict IDs,
5. least-privilege capabilities,
6. worktree and sandbox isolation,
7. leases and fencing tokens,
8. exact-hash ActionIntent and EffectReceipt,
9. secret redaction and no-secret artifacts,
10. SBOM, dependency locks, build provenance, checksums,
11. append-only audit events,
12. adversarial-source and leakage evaluations.

## Non-goals

The architecture cannot guarantee that all scientific fraud, publication bias, or sophisticated parser exploits will be detected. It must expose uncertainty and fail closed at promotion and execution boundaries.
