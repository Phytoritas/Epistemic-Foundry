# A06-0002 Independent Constitutional Re-Audit

Status: `INDEPENDENT_REAUDIT_RECORD`

Work package: `A06`, attempt `0002`, ordered by
`HD-EF4-A06-RM001-20260730-001` after the immutable `A06-0001` FAIL.

## 1. Method

The attempt-local verifier
(`artifacts/work_packages/A06/attempts/0002/constitutional_audit_verifier_0002.py`)
re-derives every A06-0001 finding from primary sources only: the canonical
schema and sample files, the live verifier-firewall runtime, and the workflow
YAML documents.  It performs its own graph analysis (gate declaration and
ancestry, llm output classes, capability holders, authority-artifact outputs)
and re-executes the 24 negative and 6 positive A05 constitutional cases into
its own JUnit evidence.  The audited A05 registry verifier is consulted only
as a labelled cross-check and contributes nothing to any finding verdict, so
the remediated runtime cannot certify itself.

## 2. Finding verdicts

| Finding | A06-0001 defect | A06-0002 verdict |
| --- | --- | --- |
| `A06-F001` | Evaluator schema accepted candidate-readable / mutable-during-run bundles. | `PASS` — hostile `readable_by_candidates`, `mutable_during_run`, and `candidate_access=true` fixtures are all schema-rejected. |
| `A06-F002` | Holdout schema and runtime seal accepted metadata/aggregate candidate access. | `PASS` — `METADATA_ONLY`, `AGGREGATE_ONLY`, and boolean-true access are rejected by schema and by `build_holdout_manifest`/`VerifierFirewall`. |
| `A06-F003` | A provider-nondeterministic llm node emitted `PromotionDecision` directly upstream of Passport issuance. | `PASS` — the chamber promotion node is a deterministic `subworkflow` delegation to `workflows/evolution_promotion.workflow.yaml`; no llm node in the chamber emits a `PromotionDecision`; the chamber keeps 26 nodes. |
| `A06-F004` | No graph enforcement of G00-G14, Parliament, attestation, approval, lease, CAS, or receipts. | `PASS` — the 23-node `evolution_promotion` graph declares all fifteen gates on dependency-ordered nodes, restricts llm nodes to advisory `Adjudication`/`Attestation`, grants `promotion:commit` to exactly one deterministic node that alone emits the `PromotionDecision`, and emits ActionIntent, PhaseArtifactSet, ArtifactReceipt, GateDecision, ApprovalRecord, CapabilityLease, and EffectReceipt artifacts. |
| `A06-F005` | The bounded promotion helper was not bound to a canonical workflow. | `PASS` — all 21 deterministic/policy/human-gate nodes resolve to `epistemic_foundry.governance.evolution_authority.nodes`, whose entrypoints delegate to `decide_promotion` and `PromotionCommitter`. |

Schema meta-audit: 127 canonical schemas, all Draft 2020-12 valid, no
duplicate `$id`.  Constitutional cases: all 24 negative and 6 positive case
tokens present and passing in the re-executed JUnit evidence.

## 3. Boundaries of this audit

- Review is a procedurally separate primary-session pass under the product
  owner's no-subagent instruction; `actor_independence=false` is recorded.
  This record is not external actor-independent certification.
- The audit proves contract and graph enforcement of the remediated
  surfaces.  It does not claim kernel-scheduler execution of the promotion
  workflow, evaluator qualification, live candidate promotion, or any
  release-level maturity.
- `A06-0001` remains the immutable FAIL record; nothing in this attempt
  rewrites, relabels, or retroactively passes it.
