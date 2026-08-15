# W01 package review record

Standing verdict: `PASS` (from attempt `0001`).

This file is the package-level projection the manifest requires. The
attempt review below, at `attempts/0001/review.md`, is the primary record.

---

# W01-0001 primary-session separate adversarial review

- Reviewer: primary session in a separate adversarial pass under the
  product-owner instruction forbidding subagents and Fleet;
  actor_independence=false is recorded, not hidden.
- Vocabulary authority (EF4-I22): executor types, determinism
  classes, failure policies, model tiers, and the exact NodeContract
  field set derive at runtime from schemas/node-contract.schema.json;
  a tampered, open, or renamed schema is rejected at factory time,
  and the schema file is pinned to the sealed contracts registry by
  source hash.
- Unknown executors are blocked with the canonical vocabulary in the
  typed error, and executor references follow the observed canonical
  conventions (llm prompts, subworkflow workflow documents, dotted
  entrypoints or tools scripts).
- DAG authority stays with the sealed scheduler compiler: duplicate,
  unknown, and self dependencies and contract-less cycles are its
  typed failures, and the compiled plan passes its integrity check.
- Hidden-edge rule: two nodes whose write scopes overlap must be
  dependency-ordered or share a declared resource; the compiler
  fails closed otherwise and emits the resource-edge evidence.  A
  survey of all 22 canonical workflows found zero violations of this
  rule, so the contract matches the corpus it will compile.
- Real-shape proof: the memory_recall projection (hash-bound to its
  YAML source) compiles to an eight-node plan; full-corpus
  compilation of all 22 workflows remains a later integration gate
  because the Node runtime deliberately has no YAML parser.
- Determinism: identical documents compile to identical bytes and
  hashes; the input document is never mutated; outputs are frozen.
- Residual limitations: workflow YAML parsing, runtime execution,
  checkpointing (W02), and staleness reassessment (W03) are outside
  this package; this review is not external actor-independent
  certification.
