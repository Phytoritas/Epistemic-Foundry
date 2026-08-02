# A05 Evolution Authority and Scientific Promotion Charter

Status: `CANONICAL AUTHORITY CONTRACT`

Work package: `A05`, attempt `0002`

Effective decision: `HD-EF4-A05-C01-B04-20260727-001`

This charter prospectively resolves `A05-SG001` and `A05-SG002`. It does not
delete, relabel, or retroactively pass the prior `SPEC_GAP` attempt. The prior
gap report, commands, review, and probe remain immutable historical evidence.
This package defines the contract that C01 and later runtime packages must
implement. A05 does not modify a schema, workflow, or runtime file.

The keywords MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
and MAY are normative. When this charter conflicts with a higher authority,
the higher authority wins and the implementation stops with `SPEC_GAP` rather
than guessing.

## 1. Authority boundary

Foundry Kernel and Noetic Ledger own canonical state, authority, receipts,
gates, and replay. An Evolution Chamber, candidate generator, mutation model,
parent selector, prompt, hook, provider adapter, or Shinka backend MAY propose,
mutate, challenge, and rank candidates. None of them may read a hidden holdout,
mutate the current evaluator or policy, issue approval, commit promotion,
rewrite the ledger, or certify its own candidate.

Source evidence, the sealed `EvolutionRunSpec`, the active policy and
evaluator bundles, the holdout, the statistical family, promotion gates, and
release state are outside every mutable genome. Combined or scalar fitness is
an advisory search signal only. It can never substitute for a deterministic
gate, Parliament, independent attestation, approval, or receipt.

The final authority path is:

`deterministic G00-G10 -> sealed Evidence Parliament -> G11 -> independent
attestation -> G12 -> replication-ceiling recheck -> G13 -> bounded
promotion:commit lease -> atomic G14`.

No majority vote, model confidence, scalar score, human preference, or backend
observation can override a failed non-waivable gate.

## 2. EvolutionRunSpec resolution and sealing

### 2.1 A string ID is not a pin

Every reference MUST be resolved before execution. Each entry in the required
`resolved_refs` object is an immutable tuple with all of these fields:

| Tuple field | Contract |
| --- | --- |
| `logical_id` | Stable logical identity used by the RunSpec or policy. It is not sufficient by itself. |
| `exact_version_or_revision` | Exact version, revision, commit, snapshot, or immutable release identifier. Ranges and floating aliases are forbidden. |
| `content_hash` | `sha256:<64 lowercase hex>` over the resolved bytes or the canonical JSON representation defined below. |
| `resolver_id` | Identifier of the resolver implementation or authority. |
| `resolver_version` | Exact resolver version or revision. |
| `resolved_artifact_locator` | Immutable or version-bound locator used for later retrieval and replay; it is not an authorization grant. |
| `resolved_at` | RFC 3339 date-time at which resolution completed. |
| `authority_source_class` | Typed authority/source class, such as canonical bundle, policy authority, licensed corpus snapshot, provider surface, or external backend. |
| `reproducibility_class` | Exact reproducibility classification, including limitations such as `provider_versioned_not_byte_pinned`. |

An entry is unresolved if any tuple field is missing. A locator that resolves
only because of the current working directory, a mutable search path, or a
repository checkout is not immutable resolution.

### 2.2 Required resolved-reference inventory

The one existing `EvolutionRunSpec` schema MUST gain one required
`resolved_refs` object. C01 MUST keep that existing schema file rather than
creating a second evolution-run schema. The object seals every row below.

