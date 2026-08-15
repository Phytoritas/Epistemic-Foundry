# T04 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# T04-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- The adapter contract is read, not restated. Network policy, safety
  class, approval policy, data classes and the manifest field set come
  from validation-target-manifest.schema.json; quota dimensions,
  enforcement modes and breach policy from budget-envelope; effect
  statuses from effect-receipt; the pinned isolation flags from
  holdout-manifest. Every local decision table is checked against the
  schema that declares it on each use, so a vocabulary the schema grows
  fails loudly as VOCABULARY_DRIFT instead of silently defaulting open.
- Outputs are hashed over the bytes, and verification re-derives both
  the digest and the size rather than trusting the receipt. Re-sealing a
  forged size does not help, because the size is recomputed too. A
  truncated capture is still hashed, as what was actually captured, and
  records the completeness failure instead of presenting itself as
  whole.
- Ceilings are mandatory rather than optional. UNMETERED never satisfies
  any safety class, a bounded_compute adapter cannot run on an estimate,
  high_risk requires preallocation, and an adapter that may reach the
  network must bound what it sends. A breach resolves through the
  envelope's own policy: CANCEL charges nothing and stops, MARK_PARTIAL
  clamps to the ceiling, PAUSE_AND_ESCALATE stops, WARN continues.
- Cancellation reconciles. The effect status is derived from what was
  observed, never from what was intended: a proven non-start is
  NOT_EXECUTED with no external effect, an interrupted run is UNKNOWN
  and must carry reconciliation_required, and a success that claims no
  hashed output is refused. The observation table is checked to cover
  the effect status vocabulary exactly, so a new status cannot become
  unreachable.
- Isolation dominates. A holdout that declares candidate access true
  contradicts its own schema and is refused before anything else runs; a
  sandboxed principal cannot reach a hidden partition or the evaluator
  even with an approval in hand; a non-sandboxed principal may unblind
  only with one, which is what the holdout contract itself pins.
- The gate cannot be talked up. Its status is derived from six criteria
  and a declared status stronger than the derived one is refused as
  GATE_OVERCLAIM rather than recorded.
- Correction recorded: the sealed attempts from R02 onward carried an
  evidence-build command naming build_r01_0001_evidence.py in their own
  directory. The command executed was each package's own builder; the
  recorded string was wrong. Those generations are hash-sealed and are
  not rewritten, so the defect is recorded in
  inherited-defect-corrections.json and corrected from T04 onward.
- Residual limitations: this is a contract gate, not an operating-system
  or container sandbox, and it says so; no test executes an external
  tool; path safety is decided over declared portable paths without
  touching the filesystem, so link and mount escapes remain the
  executing adapter's problem, which S02 covers on the kernel side; and
  binding this gate to the kernel and MCP surfaces belongs to T05 and
  later. This review is not external actor-independent certification.
