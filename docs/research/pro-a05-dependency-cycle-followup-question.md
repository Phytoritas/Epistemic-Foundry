Delta after the owner question was submitted: local static mapping found a decisive manifest cycle and additional fixed Kernel constraints.

The user approved the direction that A05 owns promotion runtime orchestration, but not a cyclic dependency graph.

Current manifest edges are:

```text
C01 -> A05
C02 -> C01
C03 -> C01,C02
C04 -> C02,C03
E01 -> C04,D04
E02 -> E01
E03 -> E01
E04 -> E02,E03
```

Therefore adding `A05 -> E03/E04` creates `A05 -> E04 -> E01 -> C04 -> C03/C02 -> C01 -> A05`.

Additional verified facts:

- Kernel `commitWithLease()` is the live authority primitive. It accepts exact lease-use fields plus a synchronous transaction-scoped callback, revalidates the persisted lease before and after the callback, records an immutable lease-use/outbox, and returns `COMMITTED|EXISTING` plus operation/lease/fencing/result.
- No public package export, Python transport, or production consumer exists.
- The A05 workflow's commit node returns the wrong shape today, and its reconcile node also returns the wrong declared output type.
- E02's fixed lifecycle is ActionIntent -> Attempt -> effect -> EffectReceipt. Current A05 incorrectly requires a completed EffectReceipt before CAS even though the workflow reconciles it afterward.
- `NodeInvocation` does not bind the E03 lease/principal/capability/scopes/operation, and `ResultEnvelope` does not carry the Kernel lease-use result.

Question: Is there a cycle-free way for A05 itself to own runtime orchestration without weakening authority—such as keeping A05 dependent only on predecessor-neutral abstract contracts while a later package supplies the Kernel adapter—or does the new evidence require the earlier option 2: A05 remains the semantic/charter owner and a later named integration package owns the E02/E03/E04 runtime composition?

Give one recommended DAG/ownership layout. Identify the exact edge(s) to change, the package that owns the provider-neutral port, the package that owns the concrete Kernel adapter, and the smallest canonical transport schema needed. Do not suggest removing `C01 -> A05` unless higher authority clearly permits it; MASTER_SPEC lists C01 as depending only on A04 while the lower manifest adds A05, so treat that disagreement explicitly as a SPEC_GAP if necessary.
