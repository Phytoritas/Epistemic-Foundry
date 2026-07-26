# ShinkaEvolve → Epistemic Foundry v4.0 Source Audit and Design Synthesis

- Research snapshot: **2026-07-26**
- Target repository: `SakanaAI/ShinkaEvolve`, public `main`
- Latest release observed: **v0.0.7**, released 2026-06-02; public `main` also contains later unreleased/TBD changes.
- License observed: **Apache-2.0**
- Paper: **ShinkaEvolve: Towards Open-Ended and Sample-Efficient Program Evolution**, arXiv `2509.19349`, ICLR 2026.
- Audit boundary: public repository pages, raw source files, documentation, skills, changelog and paper metadata. A byte-complete local clone was unavailable; claims below are limited to the source inventory in `shinkaevolve_source_manifest.json`.

## 1. Executive finding

ShinkaEvolve is a strong **program-search engine**: it maintains evolving programs and lineage, samples parents and inspirations, uses multiple LLMs as mutation operators, filters redundancy with novelty checks, separates populations through islands and archives, routes models with a cost-aware bandit, and overlaps proposals, evaluation and persistence asynchronously.

Epistemic Foundry v3 already owns the layers ShinkaEvolve intentionally does not try to be: source-grounded Claims, searched-scope accounting, evidence dependency, inference typing, asymmetric deliberation, side-effect authority, provenance, replay and Hypothesis Passports.

The correct v4 synthesis is therefore not “replace Foundry with Shinka” and not “attach a genetic loop to a literature RAG.” It is:

> **Place a governed quality-diversity Evolution Chamber inside Foundry. Let evolution propose, mutate, cross, challenge and prioritize typed scientific candidates. Keep evidence truth, evaluator authority, hidden holdout, statistical correction, replication and promotion outside the evolving population.**

## 2. What ShinkaEvolve actually contributes

### 2.1 Search unit and task boundary

The repository frames a task around an initial executable program, an evaluator, and a results directory. The core loop samples a parent and inspirations, asks an LLM mutation model for a patch or full program, validates/materializes it, evaluates it, persists the result and updates archive/island/meta-state. This is an excellent bounded contract when the candidate is code and a verifier exists.

### 2.2 Population search rather than one-shot generation

A population and lineage make failures, branches and reuse explicit. Parent strategies include weighted sampling and beam-style behavior. The weighted path normalizes `combined_score` around a median/MAD scale and multiplies it by `1/(1 + children_count)`, balancing performance and underexplored parent lineages. That mechanism is useful search engineering, but it is not a scientific evidence model.

### 2.3 Novelty rejection

The novelty path compares embeddings within an island and can ask an LLM whether a highly similar program is meaningfully different. Rejection sampling avoids spending evaluations on obvious duplicates. The important limitation for v4 is type safety: the inspected source returns “novel” from the LLM helper when no novelty client is configured, when a response is empty, or when the LLM check raises. In the outer high-similarity path, some read errors reject by default, but the helper semantics still make `NOVEL`, `UNASSESSED`, and `FAILED` insufficiently distinct for scientific novelty. v4 separates these states and never converts novelty-check failure into novelty.

### 2.4 Islands and archives

Island-local populations, migration and a global archive preserve diversity and transfer improvements. For scientific hypotheses, syntactic island separation is insufficient; v4 turns them into **epistemic niches** keyed by mechanism family, scope, evidence state, testability and causal status.

### 2.5 Model bandit

Shinka's documented AsymmetricUCB-style selection blends normalized reward/exploration with cost-aware cheapness and epsilon exploration. v4 retains this shape but changes the reward: immediate candidate score is only a proxy; validated hidden-stage improvement, challenge survival and replication produce delayed reward. Safety violations and evaluator leakage disqualify arms.

### 2.6 Prompt co-evolution

Evolving mutation prompts can discover productive search styles. It can also make the search system silently rewrite its own behavior and optimize the verifier. v4 treats prompts as quarantined `PromptGenome` objects. A prompt mutation is qualified independently and can affect future runs only; it cannot change the current evaluator, policy, holdout or promotion gate.

### 2.7 Async execution and persistence

The unified runner and documented async mode separate proposal/evaluation/database work and support bounded concurrency. v4 adopts the throughput pattern but requires exact reconciliation of proposed, evaluated, persisted, failed, cancelled and missing candidates. No `.filter(Boolean)` disappearance is allowed.

### 2.8 Agent skills

