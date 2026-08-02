#!/usr/bin/env python3
"""Materialize the bounded J02 production skill and reference surfaces."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
BLUEPRINT = ROOT / "plugin_blueprint/epistemic-foundry/skills"
PRODUCTION = ROOT / "plugins/epistemic-foundry/skills"

DESCRIPTIONS = {
    "foundry": (
        "Route research and evidence-synthesis requests. Use for claim validation; "
        "do not use for ordinary editing or casual questions."
    ),
    "foundry-admin": "Explicit-only administration for health, policy, consent, backup, migration, rollback, signing, and recovery.",
    "foundry-aporia": "Turn contradictions into competing mechanisms, moderators, and discriminating tests without forcing one explanation.",
    "foundry-archive": "Inspect or rebalance the quality-diversity archive while preserving negative, unsafe, failed, and minority lineages.",
    "foundry-atlas": "Map evidence coverage, contradictions, dependencies, method compatibility, and searched or unsearched gaps.",
    "foundry-challenge": "Generate, run, replicate, and archive safe Red Queen challenges for hypotheses or evaluators.",
    "foundry-claim-forge": "Extract atomic source-span ClaimCards with scope, method, stance, quantitative context, and provenance.",
    "foundry-domain-pack": "Author a versioned DomainPack for ontology, measurement, methods, evidence hierarchy, coverage, and contradiction rules.",
    "foundry-evaluator-audit": "Qualify an evaluator bundle as a fallible scientific instrument before scoring or after a defect proposal.",
    "foundry-evolution-replay": "Replay an evolution cycle or lineage from a checkpoint under strict, semantic, or provider-nondeterministic equivalence.",
    "foundry-evolution-stop": "Stop, pause, or cancel evolution safely with a typed stop certificate and atomic checkpoint.",
    "foundry-evolve-convert": "Convert a hypothesis, model-search, benchmark, or Shinka task into typed genomes and evaluator contracts.",
    "foundry-evolve-inspect": "Inspect populations, Pareto fronts, niches, lineages, challenges, receipts, bias, and unresolved candidates without mutation.",
    "foundry-evolve-run": "Run or resume governed evolution with bounded workers, immutable evaluators, receipts, checkpoints, and explicit stop conditions.",
    "foundry-evolve-setup": "Create a typed EvolutionRunSpec, seed genomes, evaluator and holdout manifests, diversity axes, budgets, and stop rules.",
    "foundry-evolve": "Route a falsifiable research problem into governed EVOLVE search; not for a single lookup.",
    "foundry-intake": "Frame research ideas into scoped claims, predictions, mechanisms, alternatives, and falsifiers before evidence search.",
    "foundry-map": "Map code, schemas, workflows, papers, data, claims, evidence, artifacts, tests, and authority dependencies.",
    "foundry-observe": "Acquire relation-aware evidence with receipts across support, counter, null, boundary, method, temporal, and novelty lanes.",
    "foundry-parliament": "Run blind asymmetric evidence-gated deliberation with audits, cross-examination, minority report, judge, and attestation.",
    "foundry-passport": "Build or inspect a provenance-bound Hypothesis Passport after evidence and gate artifacts exist.",
    "foundry-plugin-dev": "Build, test, audit, package, migrate, or release Epistemic Foundry without self-approval or unsupported readiness claims.",
    "foundry-promote-evolved": "Review an evolved candidate after sealed evaluation, statistics, replication, Parliament, and independent attestation.",
    "foundry-reason": "Apply typed inductive, deductive, abductive, contradiction, and causal reasoning without converting plausibility into proof.",
    "foundry-recall": "Retrieve prior decisions only when needed and permitted; memory is not source evidence.",
    "foundry-replay": "Replay a run, compare strict or semantic outputs, and propagate staleness without overwriting prior artifacts.",
    "foundry-replicate": "Plan and execute an independent preregistered replication using clean executors, data, methods, or seeds.",
    "foundry-shinka-adapter": "Use pinned ShinkaEvolve only as an optional program-search backend behind Foundry authority.",
    "foundry-validation": "Preregister and execute validation under capability leases and receipts without relabeling computation as empirical evidence.",
}

PARENT_ROUTER = {"foundry"}
IMPLICIT_SAFE = {
    "foundry-intake",
    "foundry-claim-forge",
    "foundry-observe",
    "foundry-atlas",
    "foundry-reason",
    "foundry-aporia",
    "foundry-map",
    "foundry-passport",
    "foundry-evolve-inspect",
}
PARENT_ROUTED = {
    "foundry-parliament",
    "foundry-evolve",
    "foundry-evolve-setup",
    "foundry-evaluator-audit",
    "foundry-challenge",
    "foundry-archive",
}

REFERENCES = {
    "core/constitution.md": """# Foundry constitution