| Canonical key | Required content and resolution rule |
| --- | --- |
| `base_run_spec` | The complete base `RunSpec` artifact, its exact revision, and content hash. Indirect IDs in the base spec do not replace any row below. |
| `schema_bundle` | The exact canonical schema-bundle version/revision and bundle hash. |
| `workflow` | Workflow logical ID, exact workflow version, workflow content hash, and immutable workflow artifact locator. |
| `policy_bundle` | The exact `PolicyBundle`, including capability, approval, veto, and non-waivable-gate policy. |
| `corpus_evidence_snapshot` | Immutable corpus/evidence snapshot, source/license authority, and snapshot hash. |
| `ontology` | Exact ontology revision and hash. |
| `domain_pack` | Exact `DomainPack` revision and hash. |
| `evaluator_bundle` | Exact immutable `EvaluatorBundle`, qualification reference, revision, and hash. |
| `holdout_manifest` | Exact access-controlled `HoldoutManifest`, revision, and hash; the locator does not grant content access. |
| `operator_registry` | Exact mutation/crossover operator registry revision and hash. |
| `prompt_bundle` | Exact prompt bundle revision and hash. A mutable prompt lineage cannot be activated in the current run. |
| `model_routing_policy` | Exact routing policy revision and hash. |
| `provider_adapter_manifest` | Every provider adapter's exact version/revision and hash plus the remote-model disclosures in section 2.4. |
| `statistical_plan` | Exact sequential-testing, multiplicity, selective-inference, winner-selection, and holdout-consumption plan. |
| `selection_policy` | Exact parent, survivor, Pareto/niche, island, and model-selection policy revision and hash. |
| `stop_policy` | Exact stop, reconciliation, exhaustion, and stop-certificate policy revision and hash. |
| `replication_policy` | Exact replication requirement, independence, formal-exception, and ceiling policy revision and hash. |
| `archive_niche_policy` | Exact archive, niche, minority-lineage, failed-replication, unsafe-candidate, and negative-knowledge retention policy. |
| `budget_envelope` | Exact hard/soft budget and concurrency envelope revision and hash. |
| `execution_environment_toolchain_manifest` | Exact operating environment, runtime, dependency lock, toolchain, sandbox, and relevant host-capability manifest. |
| `external_backend_manifest` | Conditional: REQUIRED whenever an external backend is enabled; otherwise its absence MUST be explicitly represented as not enabled by the sealed policy. |

The `resolved_refs` object is complete only after every unconditional key and
every applicable conditional key resolves. A reference cannot be satisfied by
a later "current" lookup.

### 2.3 Floating-reference prohibition

The following are forbidden: `main`, `latest`, an unpinned tag, a version
range, an unversioned provider model alias, or any resolver behavior that maps
a logical ID to whichever artifact is current at execution time. An external
backend MUST include at least one of:

1. an exact source commit;
2. an immutable package digest; or
3. an immutable container digest.

If none exists, the run MUST NOT start. A resolver MUST NOT convert a floating
reference to its current value and describe that act as pinning.

### 2.4 Remote model disclosure

When a provider does not expose a weight hash, the sealed provider-adapter
manifest MUST record:

- provider;
- exact exposed model identifier;
- exposed snapshot or revision, when available;
- adapter version and adapter content hash;
- complete decoding parameters;
- capability-report hash; and
- `reproducibility_class`.

An unversioned model alias is forbidden. When the provider supplies no
immutable model revision, the run MUST disclose
`provider_versioned_not_byte_pinned`. G10 MUST explicitly carry that
limitation into its replication-ceiling calculation. The limitation is never
silently promoted to byte reproducibility; `REPLICATED` remains possible only
after an independent replication path has reproduced the registered claim
under the sealed replication policy and all other gates pass.

### 2.5 Canonical hash and seal rules

JSON hashes use deterministic canonical JSON equivalent to RFC 8785 JCS and
UTF-8 bytes. `spec_hash` is excluded from the object when calculating
`spec_hash`. The final hash is calculated only after every `resolved_refs`
entry has been included.

Array order is preserved when order is meaningful. A set-semantic array MUST
have a schema-declared canonical sort rule, and hashing applies that rule
before serialization. If an array is semantically a set but the schema does
not declare its canonical sort, the contract is incomplete and the result is
`SPEC_GAP`; an implementation cannot invent a sort. Duplicate normalization
or locale-dependent ordering is forbidden.

After sealing, the same `evolution_run_id` cannot change a reference,
evaluator, holdout, policy, statistical family, prompt bundle, or any content
that contributes to `spec_hash`. Any such intended change requires both a new
`EvolutionRunSpec` revision and a new `evolution_run_id`.

Resolution outcomes are typed:

| Condition | Required outcome |
| --- | --- |
| Hash mismatch, sealed-artifact mutation, or tampering | `FAIL` |
| The contract identifies an exact artifact, credential, licensed source, or backend but it is unavailable | `BLOCKED` |
| The contract does not define which version, hash, or canonicalization rule applies | `SPEC_GAP` |
| Floating reference resolved to an arbitrary current value | Forbidden; `FAIL` once attempted, otherwise reject before execution |

## 3. Promotion vocabulary

`requested_level` and `granted_level` use this closed ordered enum only:

