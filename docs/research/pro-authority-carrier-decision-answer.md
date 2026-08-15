## Recommendation

**Ratify `NodeAttemptEffectTerminalProof` first**: one closed, E02-produced authority carrier that binds an exact scheduler attempt to the complete, hash-verified, publication-resolved set of `ActionIntent → E02 Attempt → EffectReceipt` chains and derives the only effect outcome N03 may consume.

Plainly:

* **N03 and A05-G14 are the same missing carrier wearing different names.**
* **A05-G01–G13 are not the same carrier.** They need gate-specific evidence resolution and deterministic verdict recomputation.
* W04 and Q05 are also distinct.

This decision gives the best runtime unlock per unit of contract change because E02 already owns most of the necessary authoritative facts. `ActionIntent` already binds `intent_id` to `run_id` and `node_id`; E02 already persists hash-bound Attempts, associates receipts with an exact E02 Attempt, enforces current-attempt and chronology constraints, and verifies publication state. The missing part is the cross-boundary binding to the scheduler’s `{run_id, node_id, attempt, input_hash}` and a canonical aggregate terminal proof.   

By contrast, N03 currently accepts caller-provided strings, requires only a nonempty receipt array for an effectful success, and then writes `SUCCEEDED`. Reconciliation similarly accepts a caller-selected outcome and arbitrary receipt identifiers.  

The decision also directly implements the existing receipt-bound-completion invariant rather than creating a new policy exception. EF4-I13 already requires resolving artifact/effect receipts for side effects and phase transitions. 

## Why this dominates the other three

| Blocker                                | Relationship to this decision              | Result after ratification                                                                                   |
| -------------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| **N03 effect-receipt resolution**      | Primary consumer                           | Becomes implementable without trusting receipt strings or caller outcomes                                   |
| **A05-G14**                            | Same post-effect carrier                   | Reclassified from a malformed pre-commit `GateDecision` into a post-commit `NodeAttemptEffectTerminalProof` |
| **A05-G01–G13**                        | Different authority problem                | Remains blocked; requires typed gate evidence and gate-specific recomputation                               |
| **W04 run inventory**                  | Different projection problem               | Remains blocked; checkpoints become safer inputs but still do not define the authoritative run inventory    |
| **Q05 selective-inference provenance** | Different source-input persistence problem | Remains blocked; `candidates_considered` and `replication_count` still must be carried canonically          |

This carrier unlocks more than N03 alone. The package graph places N03 beneath N04, then W01 and W02, with W04 downstream of W02. A trustworthy effect-terminal boundary therefore enables real scheduler, checkpoint-seal, resume, and replay work even though W04’s own inventory projection remains unresolved.    

Ratifying the A05 gate-evidence carrier first would not be as dependency-ready. It would require, at minimum, a governed type-to-evidence relation for every gate, trusted body resolution, per-gate recomputation rules, `GateDecision` canonicalization, and a separate repair for G14. A single generic “gate evidence resolver” would merely hide those missing semantics.

Q05 is a smaller local schema change, but it unlocks only Q05. W04 requires a new authoritative inventory projection, not just an additional field. The E02/N03 carrier is the only choice that resolves two concrete blockers and opens a substantial downstream runtime chain using facts already durably owned.

## Authority and ownership

Ownership must be split rather than conflated:

| Concern                                                              | Authority                                                  |
| -------------------------------------------------------------------- | ---------------------------------------------------------- |
| Carrier semantics and package ordering                               | `MASTER_SPEC.md`                                           |
| Canonical schema definition and generated projections                | `C01`                                                      |
| Authoritative intent, effect-attempt, receipt, and publication facts | `E02`                                                      |
| Proof construction and sealing                                       | `E02`                                                      |
| Scheduler transition consumption                                     | `N03`                                                      |
| Checkpoint seal/resume consumption                                   | `W02`                                                      |
| Post-commit G14 consumption                                          | `A05` workflow integration                                 |
| Role ACL projection                                                  | `manifests/role_registry.yaml`, last and non-authoritative |

Neither N03, W02, nor A05 may build the proof from caller-provided receipt IDs. They consume an E02-produced proof or fail closed.

### Required dependency changes

The dependency edits must be ratified in `MASTER_SPEC.md` first and then reproduced in `manifests/development_manifest.yaml`.

1. **Restore `C01.depends_on` to exactly `[A04]`.**
   The higher-authority package graph already places C01 directly after A04, whereas the current development manifest has added `A05`. That lower-authority edge must not be preserved merely because it is currently on disk.  

2. **Set `N03.depends_on` to `[N01, E02]`.**
   E02 is already a transitive predecessor, but the new direct runtime consumption should be explicit rather than hidden behind N01/E04.

