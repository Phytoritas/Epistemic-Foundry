---
name: foundry-observe
description: "Acquire relation-aware evidence with receipts across support, counter, null, boundary, method, temporal, and novelty lanes."
metadata:
  architecture-version: "4.0.0"
  status: "ACTIVE"
---

# Observe

Compile search lanes from the framed claim. Register source versions and exact spans. Distinguish UNSEARCHED, SEARCHED_NONE, SEARCHED_WITH_RESULTS, and FAILED. Build a dependency-adjusted Evidence Pack and SearchCompletenessCertificate.

## Executable slice

Check readiness with MCP `foundry.status`. Proceed only when its `runtime` reports `READY`; otherwise report the bridge blocker.

Run the lexical lane against an existing index:

```
efoundry --json retrieve query <db_path> --lane lexical --expression <fts5-expression> \
  --run-id <id> --query-plan-id <id> --plan-hash <sha256:...> \
  --policy-bundle-hash <sha256:...> --lane-decision-evidence-id <id> \
  --started-at <rfc3339> --finished-at <rfc3339>
```

Every binding is caller-supplied; the command reads no clock and invents no plan. Omitting one fails closed rather than guessing.

Served lanes are `lexical`, `citation`, and `entity_variable`. The other eight return their `UNSEARCHED` sentinel with a reason, which is the honest searched-scope record, not an empty result.

Accept only what the command returns: `retrieval-candidate` objects, the sealed `search-lane-receipt` set, and the lane reconciliation. This slice does not emit an Evidence Pack or SearchCompletenessCertificate; do not claim either.

Never run `retrieve build` implicitly. It mutates the index and is the caller's explicit decision.
