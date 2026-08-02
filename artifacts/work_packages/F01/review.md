# F01 independent contract review

Status: `SPEC_GAP`

Verdict: F01 cannot be implemented or objectively pass its two required checks
without a higher-authority shared-contract decision.

Reviewer: `/root/f01_independent_review`

Review mode: `READ_ONLY_INDEPENDENT_CONTRACT_REVIEW`

The reviewer did not author F01 evidence, modify repository files, mutate RAH or
Git state, or waive any gate. C04 and E04 are verified PASS dependencies, but
dependency readiness does not supply the missing classifier semantics.

## Reviewed authority

- `MASTER_SPEC.md` —
  `sha256:43fbb63f2b4cf697d10be15521a4d8ddaf123fb822b4d563ba4e026ed82cf3f3`;
- `MASTER_EXECUTION_PROMPT.md` —
  `sha256:9b6cff656c62383229c5836c260b48a6f3fd024db7dc71ff04521ab7b539b855`;
- `AGENTS.md` —
  `sha256:858e537ed3e49754b8e60d31c985467ee1246ed258c7763d6de4ef0767e381ea`;
- `manifests/development_manifest.yaml` —
  `sha256:a0a0db29da459d29c655827eaa0f7253d1becc3e75106f369850335ac7b88345`;
- `docs/forge_protocol.md` —
  `sha256:c6aef0825e6c4ea5415cda92f69964833711ac36eff6fb70294842ff0957cae7`;
- `schemas/epistemic-work-classification.schema.json` —
  `sha256:5c0c574605f4d1d2e8ea42385d6bc40ac273d1cbf1319169f6e26db6656d6049`;
- `examples/sample_epistemic-work-classification.json` —
  `sha256:51084b66591673efb22249f30de88d01e797ec2c3f4361ab8d1197d0bcf9ffb2`;
- `workflows/forge_research_cycle.workflow.yaml` —
  `sha256:280cdf43d3c9024f181cc9de612ce795f106395fce601e18092f5d90ad231aa3`;
- classifier and Interview prompts bound in `report.json`;
- C04 report —
  `sha256:eca4fdd3f10537a2fb5c39643f4dee52bab9bcf5b95f9468ddcd470ffd98592f`;
- E04 report —
  `sha256:841dcf60989cfc7ab0eff7be95e1ae721ae18ac513cae653ab6ac8a44942f6c1`.

## Findings

1. **Classifier input and authority are undefined.** The workflow gives the
   provider-nondeterministic classification node `request` and `policy/**`,
   while `NodeInvocation` contains artifact identities rather than a typed
   request-feature or risk contract. No authority rule says whether the LLM
   decides the class, proposes signals for a deterministic guard, or supplies
   an already-classified value. A Kernel implementation would have to invent
   this boundary.
2. **Mixed-signal precedence and an underprocessing floor are absent.** The
   E0-E5 table describes typical requests but has no deterministic rules for a
   high-stakes translation, an ambiguous causal request, a novelty-plus-
   expensive-validation request, or overlapping lookup, synthesis and
   mechanism work. `risk_factors` is a free string array. A locally chosen
   ordering would become unauthorized scientific process-depth policy.
3. **The required exact output cannot be derived.** The schema requires one
   `default_role_count`, an exact `required_phases` array and a boolean
   `human_gate_required`; authority supplies ranges and phrases such as
   `no FORGE`, `full FORGE`, and `full FORGE + human gates`. It does not decide
   E0 `[]` versus `["IDLE"]`, exact role counts, or every class/ambiguity human
   gate. The schema does not enforce any cross-field class invariant.
4. **Optional Interview is not executable in the current DAG contract.** The
   workflow says E5 ambiguity triggers Interview, but
   `conduct_bounded_interview` depends unconditionally on
   `detect_interview_need`, and `compile_frame` depends unconditionally on both.
   `NodeContract` provides no conditional dependency expression and
   `ResultEnvelope` has no typed Interview route. F01 cannot repair workflow or
   node contracts from its classifier-only write scope.
5. **Identity, hashing and override are incomplete.** The classification
   schema constrains only ID length, timestamp format and digest syntax. It
   does not define the ID/clock authority, canonical hash preimage, self-field
   exclusion, retry identity or replay behavior. The sample digest is a
   placeholder. `OverrideRecord` is named in prose but has no canonical schema
   or bound application workflow.
6. **There is no objective acceptance oracle.** `classifier_gold_test` and
   `underprocessing_guard` exist only as manifest names. No canonical fixture
   set, expected labels/projections, metric, threshold, adversarial minimum or
   fail-closed rule exists. Writing tests under the classifier glob would make
   the implementation author the judge of the policy it implements.
7. **The execution and capability boundary is inconsistent.** The workflow
   emits a general `ResultEnvelope` rather than binding an
   `EpistemicWorkClassification` artifact. It uses `artifact_write`, the role
   registry uses `artifact.write`, and the implemented capability authority
   uses `artifact:write`; no normalization contract connects them. The prompt
   requires evidence IDs while the node read scope exposes no evidence
   artifact. These are shared workflow/authority issues outside F01 scope.
8. **Evidence paths do not authorize an invented test oracle.** The manifest
   directly declares the three F01 report artifacts and those exact files are
   valid package evidence outputs. It authorizes classifier implementation
   files but names no canonical gold fixture location outside that glob and
   grants no schema, workflow, prompt or manifest correction scope.

## Classification

The correct typed outcome is `SPEC_GAP`, not `FAIL`: no implementation was
attempted and the missing semantics cannot be derived from the current
authority chain. It is not `BLOCKED`: no credential, licensed source, host
capability, external service or backend is unavailable.

The F01 stop condition explicitly requires `SPEC_GAP` when a shared contract,
authority boundary or acceptance threshold is ambiguous. Implementing a
keyword heuristic, selecting arbitrary role counts, treating an LLM label as
authority, or constructing a local gold set would violate that condition.

## Minimum resolving decision

A product-owner HumanDecision must freeze one coherent contract that:

1. defines a closed typed classifier input and risk vocabulary, including the
   authority relationship between model proposals and deterministic guards;
2. defines mixed-signal precedence, tie-breaks and monotonic underprocessing
   floors;
3. fixes class-by-class phase arrays, exact role-count rules, human gates and a
   typed conditional Interview route;
4. fixes classification ID, timestamp, canonical hash, retry/replay and
   immutable override semantics;
5. normalizes capability names and binds the workflow result to a canonical
   classification artifact; and
6. authorizes exact test/fixture paths and freezes gold labels, projections,
   adversarial cases, metrics and PASS thresholds.

## Decision

F01-0001 is not integrated and must remain immutable `SPEC_GAP` history. F02
and F03 remain waiting on F01. Resume only with a new F01 attempt after a
durable higher-authority decision resolves `F01-SG001`; do not weaken the
schema, silently infer missing policy, or skip to a later work package.