3. **Set `W02.depends_on` to `[W01, E02]`.**
   W02 must compose checkpoint seal/resume with the same E02 proof producer. A constructor or runtime path that omits it must not silently fall back.

4. **Set `A05.depends_on` to `[A04, E02]`.**
   This dependency is for G14’s post-commit proof only. It does not make E02 an authority over G01–G13.

These edits must be atomic. Leaving the current lower-manifest `C01 → A05` edge while adding `A05 → E02` would create the dependency cycle:

```text
C01 → A05 → E02 → E01 → C04 → C01
```

Removing `C01 → A05` restores the higher-authority graph and makes the new direct edges acyclic. There is no need to make C01 depend on A05 merely because C01 defines schemas used by A05.

### Required write-scope changes

**C01**

Add to `write_scope`:

```text
schemas/node-attempt-effect-terminal-proof.schema.json
examples/sample_node-attempt-effect-terminal-proof.json
```

and the repository’s existing generated-projection and hash-vector destinations for canonical schemas.

C01 already governs `schemas/action-intent.schema.json`; extend that schema under the same package. **Do not add `schemas/node-invocation.schema.json` to this decision.** The current `NodeInvocation` already supplies `run_id`, `node_id`, `attempt`, and `input_hash`; the missing durable binding belongs in `ActionIntent`, not in another caller-carried evidence bag.

**E02**

Use the existing effects write scope for one exact producer, for example:

```text
packages/foundry-kernel/src/effects/node-attempt-effect-terminal-proof.mjs
```

The producer may use E02’s internal state and publication records. It is not a general artifact resolver.

**N03**

Modify the current scheduler terminal-transition implementation and its tests. Remove receipt IDs and effect outcome as caller authority.

**W02**

Modify checkpoint seal/resume composition and tests so the E02 proof producer is mandatory whenever an effectful attempt is terminal or replayed.

**A05**

Modify the G14 workflow node and corresponding evolution-authority integration so G14 emits or references `NodeAttemptEffectTerminalProof`, never `GateDecision` and never a bare `EffectReceipt`.

## Carrier shape

Use one closed schema with no caller-controlled extension fields.

### `ActionIntent` additions

Every effect intent associated with a scheduler node attempt must add:

| Field                 | Meaning                                                                                               |
| --------------------- | ----------------------------------------------------------------------------------------------------- |
| `node_attempt`        | Exact positive scheduler attempt number                                                               |
| `node_input_hash`     | Exact scheduler/`NodeInvocation.input_hash`                                                           |
| `expected_effect_ids` | Nonempty canonical set of effect obligations from that node’s compiled `expected_effects` declaration |

These fields become part of `intent_hash`.

An `ActionIntent` lacking these fields cannot satisfy the new carrier. Legacy values must not receive fabricated defaults. Migration is permitted only when the exact scheduler attempt, input hash, and expected-effect binding can be re-derived from immutable records; otherwise the record remains ineligible and causes `SPEC_GAP`.

The existing `EffectReceipt` does **not** need `node_id` or scheduler `attempt` added to it. Its `intent_id`, `run_id`, `idempotency_key`, status, and receipt hash are already bound through E02’s durable ActionIntent and Attempt journal. E02 currently verifies that a receipt resolves a durable Attempt and the current intent lineage.  

### `NodeAttemptEffectTerminalProof`

Minimum semantic fields:

```text
kind
schema_version
proof_id
run_id
node_id
node_attempt
node_input_hash
expected_effect_ids
expected_effects_hash
intent_resolutions[]
terminal_outcome
proof_hash
```

Each `intent_resolutions[]` entry contains:

```text
expected_effect_ids
intent_id
intent_hash
effect_attempt_id
effect_attempt_hash
terminal_receipt_id
terminal_receipt_hash
terminal_receipt_status
```

The array has canonical ordering, such as by `intent_id`. Ordering is part of the C01 hash contract and is never caller-selected.

### Exact completeness rule

For the supplied canonical compiled node and scheduler attempt:

1. Every `expected_effect_ids` member declared by the compiled node must be covered by at least one pre-effect `ActionIntent`.
2. Every ActionIntent registered to the exact `{run_id, node_id, node_attempt, node_input_hash}` must appear exactly once in `intent_resolutions[]`.
3. The union of the ActionIntents’ `expected_effect_ids` must equal the compiled node’s exact expected-effect set.
4. No intent from another run, node, attempt, input hash, or compiled expected-effect set may appear.
5. Every intent must resolve to its durable E02 Attempt lineage.
6. Every listed terminal receipt must be the current terminal receipt for that E02 Attempt.
7. Every receipt and its referenced artifacts must pass E02 integrity verification.
8. Every resolving ledger event and publication checkpoint must be confirmed.
9. No unresolved `UNKNOWN` state or `reconciliation_required: true` may be hidden inside a terminal proof.

