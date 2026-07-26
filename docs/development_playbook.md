# Development Playbook

## 1. Preflight

```text
git status --short --branch
read authority chain
validate YAML/JSON
compute ready work packages
audit data and shared-resource edges
confirm exclusive write scopes
```

Pre-existing dirty changes are user work. Never reset, clean, stash, overwrite, or include them without explicit authority.

## 2. Select work

A work package is READY only when:
- every `depends_on` package is PASS
- required checkpoint exists
- no unresolved P0/P1 finding affects it
- its write scope is not leased
- shared schema/API is frozen
- required external prerequisite is available

## 3. Dispatch

Each maker receives one `WorkNodeContract`:

```yaml
work_package_id: B02
goal: Implement the GROBID adapter
authority_files:
  - MASTER_SPEC.md
  - manifests/development_manifest.yaml
  - workflows/corpus_ingest.workflow.yaml
allowed_read_scope:
  - src/epistemic_foundry/domain/**
  - schemas/**
exclusive_write_scope:
  - src/epistemic_foundry/ingest/grobid/**
  - tests/ingest/test_grobid*
required_checks:
  - pytest tests/ingest/test_grobid_adapter.py
forbidden_actions:
  - modify canonical schemas
  - add another parser framework
  - call external network outside configured GROBID endpoint
escalation:
  - TEI/source-span contract is ambiguous
```

## 4. Maker loop

```text
inspect
→ write a test/fixture for the contract
→ implement minimal change
→ run targeted checks
→ run affected regression
→ inspect diff
→ emit ResultEnvelope
```

The maker does not merge or approve.

## 5. Review

Reviewer returns findings only when:
- contract violated
- correctness/replay/security/data integrity at risk
- test does not exercise claimed behavior
- failure path silent
- scientific label/evidence layer wrong

Each finding:
```yaml
severity: P0|P1|P2
file: path
line:
contract:
observation:
impact:
reproducer:
minimal_fix:
confidence:
```

## 6. Integration

Integrator:
1. verifies review disposition
2. verifies base checkpoint
3. merges declared order
4. runs contract compatibility
5. runs full phase gate
6. reconciles expected artifacts
7. creates checkpoint

Leaf defects return to leaf owner. Integrator should not hide them in glue.

## 7. Retry

Retry only for transient failures. Do not retry:
- schema mismatch
- permission denial
- deterministic test failure
- SPEC_GAP
- invalid scientific grounding

Every retry increments attempt and reuses idempotency/effect policy.

## 8. Status semantics

- `PASS`: all checks + review + evidence
- `FAIL`: contract violated; actionable defect
- `BLOCKED`: clear contract, unavailable external requirement
- `SPEC_GAP`: contract incomplete/conflicting
- `PARTIAL`: useful artifacts, but cannot claim exit criteria

## 9. Phase gates

At the end of each phase:
- manifest dependency audit
- no overlapping ownership
- schema compatibility
- migration/replay
- security smoke
- traceability matrix
- open-risk review
- checkpoint hash

## 10. Completion report

```yaml
work_package_id:
base_checkpoint:
status:
changed_files:
checks:
  - command:
    exit_code:
    artifact:
review:
  agent:
  status:
  findings_resolved:
output_artifacts:
open_risks:
not_verified:
next_ready:
```
