# Decision needed: the SPEC_BUNDLE gate no longer matches the bundle

## What changed since the last turn

Your release-inventory decision was implemented as scoped.

`tools/release_inventory.py` is now the single selection authority; both
`build_release.py` and `validate_spec_bundle.py` import it, and I verified they
now select an identical 1,890-file set. `node_modules/` and `.ruff_cache/` are
excluded, `.codex/` is allowlisted to `.codex/agents/`, `.github/` is included,
and `artifacts/` is gated on exact declarations.

The wildcard you flagged was real. `artifacts/work_packages/B04/attempts/**/canonical-projection-verification.json`
caused `load_declared_evidence_paths` to raise rather than expand, exactly as
designed. I resolved it by replacing the wildcard with the eight exact attempt
paths that exist (0003 through 0010), which is inside B04's declared scope.

I did not replace `PACKAGE_MANIFEST.json`. Delta classification gave 694
authored, 476 declared-evidence, 2 policy, and 179 unexplained. All 179 are
uncommitted working files. Committing them is not mine to do, and freezing
uncommitted state into the trusted baseline would destroy the drift signal, so
I stopped there per your rule.

Error character changed even though the count did not: previously the 56
errors were dominated by dependency and cache noise; now they are 54 real
content hash changes plus 1 inventory difference.

## The finding that prompts this question

`manifests/acceptance_matrix.yaml` declares SPEC_BUNDLE gates as exact counts.
Two no longer match the bundle:

| Gate | Declared | Actual |
|---|---|---|
| `canonical_workflow_count` | 22 | 23 |
| `workflow_node_count` | 327 | 350 |

Everything else still matches exactly: 127 schemas, 127 examples, 156 work
packages, 64 invariants, 65 prompts, 28 roles, 288 audit lenses, 29 blueprint
skills, 7 blueprint hook bundles.

`tools/validate_spec_bundle.py` already carries the correct values in its
`EXPECTED` dict (`"workflows": 23, "workflow_nodes": 350`) and validates
against those. But it never compares `EXPECTED` to the acceptance matrix. It
only checks that the six release-level *names* are present:

```python
expected_levels = {"SPEC_BUNDLE", "PLUGIN_ALPHA", "EVOLUTION_MVP_50",
                   "PILOT_200", "PRODUCTION_2000", "CROSS_DOMAIN_QUALIFIED"}
if set(levels) != expected_levels:
    errors.append(f"release levels mismatch: {sorted(levels)}")
```

So the acceptance matrix can drift from the bundle indefinitely and no check
notices. That is the same class of defect as the duplicated prefix tuple you
just had me fix: two places holding the same truth, with nothing forcing them
to agree.

## The questions

1. Which direction is correct? My reading is that the bundle grew a 23rd
   workflow legitimately and the acceptance matrix was simply not updated, so
   the matrix should be corrected to 23/350. But the opposite reading is
   possible: SPEC_BUNDLE was frozen at 22/327 and a 23rd workflow is scope
   drift that should be justified rather than absorbed. How do I tell which
   happened, and which is the right correction?

2. Should `validate_spec_bundle.py` enforce agreement between its `EXPECTED`
   dict and the acceptance matrix gates? That seems obviously right, but it
   creates a question of authority: if they disagree, which one is wrong? I do
   not want a check that simply picks a winner arbitrarily.

3. Is the acceptance matrix the right home for exact counts at all? A count
   like `workflow_node_count: 327` is a derived fact about the bundle, not a
   policy decision. Counts that must be hand-maintained drift by default. Is
   there a reason to state them as gates rather than deriving them, or is the
   gate's real purpose to catch unreviewed growth?

4. Who owns `manifests/acceptance_matrix.yaml`? I searched the development
   manifest write scopes and did not find it declared. If nothing owns it,
   that is presumably another SPEC_GAP like the release tooling one.

5. Is this worth doing now, or is there a better target? I lean toward doing
   it because it is the same failure mode I just fixed and it is small. But if
   you think the 179-file uncommitted state should be resolved first, or that
   some capability work matters more, say so.

## Constraints on your answer

- Do not propose evolution, Parliament, promotion, Shinka, or hidden-holdout
  work.
- Flag explicitly as SPEC_GAP anything requiring a manifest ownership
  amendment or a shared canonical contract change.
- Prefer the smallest change that makes the gate meaningful.
- Do not propose that I commit the user's uncommitted work.
- Assume no tests will be run unless explicitly requested.