1. `INBOX`
2. `CANDIDATE`
3. `LITERATURE_GROUNDED`
4. `VALIDATION_SCREENED`
5. `EMPIRICALLY_TESTED`
6. `REPLICATED`

`BLOCK` is a promotion decision/effect semantic, not a seventh level. A schema
token such as `BLOCKED` may encode the corresponding terminal decision, but it
MUST NOT appear in either level field. A granted level can never exceed the
requested level or the deterministic G10 ceiling.

| Level | Minimum meaning; no stronger meaning may be inferred |
| --- | --- |
| `INBOX` | The falsifier, scope, or atomic claim is incomplete. The research object may be stored, but is not elevated to Parliament or validation. |
| `CANDIDATE` | Schema, parent lineage, falsifiability, and provenance are valid. This implies neither scientific support nor novelty. |
| `LITERATURE_GROUNDED` | Support, counter, null, boundary, method, and prior-art lanes ran; a valid `SearchCompletenessCertificate` exists; scope, method, and evidence-dependency audits completed; Evidence Parliament adjudicated the sealed pack. |
| `VALIDATION_SCREENED` | A qualified `EvaluatorBundle` ran public, hidden, OOD, adversarial, and metamorphic stages; leakage audit and adaptive-search statistics passed. This is not actual empirical confirmation. |
| `EMPIRICALLY_TESTED` | A preregistered `ValidationPlan` governed real measurement, experiment, or independent-data validation, with `ActionIntent`, execution receipt, Result, and reconciliation. This does not imply independent replication. |
| `REPLICATED` | An independent executor followed a preregistered `ReplicationPlan`; independence audit passed; `ReplicationResult.status` is `REPLICATED`; Parliament, attestation, and every required human/policy approval passed. |

Levels are cumulative. Requesting a higher level does not waive any lower
level's evidence.

## 4. Deterministic promotion gates

### 4.1 Canonical gate order and semantics

The following order is immutable within a run:

| Order | Gate ID | Mandatory determination |
| ---: | --- | --- |
| 00 | `G00_PIN_RESOLUTION` | Verify the sealed `EvolutionRunSpec`, its `spec_hash`, and every resolved-reference version and content hash. |
| 01 | `G01_POLICY_AUTHORITY` | Verify `PolicyBundle`, principal capability, approval policy, authority separation, and the registered non-waivable gates. |
| 02 | `G02_EVALUATOR_HOLDOUT_FIREWALL` | Verify evaluator immutability, `candidate_access=false`, and that candidate/model/prompt/backend identities cannot read the holdout. |
| 03 | `G03_SCHEMA_LINEAGE_COUNT` | Verify applicable candidate schema and parent lineage, then reconcile expected, generated, evaluated, persisted, failed, cancelled, and missing counts. |
| 04 | `G04_SOURCE_PROVENANCE` | Verify source spans, artifact receipts, evidence linkage, and trust labels. |
| 05 | `G05_SEARCH_COVERAGE` | Verify support, counter, null, boundary, method, and novelty/prior-art lanes; distinguish `UNSEARCHED` from `SEARCHED_NONE`; prohibit absence or novelty claims beyond searched scope. |
| 06 | `G06_METHOD_SCOPE_DEPENDENCY` | Verify measurement comparability, scope overlap, shared sample/dataset/preprint dependency, method vetoes, and the resulting promotion ceiling. |
| 07 | `G07_VALIDATION_LEAKAGE` | Verify evaluator qualification, hidden/OOD/adversarial/metamorphic results, leakage audit, and evaluator-gaming checks. |
| 08 | `G08_ADAPTIVE_STATISTICS` | Verify the sequential-testing ledger, multiple-testing adjustment, selective-inference report, winner-selection path, and holdout consumption. |
| 09 | `G09_RED_QUEEN` | Verify the strongest relevant counterexample, null, confounder, method, or OOD challenge and its reproducibility. |
| 10 | `G10_REPLICATION_CEILING` | Compute the requested-level replication requirement and maximum grantable level, including reproducibility-class limitations. |
| 11 | `G11_PARLIAMENT` | Verify blind briefs; prosecutor, method, scope, causal, novelty, and dependency audits; strongest counterevidence; minority report; and any attempted deterministic-gate override. |
| 12 | `G12_INDEPENDENT_ATTESTATION` | Require PASS from an eligible independent attestor reviewing only the sealed structured pack whenever the requested level is `VALIDATION_SCREENED` or above. |
| 13 | `G13_HUMAN_POLICY_APPROVAL` | Verify either a policy determination of `NOT_REQUIRED` or every valid required `ApprovalRecord`, including human authority where triggered. |
| 14 | `G14_ATOMIC_PROMOTION_COMMIT` | Use expected-revision compare-and-swap and atomically bind both ActionIntents, the short CapabilityLease, new PromotionDecision and Passport revisions, EventRecord, EffectReceipt, and ArtifactReceipt. |