This closes the omission attack: E02 does not merely verify the caller’s supplied receipt subset. It enumerates the entire prebound intent set for the exact scheduler attempt and reconciles that set against the compiled node’s expected effects.

### Supplied versus re-derived

The proof-construction port receives only the canonical lookup context:

```text
run_id
node_id
node_attempt
node_input_hash
expected_effect_ids
expected_effects_hash
```

The `expected_effect_ids` and hash must come from N03’s compiled plan, not from the executor result.

E02 then re-derives:

* the matching ActionIntent set;
* every `intent_hash`;
* every E02 Attempt and `attempt_hash`;
* every current terminal EffectReceipt and `receipt_hash`;
* exact expected-effect coverage;
* exact receipt membership;
* publication completion;
* `terminal_outcome`;
* `proof_hash`;
* `proof_id`, under the C01 identity rule.

The executor, scheduler caller, checkpoint caller, and A05 workflow may not supply:

* intent IDs;
* effect-attempt IDs;
* effect-receipt IDs;
* receipt statuses;
* completeness counts;
* terminal outcome;
* proof identity.

A suitable narrow semantic port is:

```text
resolveNodeAttemptEffects(
  run_id,
  node_id,
  node_attempt,
  node_input_hash,
  expected_effect_ids,
  expected_effects_hash
) -> NodeAttemptEffectTerminalProof | RECONCILIATION_REQUIRED
```

This is one purpose-specific E02 operation, not a general resolver framework.

## Effect-status to scheduler-transition matrix

The matrix is limited to effect authority. It does not replace ResultEnvelope validation or define all non-effect terminal receipts.

| E02-derived condition                                                                                                      | Permitted N03 treatment                                                                                         |
| -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| All required intents covered; all current terminal receipts `SUCCEEDED`; publication confirmed; no reconciliation required | `SUCCEEDED`, provided the ordinary node result also validates                                                   |
| Missing intent, missing receipt, `UNKNOWN`, unconfirmed publication, or `reconciliation_required: true`                    | `RECONCILING`; no terminal proof                                                                                |
| Any terminal receipt `FAILED`                                                                                              | Existing retry/final-failure policy; never `SUCCEEDED`                                                          |
| Any terminal receipt `ROLLED_BACK`                                                                                         | Never `SUCCEEDED`; `CANCELLED` only with independently authorized cancellation, otherwise `FAILED_FINAL`        |
| Any terminal receipt `NOT_EXECUTED`                                                                                        | `KNOWN_NO_EFFECT` only when the compiled node contract explicitly permits no effect; otherwise terminal failure |
| Unknown receipt status, mixed state not covered by the matrix, or inability to derive one outcome                          | `SPEC_GAP`                                                                                                      |

Outcome precedence must be deterministic:

```text
unresolved/missing
  > FAILED
  > ROLLED_BACK
  > NOT_EXECUTED
  > all SUCCEEDED
```

The caller cannot select `EFFECT_SUCCEEDED`, `NO_EFFECT`, or `FAILED_FINAL`.

### N03 storage rule

For an effectful attempt:

* the canonical effect authority stored by N03 is `{proof_id, proof_hash}`;
* `effect_receipt_ids` are derived from the proof;
* caller-provided `effect_receipt_ids` are rejected;
* a legacy `terminal_receipt_id` string cannot establish effect completion.

The existing legacy terminal-result field may remain temporarily as a projection for the ordinary node result, but it cannot influence the effect transition without a valid proof.

### W02 checkpoint rule

W02 may seal or resume a checkpoint only after applying the same proof:

* `pending_effect_ids` is derived from E02 state, not a caller array;
* `replay_verified: true` is forbidden when E02 cannot produce a terminal proof for every effectful terminal attempt;
* no configured E02 proof producer means `SPEC_GAP`, not an empty pending set;
* a `RECONCILIATION_REQUIRED` attempt remains pending across checkpoint and resume.

## G14 treatment

G14 must cease pretending to be part of the pre-commit `GateDecision` family.

The correct sequence is:

```text
G01–G13 authoritative pre-commit decisions
→ promotion decision
→ effect intent and commit attempt
→ durable EffectReceipt publication
→ E02 NodeAttemptEffectTerminalProof
→ G14 post-commit reconciliation state
```

Therefore:

* G14 output schema becomes `schemas/node-attempt-effect-terminal-proof.schema.json`.
* Its actual output cannot be a bare `EffectReceipt`.
* G14 cannot be required before commit.
* G14 cannot retroactively convert a failed G01–G13 decision into a pass.
* Failure to obtain the proof leaves promotion in an explicit reconciliation-required state; it does not imply successful completion.

The current workflow already treats G14 differently from ordinary gate-decision nodes, which supports making the distinction explicit rather than forcing it into the G01–G13 shape. 