The repository provides setup, convert, run and inspect skills for Codex and Claude Code. This is a valuable progressive-disclosure UX. v4 expands it into setup/convert/run/inspect plus evaluator audit, challenge, archive, promotion, replication, replay, stop and Shinka adapter skills.

## 3. Why direct transplantation would fail as hypothesis validation

1. **A scalar score invites Goodhart pressure.** An evolutionary population will learn any stable evaluator weakness.
2. **The evaluator becomes part of the environment.** Reusing it across generations produces adaptive overfitting even when no candidate sees the raw hidden data.
3. **Program novelty is not hypothesis novelty.** Different code can encode the same scientific claim; similar code can instantiate a different causal mechanism.
4. **Best-of-many selection is biased.** The winning estimate is inflated unless search, testing and final estimation are separated.
5. **“Correct” is domain-relative.** Scientific support, causal identification, calibration, safety and replication cannot be compressed to one boolean.
6. **Prompt co-evolution can acquire authority.** Without a firewall, the generator may optimize or rewrite its own instructions.
7. **Archives can forget negative knowledge.** Score-based eviction removes nulls and counterexamples even though they are scientifically valuable.
8. **A novelty outage is not evidence of novelty.** Scientific state must fail closed or remain unassessed.
9. **A verifier-available benchmark is not automatically a real-world hypothesis test.** Measurement validity and scope still matter.
10. **Evolution creates a multiple-comparison problem.** Hundreds of adaptive candidates are not one preregistered test.

## 4. v4 adoption and correction matrix

