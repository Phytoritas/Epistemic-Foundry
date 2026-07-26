# Evaluation, calibration, and architecture ablation

## Evaluation suites

### Parsing
Reading order, section boundaries, tables, figures, formulas, citations, page/bbox/character locators.

### Extraction
Candidate recall, atomicity, author stance, scope, method, quantitative fields, grounding, unsupported promotion.

### Retrieval
Recall@k and nDCG by evidence role, null/counter/boundary/method recall, diversity, dependency correction, completeness receipts.

### Reasoning
Verdict accuracy, causal overclaim, alternative explanation coverage, proof trace, method veto, minority retention.

### Security
Prompt-injection escape, active-content handling, malformed source behavior, data exfiltration, secret leakage.

### Runtime
DAG completeness, resource conflicts, retries, idempotency, checkpoint/replay, backup/restore, budget and cancellation.

## Required challenge sets

- known-false hypotheses,
- scope-mismatch pseudo-contradictions,
- method-incompatible measurements,
- duplicate publications and shared datasets,
- retracted/corrected sources,
- poisoned metadata and instruction-bearing documents,
- temporal holdouts,
- confidence traps with fluent but unsupported claims.

## Calibration

Report Brier score, Expected Calibration Error, coverage-accuracy curves, selective risk under abstention, and decision stability. Do not calibrate a single scalar across incompatible epistemic dimensions.

## Ablations

Compare:
- single agent,
- symmetric multi-agent debate,
- asymmetric Parliament,
- no counter lane,
- no dependency correction,
- no method veto,
- no minority report,
- no deterministic gates,
- full context versus compact EvidencePack.