## Ratification order

Apply changes strictly in the stated authority order:

1. **`MASTER_SPEC.md`**

   * Define `NodeAttemptEffectTerminalProof`.
   * Define E02 fact and proof authority.
   * Define N03/W02 consumption.
   * Reclassify G14 as post-commit effect reconciliation.
   * Ratify dependency changes and fail-closed behavior.

2. **`manifests/development_manifest.yaml`**

   * Restore `C01 → A04`.
   * Add direct E02 dependencies to A05, N03, and W02.
   * Extend C01, E02, N03, W02, and A05 scopes, exit criteria, and checks.

3. **`manifests/acceptance_matrix.yaml`**
   Add mandatory negative cases for:

   * unrelated but valid EffectReceipt;
   * correct receipt from the wrong run/node/attempt/input;
   * omitted ActionIntent;
   * duplicate or extra intent;
   * expected-effect coverage mismatch;
   * tampered intent, Attempt, receipt, or proof hash;
   * stale receipt rather than current terminal receipt;
   * missing publication confirmation;
   * `UNKNOWN` re-labelled as success;
   * `ROLLED_BACK` or `NOT_EXECUTED` re-labelled as success;
   * caller-supplied receipt set or terminal outcome;
   * absent E02 producer in N03 or W02;
   * checkpoint seal with unresolved effects;
   * G14 proof requested before commit.

4. **`manifests/product_invariants.yaml`**
   Extend EF4-I13:

   * add the new proof schema as an evidence artifact;
   * add N03, W02, and A05-G14 to its work-package coverage;
   * state that an identifier alone is not a resolving receipt.

5. **Schemas and workflow**

   * Extend `ActionIntent`.
   * Add the proof schema.
   * Correct G14’s output contract.
   * Generate projections and migration vectors under C01/C02/C03 rules.

6. **`manifests/role_registry.yaml`**
   Project only the already-ratified producer/consumer permissions. It must not define proof semantics, owner authority, or fallback behavior.

## Interim A05 posture

**Yes. Change G01–G13 from silent pass-through to explicit fail-closed `SPEC_GAP` stubs immediately.**

That is the correct trade even though existing integration fixtures will stop.

The stub must:

* ignore the caller’s claimed verdict as authority;
* never return the caller’s `GateDecision` unchanged;
* never copy a caller-provided evidence ID into an apparently authoritative decision;
* return a locally produced non-granting `SPEC_GAP`;
* identify the unresolved gate-evidence contract;
* make promotion impossible.

G14 should likewise return an explicit post-commit-carrier `SPEC_GAP` until this proof is ratified and wired.

The existing successful-promotion fixtures should not be deleted. Convert them into negative regression fixtures demonstrating that a self-consistent forged decision cannot reach `PROMOTE CANDIDATE`. Fixtures that require a working promotion path may remain quarantined as blocked integration scenarios, but they must not preserve silent pass-through behavior.

This follows the higher-authority rule that ambiguous shared semantics fail as `SPEC_GAP`; preserving an unsafe fixture is not a reason to keep a live authority bypass. 

## What this decision does not fix

After this carrier ships, the following remain honestly blocked:

1. **A05 G01–G13 evidence authority**

   * no canonical evidence-body carrier;
   * no gate-specific type-to-evidence contract;
   * no trusted gate evidence resolution;
   * no deterministic gate recomputation;
   * no fixed `gate_id`, evaluation-time, ordering, or `input_hash` semantics.

2. **A05 end-to-end promotion reachability**

   * G14 becomes well-typed, but promotion remains blocked while G01–G13 are `SPEC_GAP`.

3. **W04 authoritative run-reference inventory**

   * no canonical producer of the four export sections;
   * no persisted authoritative `referenced` inventory;
   * checkpoints remain insufficient as inventory authority.

4. **Q05 selective-inference provenance**

   * `candidates_considered` and `replication_count` remain absent;
   * risk and recommendation can still be reconstructed only after a separate schema/source-input ratification.

5. **Generic non-effect terminal-receipt typing**

   * this decision defines effect-terminal authority;
   * it does not settle every possible non-effect `terminal_receipt_id` representation.

6. **Runtime composition**

   * the contract makes the E02→N03/W02 composition implementable;
   * it does not itself prove that the composition root, checkpoint wiring, migration, or all workflows are reachable.

7. **Acceptance or completion**

   * no package PASS, release, implementation completion, or end-to-end runtime claim follows from this advisory decision alone.

The resulting order is therefore honest: first ratify the E02-issued node-attempt effect proof; immediately close A05’s forged-promotion path with `SPEC_GAP`; then treat the G01–G13 gate-evidence carrier, W04 inventory projection, and Q05 source-input provenance as three separate remaining authority decisions.
