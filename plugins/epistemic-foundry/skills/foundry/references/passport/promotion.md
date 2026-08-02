# Passport and promotion

- A `HypothesisPassport` is an immutable provenance view over claims, evidence, limits, validation, replication, gates, and decisions.
- Promotion levels are `INBOX`, `CANDIDATE`, `LITERATURE_GROUNDED`, `VALIDATION_SCREENED`, `EMPIRICALLY_TESTED`, and `REPLICATED`.
- `PROMOTE` grants the requested level; `CONDITIONAL` grants a strictly lower but higher-than-current level. Non-grant decisions use `granted_level: null`.
- Replication, leakage, method, statistics, Parliament, attestation, policy, and receipt gates impose ceilings; no scalar score overrides them.
- Promotion commits use expected revisions, capability leases, receipts, and immutable new Passport and decision revisions.
