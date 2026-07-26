# Optional ShinkaEvolve Backend Adapter Contract

## 1. Position

ShinkaEvolve may be used for executable-program mutation and evaluation. It is an adapter behind Foundry Kernel, not a dependency of the domain-neutral core and not a scientific promotion authority.

## 2. Pinning

Implementation must record:

- repository/package origin;
- exact commit or immutable package digest;
- package version;
- Apache-2.0 license;
- Python/dependency lock;
- enabled and disabled features;
- adapter version;
- sandbox profile;
- source inventory hash.

“Latest” is not a reproducible version.

## 3. Contract mapping

| Shinka concept | Foundry mapping |
|---|---|
| Program | executable candidate artifact + CandidateLineage |
| parent/inspiration | lineage parents/inspiration IDs |
| generation/island | EvolutionCheckpoint / IslandState |
| combined score | advisory search metric only |
| correctness | typed StageEvaluationResult |
| archive | projection into Epistemic Archive |
| novelty metadata | partial NoveltyVector signal |
| LLM bandit | OperatorBanditState / ModelRoutingReceipt |
| system prompt archive | quarantined PromptGenome |
| evaluator output | evaluator-owned FitnessEvidenceReceipt |
| database event/attempt | Noetic Ledger event/attempt/effect receipts |

## 4. Required corrections

- novelty helper outages map to `UNASSESSED`/`FAILED`, not novel;
- hidden evaluator data is unavailable to mutation models and candidate code;
- evaluator or prompt changes cannot affect the current run;
- all candidate counts reconcile;
- raw score cannot promote a hypothesis;
- archive migration preserves scientific entry class and niche;
- adaptive selection feeds statistical ledgers;
- executable code runs in Foundry sandbox profiles;
- resume checks evaluator, policy, archive and budget hashes.

## 5. Qualification tests

The adapter must pass:

1. exact source/license resolution;
2. task conversion round trip;
3. candidate lineage fidelity;
4. expected-count reconciliation under worker failure;
5. crash/resume and idempotency;
6. novelty outage semantics;
7. evaluator/holdout isolation;
8. sandbox/egress/resource controls;
9. score/evidence-class separation;
10. delayed-reward bandit mapping;
11. prompt-coevolution quarantine;
12. clean uninstall/rollback.

## 6. Fallback

When Shinka is unavailable or unqualified, Foundry's typed Evolution Chamber may use another backend or run a non-executable hypothesis-only profile. The UI and Passport state show the actual backend and validation ceiling.
