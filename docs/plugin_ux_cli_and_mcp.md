# Plugin UX, CLI, MCP and API contract

## 1. User-facing principle

The plugin exposes the minimum state needed to make rigor visible. It does not force users to memorize internal graph concepts, and it never turns a missing backend or missing search lane into a deceptively clean answer.

## 2. Primary commands

```text
efoundry init
efoundry doctor [--json]
efoundry status [--session ID] [--json]

efoundry forge interview|frame|observe|reason|gate|export
efoundry forge reopen <phase>
efoundry forge history
efoundry forge reset --reason ...

efoundry corpus add|list|verify|update
efoundry claim extract|show|verify|supersede
efoundry atlas coverage|contradictions|dependencies|methods
efoundry parliament run|status|docket|attest
efoundry aporia generate|compare|test
efoundry validate target|plan|run|reconcile
efoundry passport show|export|supersede

efoundry recall search|policy|forget
efoundry map workspace|repo|corpus|artifact
efoundry skill discover|inspect|quarantine|approve|activate|lock
efoundry replay run|compare|drift
efoundry backup create|verify|restore
efoundry plugin capability|migrate|rollback|uninstall
```

Every mutating command supports `--dry-run`, `--json`, `--expected-revision`, and an idempotency key. PATH-less invocation through the installed plugin root is a release gate.

## 3. MCP tool surface

Read tools:

- `foundry.status`
- `foundry.health`
- `foundry.session.get`
- `foundry.artifact.get`
- `foundry.claim.get`
- `foundry.atlas.query`
- `foundry.passport.get`
- `foundry.replay.diff`
- `foundry.map.query`

Planning tools:

- `foundry.frame.compile`
- `foundry.search.plan`
- `foundry.parliament.plan`
- `foundry.validation.plan`

Mutating/executing tools:

- `foundry.session.transition`
- `foundry.corpus.register`
- `foundry.search.execute`
- `foundry.claim.promote`
- `foundry.parliament.execute`
- `foundry.validation.execute`
- `foundry.passport.publish`
- `foundry.memory.write`
- `foundry.skill.activate`

Mutating tools require ActionIntent, policy evaluation, optional approval, capability lease, effect receipt, and reconciliation. Tool descriptions must state side effects and authority boundaries.

## 4. Dashboard states

The Foundry Console has seven primary views:

1. **Forge Docket** — phase, blockers, artifact obligations, revisions.
2. **Claim Forge** — source span, atomic claim, scope, method, promotion status.
3. **Epistemic Atlas** — coverage cells, search state, dependencies, contradiction classes.
4. **Evidence Parliament** — role briefs, attacks, vetoes, minority report, missing agents.
5. **Aporia Lab** — competing explanations, moderators, discriminating tests.
6. **Hypothesis Passport** — verdict dimensions, evidence, uncertainty, lifecycle.
7. **Health and Replay** — capabilities, migrations, drift, effects, backups.

Read models have four states:

```text
READY
EMPTY_CONFIRMED
DEGRADED
UNAVAILABLE
```

A network or backend error may never be rendered as `EMPTY_CONFIRMED`.

## 5. Contract generation

- JSON Schema is canonical for domain artifacts.
- OpenAPI is canonical for HTTP transport.
- TypeScript and Python models are generated.
- UI client is generated from OpenAPI.
- MCP tool schemas reference the same canonical definitions.
- Contract tests compare CLI JSON, MCP output, HTTP output, and persisted artifact shape.
- Development middleware and packaged server call the same handler services.

## 6. Local UI security

- bind to loopback by default;
- random per-run bearer token or OS-authenticated channel;
- strict Origin and CSRF checks for writes;
- Content Security Policy;
- no raw HTML rendering from evidence;
- source spans escaped and separately downloadable;
- no secrets in browser storage;
- explicit profile/workspace indicator;
- session timeout and revocation;
- audit receipt for approval/override actions.

## 7. Notifications

Notification adapters are optional. Default policy allows:

- run status;
- blocker summary;
- approval request with artifact IDs;
- final Passport availability.

Default policy denies:

- raw PDF/full-text export;
- secrets;
- arbitrary shell command submission;
- unredacted evidence excerpts;
- remote phase override.

## 8. Error model

Stable error envelope:

```json
{
  "code": "FORGE_GATE_FAILED",
  "message": "Observe phase is missing a counterevidence search receipt.",
  "category": "contract",
  "retryable": false,
  "session_id": "FS-...",
  "expected_revision": 12,
  "details": {"missing": ["counterevidence"]},
  "remediation": ["run `efoundry forge observe --lane counterevidence`"]
}
```

Errors are categorized as contract, policy, capability, dependency, transient, integrity, migration, provider, or user decision.
