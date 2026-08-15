# SPEC_GAP

**Option 2 is the more faithful architecture and the one that minimizes long-term contract duplication, but the current authority corpus does not yet authorize it.**

`MASTER_SPEC.md` places canonical state, capability, effect, checkpoint, and replay authority in the Foundry Kernel and Noetic Ledger, while describing A05 as the “Evolution authority boundary and scientific promotion charter.” The A05 charter is even more explicit: its verifier is contract evidence only, and **later runtime packages** are to implement idempotency, CAS, reconciliation, and ledger commits.  

The development manifest conflicts with that separation. It gives A05 ownership of `promotion.py`, `cas.py`, `reconciliation.py`, and `workflows/evolution_promotion.workflow.yaml`, but names no post-E04 integration owner. Meanwhile E03 owns Kernel capability leases and fencing, and E04 owns strict and semantic replay.  

Option 1 cannot be adopted merely by adding E03/E04 dependencies to A05. It would introduce the static cycle:

```text
A05
→ E04
→ E03
→ E01
→ C04
→ C02
→ C01
→ A05
```

Thus neither existing ownership nor a local dependency edit safely selects a runtime owner.

## Single required product decision

The product owner must make this one decision:

> **Freeze A05 as charter and deterministic contract-verification authority only, and establish one explicitly named post-E04 promotion-integration work package, dependent on A05 and E04, with sole ownership of the Python-to-Foundry-Kernel promotion composition and the three commit-phase workflow bindings. E03 and the Foundry Kernel remain the sole capability-lease, fencing, persisted-CAS, ledger, effect, and replay authorities.**

The package ID and its exact source root must be named by that decision; deriving either from the current tree would invent ownership. This is Option 2. Its adapter composes existing authorities—it must not implement a second Python lease engine, fencing head, CAS store, or receipt ledger.

## Authority surfaces that must change first

| Surface                                       | Required authority change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MASTER_SPEC.md`                              | Add the named integration package and its `A05 + E04` dependency; state that A05 does not execute production promotion commits; update the work-package inventory/count and any downstream dependency references.                                                                                                                                                                                                                                                                                                                                       |
| `manifests/development_manifest.yaml`         | Amend A05’s scope so its models, registry, charter verifier, and pure gate checks remain A05-owned, while production commit composition, CAS/reconciliation integration, and workflow binding move to the new package. Add that package’s exact disjoint source path, dependency set, exit criteria, checks, and rollback boundary. Do **not** add E03/E04 directly to A05.                                                                                                                                                                             |
| `workflows/evolution_promotion.workflow.yaml` | Preserve all 23 nodes, gate order, and the single `promotion:commit` holder. Retarget only `acquire_promotion_commit_lease`, `commit_promotion_atomically`, and `reconcile_commit_receipts` to the new integration entrypoints. The commit node must consume the lease produced by the acquire node; reconciliation alone may complete G14. The workflow version/hash and derived registries must advance without rewriting historical workflow bytes. The current workflow instead targets the non-owning `evolution_authority.nodes` module.          |
| Canonical schemas                             | No integration-local request or result schema is authorized. C01 must explicitly prove that the existing closed surfaces can carry the binding, or version them before runtime work: `action-intent`, `capability-lease`, `phase-artifact-set`, `promotion-decision`, `hypothesis-passport`, `event-record`, `effect-receipt`, `artifact-receipt`, and `gate-decision`, transported through the canonical `node-invocation` and `result-envelope` contracts. Any necessary schema-byte change remains C01/C03 work, not integration-package discretion. |

The charter already fixes the sequence: commit `ActionIntent`, short-lived lease, expected-revision CAS, immutable PromotionDecision and Passport revision, Ledger event, resolving receipts, and G14 only after reconciliation. It also fixes same-key replay, different-request conflict, and unknown-outcome recovery. 

## Minimum provider-neutral invocation/result contract

**Invocation binding**

The adapter must receive or resolve, by canonical ID and hash:

* the `NodeInvocation` run, node, attempt, and input identity;
* `ActionIntent(action_type=commit_promotion)`, including its idempotency key and full arguments hash;
* the sealed phase-E `PhaseArtifactSet` and promotion-pack hash;
* exact candidate and Passport identities plus expected revisions;
* requested and grantable promotion levels;
* the G00–G13 decisions, policy bundle, Parliament adjudication, independent attestation, and applicable approval records;
* the lease ID/hash emitted by the immediately preceding acquire node.

`ActionIntent` already provides the canonical action, target, arguments-artifact, arguments-hash, idempotency, capability, approval, and intent-hash bindings. 

The adapter must then ask a trusted Kernel port to resolve the persisted lease and invoke the Kernel transaction. The caller may not establish lease validity by supplying a shape-valid object. The Kernel must verify the authenticated principal, workspace/target scope, exact `promotion:commit` capability, issuance and expiry, revocation/use state, current fencing token, request binding, and CAS preconditions. The existing OpenAPI authority already restricts this lease to a short post-G00–G13 grant that candidate, model, prompt, and backend identities cannot hold. 

**Result binding**

The provider-neutral result must distinguish, semantically rather than through newly invented local enums:

* newly committed;
* idempotently replayed;
* expected-revision or request-hash conflict;
* denied, expired, revoked, or fenced lease;
* outcome unknown and requiring reconciliation;
* final integrity failure.

A successful or replayed `ResultEnvelope` must resolve the immutable PromotionDecision, new Passport revision, corresponding EventRecord, lease-use record, EffectReceipt, and ArtifactReceipt, together with the canonical request hash and observed pre/post revisions. The ordinary result contract already carries output-artifact, effect-receipt, policy-decision, input/output-hash, status, and completeness channels. 

No path may return promotion success until those authoritative records reconcile. An unknown transaction remains non-success; no receipt may be synthesized; and no existing PromotionDecision, Passport revision, event, or receipt may be rewritten.