| # | Shinka mechanism / missing capability | Decision | v4 implementation |
|---:|---|---|---|
| 1 | Program population and lineage | `ADOPT` | Generalize Program to typed Hypothesis/Challenge/Experiment genomes; preserve parent, inspiration, generation, island and mutation receipts. |
| 2 | Adaptive parent sampling | `ADOPT_WITH_CORRECTION` | Use expected information gain, uncertainty, coverage debt, replication debt, lineage saturation and cost; raw combined score is insufficient. |
| 3 | Children-count novelty bonus | `REPLACE` | Lineage saturation becomes one acquisition component; child count alone does not measure epistemic novelty. |
| 4 | Islands | `ADOPT_WITH_CORRECTION` | Use semantic islands specialized by mechanism/scope/method, with typed compatibility-gated migration. |
| 5 | Global archive | `ADOPT_WITH_CORRECTION` | Use quality-diversity archive that protects nulls, counterexamples, failed replications, unsafe failures and minority lineages. |
| 6 | Scalar combined score | `REJECT_AS_AUTHORITY` | Retain only as optional search hint; scientific promotion uses hard gates, FitnessVector, Pareto/niche analysis, statistics, replication and Parliament. |
| 7 | Correct boolean | `REPLACE` | Use typed stage outcomes and evidence classes; scientific correctness is not one evaluator boolean. |
| 8 | Embedding novelty | `ADOPT_AS_ONE_SIGNAL` | Add claim, mechanism topology, prediction, falsifier, scope, experiment, evidence and external prior-art novelty. |
| 9 | LLM novelty adjudication | `RESTRICT` | Require structured evidence and fail typed UNASSESSED/FAILED on outage; never infer novelty from empty/error response. |
| 10 | Novelty rejection sampling | `ADOPT_WITH_LIMITS` | Use bounded retries and preserve rejected candidates/reasons to prevent rediscovery loops. |
| 11 | LLM ensemble mutation | `ADOPT` | Route typed mutation operators to multiple models/providers under recorded RoleSpec and ContextManifest. |
| 12 | AsymmetricUCB model selection | `ADOPT_WITH_CORRECTION` | Use delayed holdout/replication reward, safety violations and uncertainty; raw local fitness cannot be the reward. |
| 13 | Cost-aware model routing | `ADOPT` | Maintain hard/soft budget semantics, estimated and realized cost receipts, and quality floors. |
| 14 | Prompt co-evolution | `QUARANTINE` | Prompt genomes may evolve only outside current run authority; independent qualification applies to future runs. |
| 15 | Evaluator mutability | `PROHIBIT_IN_RUN` | Evaluator defects become quarantined future-version proposals; current and completed runs are immutable. |
| 16 | Async proposal/evaluation | `ADOPT` | Separate bounded proposal, evaluation, persistence and side-effect lanes with explicit backpressure. |
| 17 | Controlled oversubscription | `ADOPT` | Use bounded queues, resource locks and headroom; reconcile every expected candidate. |
| 18 | SQLite/WAL local persistence | `ADOPT_FOR_LOCAL` | Use transactional local profile; team/production uses PostgreSQL/object store. Ledger and receipts remain canonical. |
| 19 | source_job_id idempotency | `ADOPT` | Generalize to candidate/effect idempotency keys and attempt reconciliation. |
| 20 | Side-effect worker | `ADOPT_WITH_AUTHORITY` | Every external action requires ActionIntent, capability lease, EffectReceipt and reconciliation. |
| 21 | Resume/checkpoint | `ADOPT_WITH_CORRECTION` | Checkpoint candidate populations, archive, islands, bandit, budget, testing ledger and evaluator hash atomically. |
| 22 | Diff/full/cross proposal modes | `ADOPT_WITH_TYPES` | Map to typed mutation and crossover operators; cross requires scope/measurement/unit/causal compatibility. |
| 23 | Fix mode | `ADOPT_AS_REPAIR` | A failed candidate may enter bounded repair lineage; repairs cannot change frozen objectives/evaluators. |
| 24 | Inspiration sampling | `ADOPT` | Record inspiration evidence/candidates and guard against evidence duplication and prompt contamination. |
| 25 | Local/Slurm execution | `ADOPT_AS_BACKEND` | Expose execution adapters behind capability and sandbox profiles; execution result class remains explicit. |
| 26 | Headless Codex/Claude mutation models | `ADOPT` | Treat as optional provider adapters with exact model/effort/context receipts and no authority ownership. |
| 27 | WebUI inspection | `ADOPT_WITH_CORRECTION` | Show Pareto fronts, niches, lineages, challenge survival, missing workers, statistics and hidden-stage status—not just top score. |
| 28 | setup skill | `ADOPT_WITH_EXPANSION` | Create run spec, genomes, evaluator/holdout, statistical family, niches, budgets and stop rules. |
| 29 | convert skill | `ADOPT_WITH_EXPANSION` | Map existing Shinka/model-search tasks into typed contracts and preserve semantic gaps. |
| 30 | run skill | `ADOPT_WITH_EXPANSION` | Run governed EVOLVE cycle with immutable evaluator, quality-diversity, Red Queen, statistics, replication and checkpoints. |
| 31 | inspect skill | `ADOPT_WITH_EXPANSION` | Inspect all scientific trade-offs and negative memory, not only top-performing code. |
| 32 | Evaluator contract generated by agent | `RESTRICT` | Agent may scaffold; independent evaluator qualification and human/policy approval are required. |
| 33 | Verifier-available task assumption | `ADOPT_AS_ELIGIBILITY` | Executable evolution requires a qualified verifier; otherwise limit to hypothesis generation/coverage, not empirical promotion. |
| 34 | Code correctness/readability objectives | `GENERALIZE` | Include as program-domain axes but add scientific grounding, calibration, causal validity, robustness and replicability. |
| 35 | Dynamic island creation | `ADOPT_WITH_GOVERNANCE` | Trigger on semantic stagnation/coverage debt, not only score plateau; record creation and migration rationale. |
| 36 | Prompt fitness tracking | `RESTRICT` | Use future-run holdout/replication utility and audit for policy drift. |
| 37 | Mutation feedback text | `ADOPT` | Separate public feedback from hidden evaluator details and record disclosure class. |
| 38 | Archive migration | `ADOPT_WITH_TYPES` | Require compatibility report and preserve source/target niche history. |
| 39 | Best-of-N/beam selection | `ADOPT_AS_OPTION` | Allowed for bounded search, but selection bias is logged and corrected. |
| 40 | Candidate metadata | `ADOPT` | Promote to strict schemas and append-only receipts rather than free-form metadata authority. |
| 41 | Public/private metrics | `ADOPT_WITH_FIREWALL` | Private metrics remain evaluator-only; public feedback is budgeted and cannot reveal hidden fixtures. |
| 42 | Novelty equals discovery | `REJECT` | Novelty is independent of truth, support, utility and replicability. |
| 43 | High score equals knowledge | `REJECT` | A high score is an evaluation observation subject to leakage, multiplicity, selection bias and replication. |
| 44 | Evolutionary success claim | `RESTRICT` | Require time-sliced/OOD/hidden evaluation, independent replication and corrected selection statistics. |
| 45 | Skill paper reference quality | `CORRECT` | Pin the actual ShinkaEvolve paper identifier and source manifest; documentation drift is a release-gate issue. |
| 46 | Optional Shinka dependency | `ADOPT` | Provide a pinned Apache-2.0 backend adapter; do not vendor or couple the core by default. |
| 47 | Open-ended search | `ADOPT_WITH_STOP_CONTRACT` | Use dry rounds, Pareto stability, coverage saturation, budget, safety and human stop certificates. |
| 48 | Challenge co-evolution | `ADD` | Introduce Red Queen challenge population to resist verifier overfit and expose boundaries. |
| 49 | Experiment co-evolution | `ADD` | Evolve discriminating tests jointly with hypotheses; rank by information gain, feasibility, risk and cost. |
| 50 | Statistical search governance | `ADD` | Track hypothesis families, repeated testing, alpha/e-values, multiple comparisons, winner's curse and selective inference. |
| 51 | Replication as selection stage | `ADD` | No high promotion from evolutionary search without appropriate independent replication. |
| 52 | Evaluator firewall | `ADD` | Seal evaluator bundles, hidden holdouts, leakage audits, metamorphic/adversarial tests and future-only update governance. |
| 53 | Surrogate triage | `ADD_WITH_LIMITS` | Use uncertainty-aware surrogate only to prioritize direct evaluation, never to replace it. |
| 54 | Negative-result memory | `ADD` | Archive nulls, failed replications, unsafe candidates and counterexamples as first-class scientific assets. |
| 55 | Promotion authority | `PRESERVE_FOUNDRY` | Only deterministic gates + Evidence Parliament + independent attestation + human/policy authority can promote. |