- Canonical state, authority, receipts, gates, and replay belong to the Foundry Kernel and Noetic Ledger.
- Claims resolve to immutable source evidence; an Insight requires scope, prediction, falsifier, and searched-scope accounting.
- Counter, null, boundary, method, leakage, and OOD evidence remain visible, and dependency clusters prevent evidence-count inflation.
- Evolution and models may propose but never certify themselves. Majority vote, scalar fitness, confidence, or novelty cannot promote.
- Evaluator and holdout integrity are non-waivable. Honest `UNDERDETERMINED` and `BLOCKED` outcomes are valid.
- Domain-specific ontology and measurement rules stay in versioned DomainPacks rather than the domain-neutral kernel.
""",
    "core/status-receipts.md": """# Status, receipts, and revisions

- Use `PASS`, `FAIL`, `BLOCKED`, and `SPEC_GAP` truthfully: implementation failure is not a contract gap, and missing infrastructure is not failure.
- Every effect starts from an `ActionIntent` and resolves through an `EffectReceipt`; every artifact claim has an `ArtifactReceipt`.
- Canonical records are immutable revisions. Corrections, promotions, invalidations, and replays append new records rather than overwriting history.
- Retries bind an idempotency key and canonical request hash. Same key plus different input is a conflict.
- A crash without a resolving receipt is not success. Reconcile external state and ledger state before retrying or reporting completion.
""",
    "router/e0-e5-routing.md": """# E0-E5 routing

- The deterministic work classifier selects the maximum signal floor from E0 transform through E5 novelty or ambiguity.
- FORGE phases are Interview, Frame, Observe, Reason, Govern, and Emit; only phases required by the sealed classification may execute.
- Interview resolves missing or conflicting research contracts. It is distinct from the human gate for high-risk effects or release.
- The parent skill routes to the minimum applicable child skill and grants no state, approval, capability, or execution authority.
- Skill instructions and references load only after a valid routing decision; sensitive or effectful skills require exact authorization.
""",
    "evidence/claim-search.md": """# Claims and evidence search

- A `ClaimCard` is atomic and binds exact `SourceSpan`, provenance, scope, method, author stance, and quantitative context.
- A typed `QueryPlan` searches support, counter, null, boundary, method, temporal, and novelty lanes as applicable.
- `UNSEARCHED` is never rewritten as `SEARCHED_NONE`; absence and novelty claims cannot exceed the searched corpus and time boundary.
- A `SearchCompletenessCertificate` records lanes, sources, queries, stop rules, limitations, and unresolved access before synthesis.
- Retrieval rank, source trust, methodological strength, and scientific support remain separate dimensions.
""",
    "evidence/scope-method-dependency.md": """# Scope, method, and dependency

- Compare claims through a typed `ScopeVector`; disagreement outside overlapping population, setting, intervention, outcome, or time is conditional, not absolute.
- Measurement constructs, instruments, units, transformations, and method compatibility must be explicit before evidence aggregation.
- Shared samples, datasets, laboratories, preprints, models, or citation chains form dependency clusters and do not count as independent evidence.
- Method vetoes and scope mismatch constrain conclusions and promotion ceilings even when supporting item counts are high.
- Contradiction records preserve the conditions under which each result holds and the observation that would discriminate them.
""",
    "reasoning/typed-modes.md": """# Typed reasoning modes