Every gate executes in this order and emits one immutable `GateDecision` with
at least `input_hash`, `decision_hash`, `policy_version`, and evidence IDs.
Applicability is not represented by omitting a gate. When a substantive check
is below the requested level, the gate may PASS only with sealed policy
evidence that the check is `NOT_REQUIRED` for that request. That is not a
`WAIVE` and does not grant the scientific meaning of the higher tier.

### 4.2 Requested-level gate applicability matrix

Legend: `R` = substantive evidence required; `P` = gate still executes and
requires policy-backed `NOT_REQUIRED` evidence; `C` = applicability is
triggered by work class, risk, effect, data, release, or policy, and the gate
must produce either required approval evidence or a policy-backed
`NOT_REQUIRED` PASS. There are no omitted gates.

| Gate | INBOX | CANDIDATE | LITERATURE_GROUNDED | VALIDATION_SCREENED | EMPIRICALLY_TESTED | REPLICATED |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| `G00_PIN_RESOLUTION` | R | R | R | R | R | R |
| `G01_POLICY_AUTHORITY` | R | R | R | R | R | R |
| `G02_EVALUATOR_HOLDOUT_FIREWALL` | R | R | R | R | R | R |
| `G03_SCHEMA_LINEAGE_COUNT` | P | R | R | R | R | R |
| `G04_SOURCE_PROVENANCE` | R | R | R | R | R | R |
| `G05_SEARCH_COVERAGE` | P | P | R | R | R | R |
| `G06_METHOD_SCOPE_DEPENDENCY` | P | P | R | R | R | R |
| `G07_VALIDATION_LEAKAGE` | P | P | P | R | R | R |
| `G08_ADAPTIVE_STATISTICS` | P | P | R | R | R | R |
| `G09_RED_QUEEN` | P | P | R | R | R | R |
| `G10_REPLICATION_CEILING` | R | R | R | R | R | R |
| `G11_PARLIAMENT` | P | P | R | R | R | R |
| `G12_INDEPENDENT_ATTESTATION` | P | P | P | R | R | R |
| `G13_HUMAN_POLICY_APPROVAL` | C | C | C | C | C | C |
| `G14_ATOMIC_PROMOTION_COMMIT` | R | R | R | R | R | R |

For `INBOX`, G03 confirms that incomplete fields are represented truthfully
and that no candidate-level claim is issued; it does not pretend that the
candidate schema passed. For `CANDIDATE`, a non-inferential sealed policy may
make G08 and G09 substantively not required only while no support, novelty, or
validation claim is made. Any adaptive inferential claim activates the full
statistical and challenge evidence regardless of the requested label.

### 4.3 Non-waivable failures

`WAIVE` is forbidden for a non-waivable gate. Human or policy approval cannot
turn any of the following into PASS:

- evaluator mutation;
- hidden-holdout leakage or candidate access;
- missing source provenance;
- self-approval;
- scalar-only promotion;
- missing count reconciliation;
- missing adaptive-search statistics;
- a fabricated or missing receipt; or
- a failed integrity check.

The request fails at the corresponding gate. The system may preserve the
candidate and negative knowledge at a truthful lower state, but it cannot
launder the failure through a lower-level label without a new sealed request
and complete evidence.

## 5. Replication ceiling

G10 computes a ceiling before Parliament and rechecks it after attestation.
The final `granted_level` is the minimum of requested level, evidence-derived
level, method/scope ceiling, reproducibility ceiling, and replication ceiling.

