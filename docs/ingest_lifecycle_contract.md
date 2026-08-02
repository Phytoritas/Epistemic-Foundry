# Document ingest lifecycle contract

K01 separates three immutable artifacts that represent different lifecycle moments:

1. `DocumentRegistrationRequest` seals the caller's registration intent and the ID of an already staged source artifact.
2. `DocumentRegistration` proves that immutable source bytes, the caller's license/access declaration, resolving receipts, a ledger event, and a fenced CAS commit were reconciled.
3. `DocumentManifest` is built later, after integrity scanning, metadata resolution, parsing, reconciliation, and source-span emission. It is never required as input to `register_document`.

## Authority boundary

`register_document` computes canonical request and registration semantics only. It has no default repository or in-memory fallback. D03 owns content-addressed bytes and `ArtifactReceipt`; E01 owns the Noetic Ledger event; E02 owns `ActionIntent`, attempts, idempotency, and `EffectReceipt`; E03 owns capability leases and fencing; the shared revision store owns CAS state. K01 receives these authorities through required `RegistrationPorts` adapters.

`source_origin.original_uri` records acquisition provenance. K01 never interprets it as a fetch command, never reads `file:` URIs, and never discovers bytes from the current directory or repository root. The staged artifact and its resolving receipt are the only byte source.

## Hash and identity rules

Both hashes use deterministic canonical JSON encoded as UTF-8. Identifier hints must be stored in canonical JSON order. `requested_at`, `registered_at`, receipt IDs, event IDs, and request IDs do not enter their respective semantic hash unless the canonical schema's preimage table explicitly names them.

- `request_id = DREQ-<request_hash hex>`
- `registration_id = DREG-<registration_hash hex>`
- `initial_state = REGISTERED_UNSCREENED`

No placeholder digest is accepted. A mismatch between bytes, a manifest projection, an ArtifactReceipt, an EffectReceipt, or a hash-bound ID is a typed failure.

## Receipt-bound sequence

The node validates the `NodeInvocation`, resolves and validates the request artifact, verifies `input_hash == request_hash`, validates the current capability lease and fencing token, and checks idempotency before producing effects. It then resolves staged bytes and asks E02 to reserve a canonical `ActionIntent` whose `action_type` is `register_document_source`, whose risk class is `controlled_effect`, and whose exact capabilities are `artifact_write` and `document_register`. K01 validates that intent's self-hash and run, node, target, request artifact, request hash, idempotency, capability, and risk bindings before it publishes the source blob. It then records and verifies the resolving source `EffectReceipt`, builds and publishes the immutable registration, appends the reserved E01 event, and performs the lease-bound CAS. A success `ResultEnvelope` is emitted only after all evidence reopens and reconciles.

A crash can leave an immutable source blob, registration artifact, or ledger event before the active state is committed. Those objects are evidence, not success. Retry uses the same idempotency binding and shared reservations. If a committed record lacks any resolving receipt/event/CAS evidence, the state adapter must reconcile it; otherwise K01 returns `DOCUMENT_RECONCILIATION_REQUIRED`.

The same idempotency key and request hash return the original immutable registration, timestamp, and evidence. Replay resolves the original canonical `ActionIntent` from E02 and revalidates its full payload, self-hash, and request/effect bindings; an intent ID alone is not sufficient evidence. Reusing the key with another request hash returns `DOCUMENT_IDEMPOTENCY_CONFLICT`.

## Lineage and lifecycle state

`supersedes_registration_id` must resolve to a valid registration in the same workspace and corpus. Self-reference, unknown predecessors, and cycles fail closed. Existing registrations are never edited. Correction, retraction, version, quarantine, and release state are append-only events and downstream projections.

The initial declaration retains `license_status`, `access_policy_ref`, and `confidentiality` exactly. `open_access` does not imply unrestricted content export, and `unknown` is never promoted to a more permissive status.

## Legacy records

A final legacy `DocumentManifest` does not prove the earlier registration effect. Migration requires a canonical request plus immutable source, artifact receipt, effect receipt, event, lineage, and timestamp evidence. If any exact binding is unavailable, migration fails with `LEGACY_DOCUMENT_REGISTRATION_EVIDENCE_REQUIRED`; it never inspects the current environment or fabricates a historical pin.

`ResultEnvelope` is execution telemetry. The canonical business truth remains the immutable `DocumentRegistration` resolved by its ArtifactReceipt and ledger/CAS evidence.