## 5. v4 architectural consequence

The new **Evolution Chamber** is a search subsystem, not a truth subsystem.

```text
Source-grounded Evidence + falsifiable Frame
                    │
                    ▼
          Typed seed populations
   Hypotheses / Challenges / Experiments
                    │
                    ▼
   Parent selection + typed mutation/crossover
                    │
                    ▼
      Verifier Firewall evaluation cascade
                    │
          ┌─────────┴──────────┐
          ▼                    ▼
  Pareto / MAP-Elites     Red Queen attacks
          │                    │
          └─────────┬──────────┘
                    ▼
      multiplicity + selective inference
                    ▼
       hidden/OOD + independent replication
                    ▼
        Evidence Parliament + attestation
                    ▼
        Hypothesis Passport revision
```

The following remain outside the evolutionary mutation surface:

- Foundry Kernel authority and policy
- Noetic Ledger history
- current RunSpec and scope
- current evaluator bundle
- hidden holdout bytes and ACLs
- hard safety/provenance gates
- release and promotion authority
- prior decisions and source evidence

## 6. Optional Shinka backend boundary

ShinkaEvolve is integrated as an optional Apache-2.0 **executable-program search backend**. The adapter must pin an exact source revision or package digest at implementation time. It may supply program mutation, islands, archive mechanics, model routing and async evaluation. Foundry maps those outputs into candidate lineages, mutation receipts, stage results and effect receipts.

The adapter is rejected or restricted if it cannot demonstrate:

- candidate/evaluation/persistence count reconciliation;
- evaluator and hidden-holdout separation;
- sandbox isolation and capability control;
- resume and idempotency integrity;
- typed novelty failure semantics;
- raw score isolation from scientific promotion;
- exact backend/version provenance.

## 7. Source-specific defects and limitations carried into v4 tests

- `novelty_judge.py`: the LLM helper accepts novelty on absent client, empty response and exception; v4 has explicit tests that these become `UNASSESSED` or `FAILED`.
- `parents.py`: weighted sampling is dominated by `combined_score` and `children_count`; v4 adds epistemic acquisition components and uncertainty.
- skill layer: setup/run/inspect is useful but lacks evaluator qualification, holdout leakage, statistical search correction, replication and promotion contracts.
- prompt co-evolution: productive but authority-sensitive; v4 quarantines it.
- archive/islands: diversity-preserving but not semantically scientific by default; v4 uses epistemic niches and protected negative memory.
- async throughput: valuable but scientifically incomplete without missing-worker and effect reconciliation.
- release/main drift: the latest release and current main can differ; v4 requires exact revision pinning rather than “latest.”

## 8. What v4 does not claim

This study does not establish that ShinkaEvolve is unsafe, incorrect, or unsuitable for its intended program-optimization tasks. Several v4 controls address a **different and stricter product objective**: evolving and validating scientific hypotheses under evidence, causal, statistical and governance constraints.

The package is a specification bundle. It does not claim a working v4 runtime, a completed Shinka adapter, production security, or superior real-world discovery performance. Those require the release gates defined in `manifests/acceptance_matrix.yaml`.
