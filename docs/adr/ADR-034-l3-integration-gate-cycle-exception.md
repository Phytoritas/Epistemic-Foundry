# ADR-034 — L3 integration-gate cycle exception (refines ADR-032 rule 5)

**Status:** Accepted

This record refines — and for its narrow subject supersedes — rule 5 of
ADR-032 (*Component import direction and cycle policy*). ADR-032 as a whole
remains Accepted and normative; only its top-level-granularity statement of the
acyclicity invariant is restated here. All other ADR-032 rules (1–4, 6, 7) are
unchanged and continue to bind.

## Context

ADR-032 rule 5 says "the top-level internal component graph is a directed
acyclic graph" and its exception clause requires "a superseding ADR, an updated
boundary check, and proof that Kernel/Ledger authority and provider neutrality
remain intact." `docs/v4_plugin_architecture.md` §5 likewise states "Any
boundary change requires a new ADR, compatibility analysis, and an updated
deterministic check." This record exercises exactly that sanctioned path.

After the S/J/K/O-phase services landed, `boundary_cycle_policy_check` detected
two forbidden top-level 2-cycles between L3 governed services:

1. **(operators, security)** — carried by two module-slice edges:
   - `security.v4_s06` → `operators.v4_j05`
     (`security/v4_s06/governance_gate.py` importing the
     `governance_retroactivity_node` / `MutationOperatorError` public surface of
     `operators.v4_j05`), and
   - `operators.v4_j05` → `security.v4_s05`
     (`operators/v4_j05/registry.py` and `operators/v4_j05/prompt_workflow.py`
     importing `require_inert_mutations` / `ThreatControlError` from
     `security.v4_s05`).
2. **(evidence, retrieval)** — carried by:
   - `evidence.v4_k06` → `retrieval.v4_o05`
     (`evidence/v4_k06/gate.py` importing `require_plan_identity`,
     `RECEIPT_SCHEMA`, `AcquisitionError` from `retrieval.v4_o05`), and
   - `retrieval.v4_o05` → `evidence.v4_k05` and
     `retrieval.v4_o06` → `evidence.v4_k05`
     (`retrieval/v4_o05/acquisition.py` and `retrieval/v4_o06/gate.py` importing
     `assess_novelty_within_boundary` and peers from `evidence.v4_k05`).

Both cycles are appear-cyclic **only at top-level component granularity**. At
**module-slice granularity** — where each component and each `component/v4_*`
subpackage is a distinct node — the graph is a strict DAG:

```text
security.v4_s06 ─▶ operators.v4_j05 ─▶ security.v4_s05
security.v4_s06 ───────────────────────▶ security.v4_s05

evidence.v4_k06 ─▶ retrieval.v4_o05 ─▶ evidence.v4_k05
retrieval.v4_o06 ─────────────────────▶ evidence.v4_k05
```

No slice appears twice on any path, so **there is no runtime circular import**;
Python can import every module in a valid topological order. The top-level
2-cycle is an artifact of collapsing distinct integration-gate subpackages onto
one component name, not a real initialization cycle.

## Decision

The acyclicity invariant is restated at two granularities:

- **Runtime invariant (load-bearing, absolute).** The internal import graph at
  **module-slice granularity** — nodes are each top-level component *and* each
  `component/v4_*` subpackage, with every import resolved to its finest slice —
  **MUST be a strict DAG**. Any module-slice cycle is a real circular import and
  is forbidden with no exception.

- **Top-level invariant (refined).** At top-level component granularity a
  2-cycle between two **L3 governed services** is permitted **only** under the
  closed, enumerated, fingerprinted exception below. Every other top-level
  cycle — a third participant, a size ≥3 strongly connected component, a changed
  carrier edge, or any pair not on the list — remains forbidden and requires a
  further ADR.

- **Authority and adapter cycles remain absolutely forbidden.** No L0/L1/L2
  authority component (`contracts`, `domain`, `noetic_ledger`, `foundry_kernel`)
  and no L4 adapter (`plugin_shell`, `providers`, `shinka_adapter`, `cli`,
  `adapters`) may appear in **any** cycle at **any** granularity. No allowlist
  entry may cover such a component. Layer-inversion (an importer depending on a
  more-outward layer) and any authority→adapter edge also remain forbidden.

### Enumerated exemptions (closed list — fingerprinted)

Exactly two top-level SCCs are permitted. Each is pinned by its exact component
pair **and** its exact set of module-slice carrier edges. Any deviation fails
the check.

| # | L3 service pair | Carrier module-slice edges (public-API only) |
|---|---|---|
| E1 | `operators` ↔ `security` | `security.v4_s06 → operators.v4_j05`; `operators.v4_j05 → security.v4_s05` |
| E2 | `evidence` ↔ `retrieval` | `evidence.v4_k06 → retrieval.v4_o05`; `retrieval.v4_o05 → evidence.v4_k05`; `retrieval.v4_o06 → evidence.v4_k05` |

