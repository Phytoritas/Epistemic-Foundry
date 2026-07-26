# Bootstrap with Claude Code

## Preflight

```text
Read CLAUDE.md, MASTER_SPEC.md, manifests, schemas, and workflows.
Do not edit. Build both the data-dependency graph and shared-resource graph.
Validate that ready nodes have disjoint write scopes and frozen contracts.
Report pre-existing changes and missing prerequisites.
```

## Worktree policy

For parallel implementation:
```bash
claude --worktree wp-a01
```

Use a different worktree for independent review. Do not copy secrets automatically.

## Implement A01

```text
Implement A01 only in this worktree. Keep changes inside the exact write
scope. Use deterministic checks and preserve unknown user work. Emit the
structured WorkPackageReport and an output artifact manifest.
```

## Review A01

```text
Review the A01 branch read-only from the latest approved base. Compare the
specification, actual diff, tests, and artifacts. Return structured findings.
Do not edit or approve based on the maker's prose.
```

## Integration

The main session merges only after review disposition and required checks. It runs the phase integration gate and records a checkpoint.
