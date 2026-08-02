# Trust-zone enforcement boundary

`trust-boundary.mjs` implements the S01 negative authority boundary. Text from
evidence, tools, prior agents, subagents, and models is sealed as immutable
data with a runtime-private provenance brand. It can be used only for the
explicit data transforms in `DATA_ONLY_USE`.

Prompt-injection scanning is advisory. A clean scan or a `trusted` extraction
label does not change the content's plane, and this module has no API that can
grant a capability, mutate policy, change phase, execute an effect, or create
an approval. Authority-bearing requests receive a typed `DENY` decision.

Persisted or transported content loses the private runtime brand and must be
re-sealed from canonical provenance before use. Callers must not infer
authority from serialized public fields.

Required checks:

```text
node --test packages/foundry-kernel/src/security/trust/prompt-injection.test.mjs
node --test packages/foundry-kernel/src/security/trust/authority-escalation.test.mjs
```