- Induction summarizes observed patterns; deduction derives consequences from premises; abduction proposes the best current explanation.
- Causal identification requires explicit assumptions, interventions or counterfactual structure, confounder handling, and falsifiable implications.
- Simulation, association, plausibility, and model fit are not relabeled as empirical or causal proof.
- An `ArgumentGraph` types premises, claims, warrants, objections, dependencies, and unresolved conflicts.
- Competing explanations and minority reasoning remain inspectable when evidence underdetermines a single conclusion.
""",
    "parliament/asymmetric-gates.md": """# Evidence Parliament

- Parliament receives sealed, provenance-bound briefs; candidate persuasion cannot alter the evidence pack or deterministic gates.
- Defense is balanced by prosecutor, method, scope, causal, novelty, and dependency audits with strongest counterevidence visible.
- Cross-examination records unresolved objections, a minority report, and the judge's evidence-bound rationale.
- Deterministic non-waivable failures cannot be overturned by majority vote or human preference.
- Independent attestation is separated from candidate generation, implementation, first adjudication, mutable prompt lineage, and commit authority.
""",
    "passport/promotion.md": """# Passport and promotion

- A `HypothesisPassport` is an immutable provenance view over claims, evidence, limits, validation, replication, gates, and decisions.
- Promotion levels are `INBOX`, `CANDIDATE`, `LITERATURE_GROUNDED`, `VALIDATION_SCREENED`, `EMPIRICALLY_TESTED`, and `REPLICATED`.
- `PROMOTE` grants the requested level; `CONDITIONAL` grants a strictly lower but higher-than-current level. Non-grant decisions use `granted_level: null`.
- Replication, leakage, method, statistics, Parliament, attestation, policy, and receipt gates impose ceilings; no scalar score overrides them.
- Promotion commits use expected revisions, capability leases, receipts, and immutable new Passport and decision revisions.
""",
    "validation/replication.md": """# Validation and replication

- A preregistered `ValidationPlan` states target, data, evaluator, metrics, thresholds, falsifiers, budget, and analysis before execution.
- Empirical, formal, computational, observational, and simulated evidence classes remain explicit and are not interchangeable.
- Validation effects require capability leases, execution receipts, results, reconciliation, and limitation records.
- A `ReplicationPlan` seals independence criteria, executor, data or seeds, methods, analysis, and outcomes before access to results.
- `REPLICATED`, `PARTIAL`, `INCONCLUSIVE`, `FAILED`, and `BLOCKED` constrain promotion without erasing prior evidence.
""",
    "evolution/run-genomes.md": """# Evolution runs and genomes

- An `EvolutionRunSpec` resolves every logical reference to exact version or revision, SHA-256, resolver identity, locator, authority, and reproducibility class.
- EVOLVE mutates typed hypothesis or program genomes while RunSpec, policy, evaluator, holdout, evidence, and release state remain immutable.
- Parent selection, operators, routing, candidates, lineages, counts, budgets, and checkpoints produce replayable receipts.
- Generated, evaluated, persisted, failed, cancelled, and missing candidates reconcile exactly.
- Stop conditions emit a typed certificate and atomic checkpoint; failure, leakage, or authority uncertainty stops the run fail-closed.
""",
    "evolution/verifier-statistics.md": """# Verifier firewall and statistics

- Evaluator bundles are qualified and immutable within a run; candidates, generators, prompts, and backends cannot write evaluators.
- Hidden and OOD holdouts are access-controlled. Candidate access, unblinding, contamination, or gaming invalidates evaluation rather than lowering a score.
- Adaptive search records a sequential-testing ledger, multiple-testing correction, selective-inference report, winner path, and holdout consumption.
- Public, hidden, OOD, adversarial, and metamorphic stages remain distinct with complete receipts.
- A verifier result is evidence for deterministic gates, not autonomous promotion authority.
""",
    "evolution/archive-red-queen.md": """# Archive and Red Queen