| Replication state | Maximum grant and required decision/effect |
| --- | --- |
| Not run or `BLOCKED` | At most `EMPIRICALLY_TESTED`; the PromotionDecision must be `CONDITIONAL` or `UNDERDETERMINED`. |
| `PARTIAL` | At most `EMPIRICALLY_TESTED`; unresolved issues and limitations are required. |
| `INCONCLUSIVE` | At most `EMPIRICALLY_TESTED`; unresolved issues and limitations are required. |
| `FAILED`, peripheral/non-core failure | `REPLICATED` is forbidden; G10 and Parliament record the failure and may impose a lower ceiling. |
| `FAILED`, core empirical effect failed | At most `LITERATURE_GROUNDED`; `PromotionEffect` is `LOWER` or `BLOCK`. |
| `REPLICATED` | `REPLICATED` is eligible, not automatic; every other gate, Parliament, attestation, and required approval must also PASS. |
| Formal/deductive, policy-declared replication-not-applicable | Replication-equivalent is eligible only through two independent formal-verifier paths, or one formal verifier plus an independent attestor. It is forbidden for an ordinary empirical claim. |

No missing replication result can be represented by an empty array and then
treated as no restriction. A missing ceiling calculation is a G10 failure.

## 6. Evidence Parliament and independent attestation

Every promotion above `CANDIDATE` requires Evidence Parliament. Every request
for `VALIDATION_SCREENED` or a higher level requires independent attestation.
G11 and G12 still emit policy-backed `NOT_REQUIRED` PASS decisions for lower
requests; they are never silently absent.

The attestor MUST be independent of:

1. the actor and context that generated the candidate;
2. the candidate implementer;
3. the first adjudicator;
4. the same mutable prompt lineage; and
5. promotion-commit authority.

An attestor receives only these sealed structured artifacts, never the full
persuasive conversation:

- `EvolutionRunSpec` and all resolved references;
- candidate genome and lineage;
- Evidence Pack;
- `SearchCompletenessCertificate`;
- `FitnessVector` and its receipts;
- deterministic `GateDecision` artifacts;
- sequential, multiplicity, and selective-inference reports;
- Red Queen result;
- replication result or explicit replication status;
- Adjudication;
- MinorityReport artifacts; and
- unresolved limitations.

Attestation must PASS. A blocked, failed, missing, self-authored, or
commit-authorized attestation cannot be converted into PASS by approval.

## 7. Human and policy approval matrix

G13 always produces a `GateDecision`. An absent `ApprovalRecord` is never
interpreted as an empty but acceptable list. When approval is unnecessary,
G13 evidence MUST identify the exact PolicyBundle rule and conclude
`NOT_REQUIRED`.

| Trigger | Required authority | G13 requirement |
| --- | --- | --- |
| E4 or E5 work class | Authorized human under the sealed policy | Valid, unexpired `ApprovalRecord`; self-approval forbidden. |
| High-risk or controlled external effect | Authorized human and any domain/policy authority required by policy | Approval must precede the effect and bind its exact scope. |
| Hidden-holdout unblinding | Authorized human plus holdout policy authority | Explicit unblinding approval; promotion remains invalid if leakage already occurred. |
| External publication/release of `EMPIRICALLY_TESTED` or `REPLICATED` output | Authorized release human | Release approval binds the immutable result revision and limitations. |
| Policy or evaluator change proposal | Authorized policy/evaluator owner for a future run | Approval can authorize a proposal only; it cannot mutate the current run. |
| Non-local data export | Authorized data/export human and applicable source policy | Approval binds destination, fields, retention, and license/confidentiality conditions. |
| Publication-grade novelty claim | Authorized human publication authority | Approval binds searched scope and the valid completeness certificate; it cannot expand scope. |
| Low-risk `CANDIDATE` or `LITERATURE_GROUNDED` internal promotion | Policy approval MAY suffice only when the sealed PolicyBundle explicitly permits it | G13 cites the exact rule and records `NOT_REQUIRED` for human approval. |

Scientific role names do not imply infrastructure capability. Approval does
not grant `holdout:read`, `evaluator:write`, `policy:write`,
`promotion:commit`, `approval:issue`, or `ledger:rewrite` unless the policy
separately and lawfully authorizes that capability; candidate/model/backend
identities never receive those capabilities.

## 8. Receipt-bound promotion workflow

Promotion SHALL execute only in this exact order:

