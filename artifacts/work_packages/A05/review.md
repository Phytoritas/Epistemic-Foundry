# A05 contract review record

Status: `SPEC_GAP_WITH_RECORDED_PROCEDURE_DEVIATION`

Review mode: `USER_AUTHORIZED_SELF_REVIEW`

The user prohibited subagents and authorized direct handling of review work.
The primary author therefore performed this contract review. This record is
not independent assurance, and the procedure deviation cannot waive missing
or ambiguous evolution and promotion authority.

Reviewed authority bindings:

- `MASTER_SPEC.md`: `43fbb63f2b4cf697d10be15521a4d8ddaf123fb822b4d563ba4e026ed82cf3f3`
- `MASTER_EXECUTION_PROMPT.md`: `9b6cff656c62383229c5836c260b48a6f3fd024db7dc71ff04521ab7b539b855`
- `manifests/development_manifest.yaml`: `456330ae4aa950d1410d5180ad704927c5ec78a741d3c616d7a1cfd5bb0054a7`
- `schemas/evolution-run-spec.schema.json`: `29fe472309463865f58413c9e6566d6b3bcb71be7f6f7c74dfe1176f6a407ee9`
- `schemas/run-spec.schema.json`: `91a8ee9e05bb3fb264f355b93ddad07d1e47b2829f6f960ade4c46a04011c64c`
- `schemas/promotion-decision.schema.json`: `a71a125155f5690f7367b800d88ef7c49ef1f132cb607b37abb04e820924ebdc`
- `workflows/evolution_chamber_cycle.workflow.yaml`: `d3a611dc7c18dfdd8353cc49fa73bf0145465a245b00d22c945e5aa55ab40688`
- `prompts/promotion_attestor.md`: `cba0bf56de963541abb5231e7ac3d7ae213bcdab856ebd825dc3efaba4f0b224`
- `src/epistemic_foundry/governance/promotion.py`: `a05013fdd9ea83a51071f376075b540a2fc371bb7e9f2ff12f786feb0ba90e71`
- A04 report: `f34f72c561a6eb1696a524c1910d83a338847536e3c497c5d3038e7a1d2855ab`
- A04 review: `7e905b213492b83823bc8cdbf13c1a73bc53e0b8fce6b9a911f0879d3e100658`

Review confirmed:

1. A04 is a recorded `PASS` dependency checkpoint, with the previously
   disclosed direct-review limitation.
2. The three examined schemas pass Draft 2020-12 meta-validation. Structural
   schema validity does not establish the missing cross-field authority rules.
3. The closed `EvolutionRunSpec` fully binds only two of thirteen required
   pin groups. Eleven groups are partial, missing, or ambiguous, including
   evaluator qualification, validation stages, statistics, archive policy,
   negative memory, concurrency, and forbidden authority fields.
4. `base_run_spec_id` has no canonical resolution contract for indirect pins,
   and the referenced base schema has no `evolve` run type.
5. The promotion schema accepts `PROMOTE` with `FAIL` or `PARTIAL` hard-gate
   status and accepts empty replication and approval arrays. All three probe
   fixtures are schema-valid.
6. The canonical workflow lets a provider-nondeterministic LLM promotion node
   directly unlock Passport issuance. It produces no distinct Parliament
   adjudication, independent attestation, or approval artifact and contains no
   mandatory deterministic promotion-gate reference.
7. The Python governance helper fails safely for the covered invalid cases,
   and all 73 targeted governance/evolution tests pass. The workflow does not
   bind that helper, so local runtime safety cannot be treated as canonical
   workflow enforcement.
8. The complete Python regression suite passes 789 tests. This preserves the
   existing behavior but cannot satisfy a missing authority contract.
9. A05 owns only `docs/v4_a05/**` and
   `artifacts/work_packages/A05/**`. Repairing the canonical schemas or
   workflow within this package would exceed write scope and invent shared
   semantics.
10. Bundle-wide validation still reports six pre-existing
    `PACKAGE_MANIFEST` mismatches from the dirty worktree. Those inventory
    errors are recorded separately and are not used to explain either A05
    contract gap.

Findings: two blocking `SPEC_GAP` findings.

Required resolution:

- `A05-SG001`: define canonical per-run bindings and resolution rules for all
  mandatory evolution pins, including their compatibility, hashing, and
  `RunSpec` relationship.
- `A05-SG002`: define cross-field promotion constraints and a canonical
  workflow path through deterministic gates, separate Parliament and
  attestation, replication ceilings, explicit approval authority, and
  immutable receipts.
- Assign the required shared-schema and workflow changes to an authorized
  package, implement negative/adversarial and crash/resume coverage, and then
  obtain genuinely independent review.

Decision: A05 is not integrated. A06 is blocked on A05. This record does not
claim that evolution authority or scientific promotion is implemented,
qualified, or independently assured.