- The quality-diversity archive preserves Pareto tradeoffs, epistemic niches, lineages, counterexamples, failed replications, unsafe failures, and minority candidates.
- Archive insertion, replacement, migration, and pruning follow sealed deterministic policy and retain provenance.
- Red Queen challenges target the strongest counterexample, null, confounder, method, leakage, or OOD failure relevant to the candidate.
- Challenge generation and execution are separated from promotion; relevance, reproducibility, and receipts are audited.
- Negative knowledge is protected from score-based deletion where policy permits retention.
""",
    "context/memory-replay.md": """# Memory, context, and replay

- Memory classes distinguish canonical state, source evidence, working context, user-consented preference, and cache; memory is not source evidence.
- Retrieval obeys workspace, consent, retention, sensitivity, provenance, and purpose limits.
- A `ContextCapsule` binds included artifacts, exclusions, hashes, freshness, authority, and compaction recovery without silently broadening context.
- Strict replay reuses identical sealed artifacts; semantic replay creates a new revision under a new policy, model, or implementation version.
- Source, policy, ontology, parser, prompt, model, or dependency changes propagate explicit staleness rather than mutating history.
""",
    "extensions/map-domain-pack.md": """# Mapping and DomainPacks

- Workspace Cartographer maps code, schemas, workflows, papers, datasets, claims, artifacts, tests, authority, and blast radius.
- Baseline graph centrality is computed from the graph; query relevance and risk are separate rankings and are not mislabeled as centrality.
- A versioned `DomainPack` owns ontology, constructs, units, measurement rules, method comparability, evidence hierarchy, coverage axes, and contradiction rules.
- Domain extensions may specialize interpretation but cannot weaken kernel provenance, receipts, gates, or status semantics.
- Changes record affected nodes, migration needs, validation evidence, and unresolved scope.
""",
    "plugin/security-administration.md": """# Plugin security and administration

- Plugin shells, hooks, skills, UIs, SDKs, and search backends are adapters; Kernel capability and ledger checks remain authoritative.
- Hooks are advisory enforcement surfaces and cannot mint approval, rewrite state, reveal holdouts, or certify completion.
- Secrets never enter prompts, artifacts, logs, receipts, or source. Capabilities are least-privilege, scoped, short-lived, and revocable.
- Administrative mutations require dry-run, expected revision, human or policy approval, backup, signed receipts, rollback, and reconciliation.
- Integrity uncertainty enters safe mode; recovery preserves immutable evidence and audit history.
""",
    "backends/shinka.md": """# Shinka backend boundary

- ShinkaEvolve is an optional executable-program search backend, never Foundry authority.
- Use an exact source commit, package digest, or container digest with license, configuration, toolchain, sandbox, and qualification receipts.
- Raw combined score, correctness, novelty, island, archive, and bandit observations are advisory and map through typed Foundry contracts.
- The backend cannot read hidden holdouts, mutate evaluators or policy, issue approval, commit promotion, or rewrite the ledger.
- Apache-2.0 attribution and redistribution obligations remain attached to any included upstream material.
""",
    "plugin/development-release.md": """# Development and release

