# I05-0001 primary-session review of parallel-agent work

- Author: a bounded parallel implementation agent (disjoint write
  scope, frozen contracts) under the product owner's explicit
  parallel-execution instruction. Reviewer: the primary session,
  which did not author this attempt; author/reviewer separation
  holds, external actor-independent certification does not.
- Write-scope audit: no tracked file was modified by the wave (mtime
  sweep over the dirty worktree), the sealed G05 payload surface
  re-verified green, and this package's files sit exactly inside its
  granted scope.
- The eligibility field is named admitted (eligible is a canonical insight-card enum value) and the contract check reads the schema's properties rather than its required list, with required-ness asserted from the test side.
- I04 shipped only Node intake UI; the dependency is contract-level and honestly recorded as composing no I04 Python surface.
- The duplicate-id rule refuses an id naming two documents even when one copy is ineligible — stricter than duplicates-among-seeds and documented.
- Diversity signature is (mechanism_graph_id, scope_vector_id), a defensible reading recorded as such; the floor K is caller-declared and never chosen by the module.
- Integration gates at review time: repository EF4-I22 discipline
  5/5, structure and boundary checks PASS, git diff --check clean,
  full Python and full Node suites green with the Node inventory
  unified at 107 files across five bases.