Each exemption is admissible only if, at check time, it is (a) exactly size 2,
(b) both members are L3 services, (c) its actual component pair and cross-edge
carrier set equal the pinned fingerprint above, (d) every cross edge is a
public-package-API import that targets a `component/v4_*` package boundary (no
reach-in to a private submodule beneath the `v4_*` public API), and (e) the
module-slice subgraph induced on the pair is itself acyclic. A new top-level
cycle, a grown ≥3 SCC, a changed carrier module, or a private-submodule reach-in
invalidates the fingerprint and fails the check.

## Compatibility analysis

- **Why ADR-032 rule 7 (move shared types to L0 / invert at L4) is not applied
  here.** All participants — `security` (v4_s05/v4_s06), `operators` (v4_j05),
  `evidence` (v4_k05/v4_k06), `retrieval` (v4_o05/v4_o06) — are **sealed**
  packages (S05, S06, J05, K05, K06, O05, O06). Applying rule 7 would change
  their public package APIs, which a docs-scope decision cannot and must not do.
  The coupling is **genuine behavior** (governance retroactivity qualification,
  inert-mutation threat control, plan-identity receipts, novelty-within-boundary
  assessment), **not** shared domain wire types that belong in L0; relocating
  behavior into `contracts`/`domain` would put L3 service logic into L0
  foundation, itself a boundary violation. Because the module-slice graph is
  already acyclic, there is no runtime defect to remediate — only a
  granularity-of-measurement mismatch to record.
- **Authority integrity is intact.** No authority component participates. The
  Foundry Kernel (L2) and Noetic Ledger (L1) neither import nor are imported by
  the exempt cycles; canonical transition, history, and gate authority are
  untouched. The check asserts this directly (authority-in-cycle → FAIL).
- **Provider neutrality is intact.** No adapter (L4) participates. `providers`,
  `plugin_shell`, `shinka_adapter`, `cli`, and `adapters` remain outside every
  exempt SCC; no provider-specific type crosses a boundary. The check asserts
  this directly (adapter-in-cycle → FAIL).
- **The exception is strictly narrower than ADR-032's own exception clause.** It
  adds a load-bearing module-slice DAG obligation that ADR-032 did not require,
  and closes the top-level allowance to a fingerprinted two-entry list. It is a
  tightening, not a weakening.

## Consequences

- `boundary_cycle_policy_check` gains a new absolute obligation: the
  module-slice graph must be a strict DAG. This can catch real circular imports
  that a top-level-only check would miss, so the check is strictly stronger.
- The only two tolerated top-level cycles are pinned by fingerprint; adding a
  third participant, growing either SCC, changing a carrier module, or reaching
  into a private submodule fails the check and forces a new ADR.
- Sealed S/J/K/O public APIs are preserved; no source or schema change is
  required to reach GREEN.
- Kernel/Ledger authority and provider neutrality remain provably outside the
  mutable search space and outside every tolerated cycle.

## Rejected alternatives

- **Break the 2-cycles per ADR-032 rule 7.** Infeasible without changing sealed
  public APIs (cycle 1) or impossible outright (cycle 2); rejected because it
  would mutate sealed packages a docs-scope waiver cannot touch.
- **Weaken `boundary_cycle_policy_check` to ignore top-level cycles.** Rejected;
  that would hide real authority/adapter cycles and size ≥3 SCCs. The check is
  instead tightened.
- **Open-ended waiver for "any L3 cycle."** Rejected; the allowance is a closed,
  fingerprinted two-entry list. Every other top-level cycle stays forbidden.
- **Relocate the coupled behavior into L0 contracts/domain.** Rejected; the
  coupling is L3 service behavior, not shared wire types, and L0 must not host
  service logic.

## Verification

`boundary_cycle_policy_check` (A03) enforces this decision deterministically. It
(1) rejects any layer inversion; (2) fails if any L0/L1/L2 authority or L4
adapter component appears in any cycle at any granularity; (3) rejects any
authority→adapter edge; (4) builds the module-slice graph (each component and
each `component/v4_*` subpackage a distinct node, imports resolved to the finest
slice) and fails on any module-slice cycle; (5) admits a top-level SCC of size
≥2 only when it matches an enumerated fingerprint here (exact pair, exact
carrier edge set, both L3, public-API-only carriers, acyclic induced subgraph);
and (6) preserves the documented-policy anchors, the inward ordering, the
`public-package-api-only` source-import policy, and the forbidden
duplicate-implementation policy. `adr_index_check` proves this record is indexed
and structurally complete.
