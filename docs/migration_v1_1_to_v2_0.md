# Migration from v1.1.0 to Epistemic Foundry v2.0.0

## Scope

This migration converts the prior domain-neutral bundle into the **Epistemic Foundry** product language and strengthens contracts. It is a specification migration, not an automatic production database migration.

## Canonical renames

| v1.1 concept | v2.0 canonical name |
|---|---|
| prior product label | Epistemic Foundry |
| provider-neutral runtime | Foundry Kernel |
| claim extraction | Claim Forge |
| coverage interface | Epistemic Atlas |
| asymmetric council | Evidence Parliament |
| contradiction/abduction engine | Aporia Engine |
| artifact/event/provenance authority | Noetic Ledger |
| Python package | `epistemic_foundry` |
| CLI | `efoundry` |

## Contract changes

1. Canonical schemas expand from 17 to 48.
2. Provider-neutral workflows expand from 4 to 7.
3. Product invariants expand from 15 to 25.
4. SearchLaneReceipt and RetrievalRun become mandatory before absence or novelty language.
5. Claim, Passport, and human decision state becomes append-only and lifecycle-aware.
6. SourceIntegrityReport and hostile-document handling become mandatory.
7. ActionIntent and EffectReceipt become mandatory for side effects.
8. SchemaMigration becomes mandatory before a breaking contract change.
9. Evidence updates, corrections, and retractions trigger targeted reassessment.
10. Release claims require the 144-lens audit, independent attestation, final-byte manifest, and checksum verification.

## Repository migration order

1. Freeze the v1.1 corpus, schemas, workflows, prompt hashes, and database snapshot.
2. Install v2 schemas alongside v1.1; do not overwrite old `$id` values in place.
3. Validate every `SchemaMigration` fixture and classify compatibility.
4. Migrate immutable artifact and event records before projections.
5. Rebuild source, claim, evidence, coverage, and deliberation projections from the ledger.
6. Reissue current Passports as new revisions; preserve all prior IDs and decisions.
7. Run `python tools/validate_spec_bundle.py` and `python tools/run_144_lens_audit.py`.
8. Start implementation with A01 only; release additional work packages by dependency and integration gate.

## Prohibited shortcuts

- Renaming database columns without a migration record.
- Reusing a v1.1 hash for changed bytes.
- Marking old decisions as deleted instead of superseded or stale.
- Labeling a specification validation as production readiness.
- Running a bulk migration without rollback fixtures and a verified backup.
