# Q04-0001 primary-session review of parallel-agent work

- Author: a bounded parallel implementation agent (disjoint write
  scope, frozen contracts) under the product owner's explicit
  parallel-execution instruction. Reviewer: the primary session,
  which did not author this attempt; author/reviewer separation
  holds, external actor-independent certification does not.
- Write-scope audit: no tracked file was modified by the wave (mtime
  sweep over the dirty worktree), the sealed G05 payload surface
  re-verified green, and this package's files sit exactly inside its
  granted scope.
- Predictions are a committed synthetic fixture guarded by SYSTEM_OVERCLAIM; the gates measure the benchmark contract, not any component's accuracy, and both reports say so.
- The time axis was introduced by this package because the Q01 gold corpus carries no publication dates; labels remain bound to the sealed gold corpus by case id.
- evals/ is outside the EF4-I22 scanner; the literal scan is scoped to the vocabularies these gates consume, documented in the suite docstring.
- The evals dependency regression runs three pytest processes because the sealed Q02/Q03 evaluators share a module name and shadow each other on a combined run; reproduced, not assumed.
- One full-node failure during the loaded parallel window was diagnosed as a pre-existing E02 concurrency test sensitive to machine load (idempotency.test.mjs); it passes in isolation repeatedly and the receipt was re-run clean.
- Integration gates at review time: repository EF4-I22 discipline
  5/5, structure and boundary checks PASS, git diff --check clean,
  full Python and full Node suites green with the Node inventory
  unified at 107 files across five bases.
