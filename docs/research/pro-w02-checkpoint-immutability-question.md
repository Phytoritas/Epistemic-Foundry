We are continuing the Epistemic Foundry v4 implementation against MASTER_SPEC.md.

Please adjudicate one bounded W02 production defect only. Do not approve W02 as a whole and do not invent a shared contract.

Current code: packages/foundry-kernel/src/workflows/runtime/checkpoint-runtime.mjs

- sealCheckpoint() constructs a CheckpointManifest whose five array fields are hash-covered: artifact_ids, expected_node_ids, gate_decision_ids, pending_effect_ids, terminal_node_ids.
- It freezes only the outer manifest object. The arrays remain mutable.
- validateCheckpointManifest() rebuilds those arrays, verifies checkpoint_hash, then again freezes only the outer object.
- cancelRun() returns pending_effect_ids as a direct alias of sealed.manifest.pending_effect_ids.

Consequence: a caller can mutate a returned hash-covered array after sealing/validation, leaving checkpoint_hash stale and making a previously reviewed checkpoint fail later resume validation.

Proposed smallest W02-local repair: add one local helper that freezes each of the five arrays and then the manifest object; use it in both sealCheckpoint() and validateCheckpointManifest(). Preserve array content/order and canonical hash bytes. Do not change schemas, ABI, scheduler, cancellation semantics, or tests.

Question: Is this repair AUTHORIZED within W02, or is there a SPEC_GAP? Identify any compatibility or hash-identity constraint the exact helper must preserve. Give a concise verdict and smallest safe implementation shape.