1. Record `ActionIntent(action_type=request_promotion)`.
2. Seal the requested level and candidate revision.
3. Build the promotion pack as the FORGE phase-E `PhaseArtifactSet`.
4. Verify every required promotion-pack artifact and its receipt.
5. Execute deterministic gates G00 through G10 in canonical order.
6. Run sealed Evidence Parliament adjudication.
7. Execute G11 Parliament gate.
8. Execute G12 independent-attestation gate.
9. Recheck G10 replication ceiling against the adjudication and attestation.
10. Execute G13 human/policy approval gate.
11. Calculate the grantable level as the minimum of all applicable ceilings.
12. Record `ActionIntent(action_type=commit_promotion)`.
13. Acquire a short-lived `promotion:commit` `CapabilityLease`.
14. Compare-and-swap the expected candidate and Passport revisions.
15. Record a new immutable `PromotionDecision` and `HypothesisPassport` revision.
16. Append the corresponding Noetic Ledger `EventRecord`.
17. Record the resolving `EffectReceipt` and `ArtifactReceipt`.
18. Complete G14 only after the atomic commit and all resolving receipts reconcile.

The phase-E promotion pack MUST bind the required kinds documented for C01:
sealed run spec and resolved references; candidate genome and lineage;
Evidence Pack; SearchCompletenessCertificate; FitnessVector and receipts;
G00-G10 decisions; statistical reports; leakage audit; Red Queen result;
replication result/status; Parliament briefs, adjudication, strongest
counterevidence, and minority reports; independent attestation when
applicable; unresolved limitations; approval evidence or G13
`NOT_REQUIRED`; both ActionIntents; and all artifact/effect receipts required
for commit and reconciliation.

## 9. Idempotency, CAS, crash recovery, and immutable revisions

The idempotency key contains at least:

`candidate_id + candidate_revision + requested_level + promotion_pack_hash + policy_bundle_hash`.

The canonical request hash covers the entire canonical request. The same key
and same request hash returns the existing logical result. The same key with a
different request hash is a conflict and does not execute. Existing Passport
or PromotionDecision artifacts are never overwritten; promotion, conditional
grant, rejection, block, and demotion each create a new immutable revision.

Crash/retry/reconciliation proceeds as follows:

| Crash or retry observation | Required action |
| --- | --- |
| No committed CAS and no resolving receipt | Resume from the last verified immutable gate/artifact; do not claim promotion. |
| Existing idempotency key and identical request hash | Return or continue the same logical operation; never create a second effect. |
| Existing idempotency key and different request hash | Return conflict; do not mutate state. |
| CAS outcome unknown or ledger/event visible without resolving `EffectReceipt` | Mark success unknown, inspect both canonical state and ledger, reconcile expected revisions and receipts, then retry or decide `FAIL`/`BLOCKED`. |
| CAS committed and all EventRecord, EffectReceipt, ArtifactReceipt, PromotionDecision, and Passport revisions reconcile | Return the existing successful logical result. |
| External/canonical state contradicts the ledger or receipts | Fail closed with integrity/reconciliation failure; never synthesize a receipt. |

After a crash, absence of an `EffectReceipt` means success is not proven. A
process exit code, HTTP acceptance, model answer, or visible state fragment is
not a substitute.

## 10. C01 and later-package implementation obligations

C01 implements this charter in the existing canonical schema files. It must
add `resolved_refs` and pin/hash semantics to `EvolutionRunSpec`; close the
six-level vocabulary and promotion-pack/receipt links in
`PromotionDecision`; align Adjudication recommendations; and document phase-E
artifact kinds in `PhaseArtifactSet`. C01 does not implement API handlers or
runtime behavior and does not increase the canonical schema count for
transport-only types.

Later runtime packages implement deterministic evaluation, access isolation,
Parliament orchestration, attestation, idempotency, CAS, reconciliation, and
ledger commits. Until those packages pass, this charter is a contract, not a
claim that the runtime is implemented or scientifically qualified.

## 11. Required negative and adversarial contract tests

The normative negative-test registry is
`docs/v4_a05/adversarial_contract_tests.md`. At minimum it rejects evaluator
mutation, hidden-holdout access, scalar-only promotion, self-approval, missing
replication ceiling, and missing receipts. It also covers floating references,
hash tampering, count mismatch, missing adaptive statistics, attestor
non-independence, idempotency conflict, and crash-without-receipt recovery.

A05 PASS requires a deterministic verifier to prove the resolution inventory,
six-level vocabulary, G00-G14 order, applicability matrix, replication
ceiling, approval matrix, 18-step workflow, crash/retry rules, and all negative
test expectations. The verifier is contract evidence only; it is not the
production promotion runtime.
