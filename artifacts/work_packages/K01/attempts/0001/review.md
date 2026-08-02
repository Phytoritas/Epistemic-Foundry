# K01-0001 contract review

## Outcome

`K01-0001` is `SPEC_GAP` (`K01-SG001`). The four provisional K01 files are retained with `implementation_status: PROVISIONAL_VERIFIED`; the package is not `PASS`, and `completion_ready` remains `false`.

## Blocking finding

The canonical `corpus_ingest` workflow starts with `register_document`, whose stated purpose is to register source bytes, license metadata, and a content hash. Integrity scanning, metadata/version resolution, parser execution, reconciliation, and SourceSpan emission occur later. Only after those steps does `build_document_manifest` create the canonical `DocumentManifest` and provenance chain.

The provisional K01 API instead requires a complete final `DocumentManifest` at registration time. That schema requires later-node results including `parser_artifact_ids`, `source_integrity_report_id`, scan statuses, resolved bibliographic lifecycle metadata, and `provenance_manifest_id`. The first node therefore cannot truthfully consume the only canonical artifact currently available for the registry. Defaulting, fabricating, or prematurely sealing those values would corrupt provenance.

The workflow additionally declares `NodeInvocation` input and `ResultEnvelope` output, while the provisional function accepts an in-memory registry, bytes, and final manifest and returns `DocumentRegistration`. The authority for durable source storage, registry persistence, effects, receipts, and ledger events is not assigned across K01, D03, and the caller. The manifest component root also lacks an authorized adapter contract to the installable `src/epistemic_foundry` runtime.

These are shared-contract and ownership questions outside K01's exact product write scope. They cannot be repaired by weakening `DocumentManifest`, inventing an initial artifact, or adding an implicit source-tree fallback.

## Provisional implementation review

Within its assumed final-manifest boundary, the implementation has no blocking correctness finding: source bytes are copied and SHA-256 verified; identity and version lineage are append-only; retries are idempotent; conflicts fail closed; and license/access restrictions propagate exactly without interpreting `open_access` or `unknown` as additional authority. The targeted gate is 34/34 (`document_registry_test` 22/22 and `license_propagation_test` 12/12).

This does not resolve the lifecycle mismatch or authorize production persistence and workflow integration.

## Regression boundary

The current full Python suite is 960 passed / 4 failed, with the four failures owned by the unresolved J02 exact-tokenizer lock. The full Node suite is 436 passed / 1 failed, with only the existing S04-TM004 manifest-hash traceability failure. K01 caused no identified Python or Node failure, added no skip or xfail, and passed repository structure, boundary, and `git diff --check` checks.

## Required product-owner decision

The resolving decision must define the initial source-registration artifact and its exact fields; its immutable relationship to the final `DocumentManifest`; the business and envelope input/output of `register_document`; durable persistence, effect, receipt, and ledger ownership; the installable runtime adapter; and the minimum exact workflow/schema/runtime/persistence/test write scopes and owners.

## RAH and assurance limitation

RAH remains read-only and blocked at generation `000081-843d5565` by the pre-existing J02 tokenizer-lock and S04 traceability failures. The current generation manifest and all six payload hashes match, but K01 appended no RAH evidence and created no generation.

The product owner prohibited Fleet and subagents. This is a procedurally separate primary-session adversarial review, not actor-independent certification.
