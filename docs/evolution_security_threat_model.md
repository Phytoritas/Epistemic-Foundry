# Evolution Security and Scientific-Integrity Threat Model

## Assets

- source evidence and licenses;
- candidate genomes and lineage;
- evaluator bundles;
- hidden/OOD data;
- policies and promotion gates;
- secrets and provider credentials;
- execution sandbox and host;
- Noetic Ledger and effect receipts;
- archive and negative memory;
- release/signing identity.

## Adversaries and failure agents

- malicious or compromised candidate code;
- prompt injection from papers/web/data;
- reward-hacking candidate;
- accidental evaluator leakage;
- compromised third-party backend/skill;
- model hallucination;
- insider override;
- concurrent worker race;
- corrupted checkpoint;
- overconfident UI.

## High-priority threats

| Threat | Control |
|---|---|
| candidate reads holdout | separate storage/identity/network, ACL logs, leakage audit |
| candidate mutates evaluator | immutable bundle, read-only mount, authority denial |
| shell/network abuse | sandbox profile, capability lease, egress deny, resource quotas |
| archive poisoning | schema/provenance validation, independent archive curator |
| false completion | expected-count reconciliation and effect receipts |
| prompt genome authority drift | quarantine and future-run qualification |
| third-party backend drift | exact revision/digest and adapter qualification |
| hidden test encoded in feedback | disclosure budget and differential feedback review |
| score spoofing | evaluator-owned result channel and artifact hash |
| cross-workspace exfiltration | workspace identity and deny-by-default paths |
| unsafe challenge | safety class and controlled execution |
| rollback erases evidence | append-only ledger and checkpoint lineage |

## Sandbox classes

- `pure`: no file/network, deterministic transform;
- `bounded_compute`: temporary storage, no network;
- `controlled_data`: approved read-only datasets;
- `external_service`: allowlisted egress with receipts;
- `restricted`: human approval and specialized isolation.

Candidate-generated code never runs in the plugin host process.

## Incident handling

Leakage, evaluator mutation, unreconciled effects, archive corruption or sandbox escape cause immediate typed stop, checkpoint quarantine, credential rotation where applicable, impact analysis and explicit requalification. Prior results are marked potentially invalid; they are not silently deleted.