- Execute dependency-ready A-Z work packages within exact write scopes; shared-contract changes require product-owner authority.
- Maker, reviewer, integrator, and attestor duties remain separated where the execution contract permits it.
- Every package records commands, machine-readable verification, review, regression impact, receipts, and immutable prior attempts.
- Build, migration, install, rollback, recovery, compatibility, security, and production-load gates precede release claims.
- A passing package is not product completion, release readiness, deployment, or production proof unless the corresponding gates and receipts pass.
""",
}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    path.write_bytes(normalized.encode("utf-8"))


def body_after_frontmatter(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    match = re.match(r"\A---\n[\s\S]*?\n---\n(?P<body>[\s\S]*)\Z", normalized)
    if match is None:
        raise SystemExit("invalid SKILL.md frontmatter")
    return match.group("body")


def disposition(skill_id: str) -> str:
    if skill_id in PARENT_ROUTER:
        return "PARENT_ROUTER"
    if skill_id in IMPLICIT_SAFE:
        return "IMPLICIT_SAFE"
    if skill_id in PARENT_ROUTED:
        return "PARENT_ROUTED"
    return "EXPLICIT_ONLY"


def child_skill_frontmatter(skill_id: str, description: str, body: str) -> str:
    """Apply only the two child frontmatter changes authorized by J02."""
    return (
        "---\n"
        f"name: {skill_id}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "metadata:\n"
        '  architecture-version: "4.0.0"\n'
        '  status: "ACTIVE"\n'
        "---\n"
        f"{body}"
    )


def parent_skill_frontmatter(description: str, body: str) -> str:
    """Preserve the J01 parent policy fields without adding J02-only metadata."""
    return (
        "---\n"
        "name: foundry\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "metadata:\n"
        '  architecture-version: "4.0.0"\n'
        '  status: "ACTIVE"\n'
        "  allow_implicit_invocation: true\n"
        "  sensitive: false\n"
        "  side_effecting: false\n"
        "---\n"
        f"{body}"
    )


def child_agent(skill_id: str, description: str) -> str:
    implicit = disposition(skill_id) in {"PARENT_ROUTER", "IMPLICIT_SAFE"}
    display = skill_id.removeprefix("foundry-").replace("-", " ").title()
    return (
        "interface:\n"
        f"  display_name: {json.dumps(display)}\n"
        f"  short_description: {json.dumps(description, ensure_ascii=False)}\n"
        "policy:\n"
        f"  invocation_disposition: {disposition(skill_id)}\n"
        f"  allow_implicit_invocation: {str(implicit).lower()}\n"
        "  sensitive: false\n"
        "  side_effecting: false\n"
        "  load_full_instructions: on_demand\n"
    )


def materialize_skills() -> None:
    blueprint_ids = sorted(path.name for path in BLUEPRINT.iterdir() if path.is_dir())
    if blueprint_ids != sorted(DESCRIPTIONS) or len(blueprint_ids) != 29:
        raise SystemExit("blueprint skill inventory is not the approved 29-skill set")

    for skill_id in blueprint_ids:
        description = DESCRIPTIONS[skill_id]
        if len(description.encode("utf-8")) > 140:
            raise SystemExit(f"description exceeds 140 bytes: {skill_id}")
        if skill_id == "foundry":
            source = PRODUCTION / skill_id / "SKILL.md"
        else:
            source = BLUEPRINT / skill_id / "SKILL.md"
        body = body_after_frontmatter(source.read_text(encoding="utf-8"))
        target = PRODUCTION / skill_id / "SKILL.md"
        rendered = (
            parent_skill_frontmatter(description, body)
            if skill_id == "foundry"
            else child_skill_frontmatter(skill_id, description, body)
        )
        write_text(target, rendered)

        agent_target = PRODUCTION / skill_id / "agents/openai.yaml"
        if skill_id == "foundry":
            existing = agent_target.read_text(encoding="utf-8").replace("\r\n", "\n")
            if "invocation_disposition:" not in existing:
                existing = existing.replace(
                    "policy:\n", "policy:\n  invocation_disposition: PARENT_ROUTER\n", 1
                )
            write_text(agent_target, existing)
        else:
            write_text(agent_target, child_agent(skill_id, description))


def materialize_references() -> None:
    reference_root = PRODUCTION / "foundry/references"
    if len(REFERENCES) != 17:
        raise SystemExit("reference inventory is not the approved 17-reference set")
    for relative_path, content in sorted(REFERENCES.items()):
        if len(content.encode("utf-8")) > 4096:
            raise SystemExit(f"reference exceeds 4096 bytes: {relative_path}")
        write_text(reference_root / relative_path, content)


def main() -> int:
    materialize_skills()
    materialize_references()
    print(
        json.dumps(
            {
                "production_skill_count": 29,
                "reference_count": 17,
                "status": "MATERIALIZED",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
