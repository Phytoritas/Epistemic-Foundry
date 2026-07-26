# v4 Evolution Plugin Skills and CLI Contract

## Skills

The reference blueprint contains:

- `foundry-evolve`
- `foundry-evolve-setup`
- `foundry-evolve-convert`
- `foundry-evolve-run`
- `foundry-evolve-inspect`
- `foundry-evaluator-audit`
- `foundry-challenge`
- `foundry-archive`
- `foundry-promote-evolved`
- `foundry-replicate`
- `foundry-evolution-replay`
- `foundry-evolution-stop`
- `foundry-shinka-adapter`

Skills route and explain; they cannot mutate canonical state without the CLI/MCP/kernel contracts and receipts.

## Proposed CLI

```text
efoundry evolve setup
efoundry evolve convert
efoundry evolve run
efoundry evolve pause|resume|stop
efoundry evolve inspect
efoundry evolve replay
efoundry evaluator register|audit|qualify|diff
efoundry challenge generate|run|inspect
efoundry archive map|inspect|rebalance
efoundry replicate plan|run|audit
efoundry promote evolved
efoundry backend shinka qualify|inspect|disable
```

Every mutating command supports:

- `--dry-run`;
- expected state revision;
- input artifact hash;
- idempotency key;
- explicit budget;
- capability profile;
- machine-readable JSON output;
- receipt destination;
- cancellation.

## Inspect output

Inspection must include Pareto/niche view, lineage diversity, model/operator concentration, candidate/evaluation counts, challenge survival, statistical budget, hidden-stage status without hidden contents, failed replications, protected negative memory and current checkpoint.

A “top candidates” view is optional and never the sole view.

## Hooks

Evolution and holdout hooks are convenience guardrails. Hosted tools or disabled hooks may be unobserved. Kernel ACL/policy and storage isolation remain authoritative.
