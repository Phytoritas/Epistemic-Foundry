# Decision

Do **not** implement a generic runner that makes all eight declarations executable.

Implement one narrow, read-only **`SessionStart` bootstrap hook**, register only that event, and remove the other seven event declarations from the installed plugin and the active Codex binding. The runner’s only truthful capability is to project already-observed plugin/status/health facts into a concise session-start context. It must not create or resume a FORGE session, reconstruct a `ContextCapsule`, make policy decisions, approve tools, append to the ledger, or validate subagent completion.

If the existing status/health and Codex-binding producers cannot be reused without copying their logic, the fallback is to quarantine **all** hooks. A no-op eight-event runner is not an acceptable fallback.

## 1. The correct next increment

### Selected active surface

Retain only:

```text
SessionStart
  matcher: startup|resume|clear|compact
  command: node "${PLUGIN_ROOT}/dist/hook-runner.mjs" session-start
```

Remove from the active plugin:

```text
PostCompact
UserPromptSubmit
PermissionRequest
PreToolUse
PostToolUse
SubagentStart
SubagentStop
```

An unregistered declaration pointing to a missing executable is a misleading capability signal. More importantly, creating an empty runner would satisfy the current structural `BOUND` test even though it supplies no event semantics. Therefore, `BOUND` must continue to mean only “the declared payload files resolve,” never “the host has trusted and executed a functioning hook.”

### Exact plugin changes

In:

```text
plugins/epistemic-foundry/.codex-plugin/plugin.json
```

add only:

```json
"hooks": "./hooks/session.json"
```

Codex supports a single hook path, an array of paths, or inline hook objects in the plugin manifest. Plugin hooks are skipped until the current definitions have been reviewed and trusted, so manifest registration and file existence are not themselves evidence of operational execution. ([OpenAI Developers][1])

Rewrite:

```text
plugins/epistemic-foundry/hooks/session.json
```

to contain only:

```json
{
  "description": "Bounded Epistemic Foundry bootstrap observation.",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "node \"${PLUGIN_ROOT}/dist/hook-runner.mjs\" session-start",
            "timeout": 3,
            "statusMessage": "Checking Epistemic Foundry capabilities"
          }
        ]
      }
    ]
  }
}
```

The three-second timeout is a local boundedness decision, not a host-standard value. The implementation should be Node-only, local, network-free, and non-persistent, so it should not need anything close to the present 15 seconds.

Do not add `additionalContextLimit` in this increment unless the local Codex registration parser is deliberately updated: its current exact handler-field set does not admit that field. Instead, cap the runner’s rendered output internally, for example at 1,024 UTF-8 bytes.

Update:

```text
adapters/codex/codex-binding.json
```

from four files to:

```json
"hook_files": [
  "hooks/session.json"
]
```

The binding declaration must describe the files the manifest actually activates. It must not continue calling the other three files registered when the host manifest does not load them.

Remove from the installed plugin root:

```text
plugins/epistemic-foundry/hooks/prompt.json
plugins/epistemic-foundry/hooks/tools.json
plugins/epistemic-foundry/hooks/delegation.json
```

Deleting them is preferable. If they are needed as future protocol fixtures, move them outside the installable plugin tree, such as under an already-owned:

```text
tests/compatibility/hooks/fixtures/unregistered/
```

They must not remain next to active plugin hooks or in `codex-binding.json`.

### Why `PostCompact` is unnecessary in this profile

Codex invokes `SessionStart` with `source: "compact"` after root-session compaction and before the next model request. The same bounded bootstrap hook can therefore reassert the Foundry’s capability limits after compaction without pretending to rebuild prior session state. ([ChatGPT Learn][2])

It should say, in substance:

```text
The host compacted the conversation. No Foundry ContextCapsule was
reconstructed, and no FORGE session state was restored. Current Foundry
capabilities must be obtained from the observed status/health surfaces.
```

That is useful context, but it is not a `ContextCapsule`.

## 2. Minimum truthful behavior by event

| Event               | Disposition    | Minimum truthful behavior                                                                                                                         |
| ------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SessionStart`      | **Register**   | Read-only capability observation and concise boundary context. No session creation, resume, recovery, or write.                                   |
| `PostCompact`       | **Unregister** | No capsule or cursor producer exists. `SessionStart(source=compact)` provides the bounded boundary reminder.                                      |
| `UserPromptSubmit`  | **Unregister** | No intake classifier or prompt-policy producer exists. A synchronous no-op would add latency while implying classification coverage.              |
| `PermissionRequest` | **Unregister** | Never emit unconditional `allow`. With no policy engine, approval authority does not exist.                                                       |
| `PreToolUse`        | **Unregister** | No capability/path/egress/secret policy decision is available. Exit-zero silence would let the tool continue but would falsely advertise a guard. |
| `PostToolUse`       | **Unregister** | No ledger append, receipt, artifact registration, or durable cache update.                                                                        |
| `SubagentStart`     | **Unregister** | Static role mappings do not establish an exact run-local dispatch, expected count, or authorized context binding.                                 |
| `SubagentStop`      | **Unregister** | No dispatch record, expected-count state, or result-envelope obligation is available to validate.                                                 |

### `SessionStart`

The new source-level producer should be named something like:

```text
buildSessionStartObservation(...)
renderCodexSessionStartResponse(...)
```

It should consume existing producers rather than reimplement them:

```text
loadCodexBinding(...)
codexBindingReceipt(...)
existing status/health read producer
existing capability-probe projection, when available
```

A valid host response is:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Epistemic Foundry bootstrap observation: the active hook profile is SessionStart-only. No FORGE session was created or resumed; no ContextCapsule was restored; tool-policy, permission, prompt, post-tool, and subagent hooks are unregistered. Consult the backed Foundry status and health tools for current observed capability details."
  }
}
```

The actual text must be rendered from current observations rather than hard-coded capability counts. It must not include:

```text
absolute paths
transcript contents
PLUGIN_DATA contents
raw exception strings
credentials or secrets
unbounded lists of findings
claims that a hook is trusted merely because its file exists
```

For `source: "resume"`, the hook may report that the host resumed a Codex session. It must not say that a FORGE session was resumed.

For a known absent producer, return a valid bounded response that explicitly says `UNAVAILABLE`. For malformed stdin or a verb/event mismatch, reuse the existing adapter failures such as:

```text
RAW_EVENT_UNREADABLE
HOOK_VERB_UNREGISTERED
```

Exit nonzero, write only the stable code to `stderr`, and produce no `stdout`. Do not expose raw exceptions.

### `PermissionRequest` and `PreToolUse`

“Always allow” is worse than leaving the hook unregistered.

A `PermissionRequest` `allow` decision causes the request to proceed without the normal approval prompt. With no policy engine, that would exercise authority the Foundry does not possess. Returning no decision would preserve the normal approval flow, but registering such a hook would still imply that Foundry policy had inspected the request. Therefore the truthful profile is **unregistered**, not “registered but undecided.” ([OpenAI Developers][3])

For `PreToolUse`, unsupported output fields can themselves cause a failed hook while the tool call continues. The runner must not guess that its internal `HookDecision` envelope is a valid host decision. ([OpenAI Developers][3])

Even when these hooks are eventually implemented, they remain guardrails rather than the complete security perimeter because hosted and some specialized tool paths can bypass the local tool-hook route. ([OpenAI Developers][3])

### `PostToolUse` and the Noetic Ledger

Do not append directly to the Noetic Ledger.

A hash chain establishes sequence integrity. It does not establish:

```text
canonical FORGE session identity
authorized workspace identity
action or effect identity
idempotency across hook retries
policy and capability authority
confidentiality/redaction
artifact/effect receipt issuance
failure reconciliation
```

The host provides a Codex `session_id`, `tool_use_id`, `cwd`, tool arguments, and tool response. Those are host observations, not automatically canonical Foundry identities or authorized ledger events.

A ledger append would also be a new durable effect triggered by a post-effect observation. It must pass the normal intent, authority, idempotency, and receipt boundary. Since that path does not exist here, `PostToolUse` must remain unregistered.

Codex also documents that `PostToolUse` occurs after the tool has run and cannot undo its side effects; a block is feedback or result replacement, not rollback. ([OpenAI Developers][3])

### `SubagentStart` and `SubagentStop`

A sealed role table is not enough to activate these hooks.

`SubagentStart` would need an exact run-local relationship among:

```text
host agent_id
host agent_type
canonical RoleSpec
parent dispatch
authorized scopes
expected result schema
expected result count
```

`SubagentStop` additionally needs the exact dispatch record and the result obligation it is checking. Without those, there is no truthful completion decision.

There is also a host-wire trap: `SubagentStop` requires JSON on `stdout` when the command exits zero. It is not safe to assume that a generic empty or plain-text success response has the same meaning as other hook events. ([OpenAI Developers][3])

## 3. The Codex host protocol is knowable

This is **not a SPEC_GAP**.

The current official Codex release documentation defines the relevant protocol:

1. Every command hook receives one JSON object on `stdin`.
2. Common fields include `session_id`, `transcript_path`, `cwd`, `hook_event_name`, and `model`; many of these events also carry `permission_mode`.
3. Event-specific fields and output shapes differ.
4. Exit zero with no output generally means success and continuation, but event-specific rules still apply.
5. `PreToolUse` and `PermissionRequest` do not accept the same continuation fields as lifecycle events.
6. `PermissionRequest` may allow, deny, or decline to decide.
7. `PostToolUse` cannot undo an already-completed action.
8. `SubagentStop` requires JSON on successful exit.
9. The release documentation, rather than potentially ahead-of-release `main`-branch schemas, is the behavior authority. ([OpenAI Developers][3])

The repository’s internal object and the Codex wire object must remain distinct:

```text
Codex JSON stdin
→ Codex adapter normalization
→ H01 Hook Gateway request
→ internal hashed HookDecision envelope
→ Codex event-specific response renderer
→ JSON stdout
```

Do **not** print the internal gateway envelope directly to `stdout`.

The runner should support exactly one verb in this increment:

```text
session-start
```

Any other verb must be refused, not silently treated as a no-op.

The installed Codex version still needs to be feature-probed. Plugin hook definitions also require host trust before execution. This is a runtime compatibility qualification, not an ambiguity in the published protocol. ([ChatGPT Learn][2])

## 4. Ownership of the runner

Yes: **T03 owns the generated packaged runner, while H01 owns the semantics and Codex-wire translation it packages.**

The split should be:

| Surface                                           | Owner                      | Responsibility                                                                      |
| ------------------------------------------------- | -------------------------- | ----------------------------------------------------------------------------------- |
| `packages/plugin-host/src/hooks/gateway/**`       | H01                        | Host-neutral normalization, hashing, internal decision validation, timeout behavior |
| `adapters/codex/hook-runner.mjs`                  | H01                        | Codex stdin/verb handling and event-specific response rendering                     |
| `plugins/epistemic-foundry/hooks/session.json`    | H02                        | Active lifecycle declaration and bounded SessionStart semantics                     |
| `plugins/epistemic-foundry/hooks/prompt.json`     | H02                        | Removal from installed payload                                                      |
| `plugins/epistemic-foundry/hooks/tools.json`      | H03                        | Removal from installed payload                                                      |
| `plugins/epistemic-foundry/hooks/delegation.json` | H03                        | Removal from installed payload                                                      |
| `.codex-plugin/plugin.json`                       | G01/current manifest owner | Exact registration of `./hooks/session.json`                                        |
| `plugins/epistemic-foundry/dist/hook-runner.mjs`  | T03                        | Reproducibly generated and sealed installed artifact                                |

### Source ownership gap

There is presently no stated owner for the source entrypoint that binds the existing Codex adapter to stdin/stdout execution. That is a:

> **SPEC_GAP — source-entrypoint ownership gap**

The smallest amendment is one exact H01 line:

```yaml
- id: H01
  write_scope:
  - packages/plugin-host/src/hooks/gateway/**
  - adapters/codex/hook-runner.mjs
```

The new file should import the existing Codex adapter functions rather than implement a parallel path:

```text
loadCodexBinding
toHookRequest
dispatchRawCodexEvent
verifyBridgedEnvelope
```

If `adapters/codex/codex-binding.json` has no existing declared owner, add one further exact H01 line:

```yaml
  - adapters/codex/codex-binding.json
```

Do not broaden this to:

```yaml
- adapters/codex/**
```

unless changes to the existing adapter modules are actually required.

T03 must not hand-author hook policy in `dist/`. It should bundle the exact H01 source closure into:

```text
plugins/epistemic-foundry/dist/hook-runner.mjs
```

and record the source/provenance hash, following the same non-duplication discipline used for the workspace-map bundle.

### Structural `BOUND` is not operational capability

The current adversarial fixture demonstrates that creating an otherwise empty runner file changes the binding to `BOUND`. Therefore:

```text
BOUND
≠ registered
≠ trusted
≠ host-supported
≠ executed
≠ policy-enforcing
```

The existing H04 health/degraded-mode surface should distinguish those facts without redefining `BOUND`. If the canonical health contract cannot represent configured-but-untrusted or configured-but-unobserved hooks, changing that shared schema is a separate:

> **SPEC_GAP — HostCapabilityReport/health contract gap**

Do not invent new canonical status literals inside the runner to avoid that gap.

## 5. A FORGE session store is not the better next target

The earlier “not next” decision still holds.

A `forge-session-state` store by itself would not make these hooks meaningful. A lawful session capability would also require:

```text
session creation authority
workspace and actor binding
initial values for all required fields
revision/CAS behavior
transition reducer
idempotency
recovery and replay
read-model projection
artifact-obligation handling
failure semantics
```

It would still not provide:

```text
ContextCapsule assembly
tool-policy decisions
permission authority
post-tool effect receipts
subagent expected-count state
subagent result-envelope validation
```

Building a store merely so that `SessionStart` can say it touched a session would be the wrong dependency direction. The selected observational hook gains its value precisely by reporting that session state is unavailable rather than manufacturing it.

The remaining ten MCP tools should therefore remain explicitly unavailable until their real domain stores and producers exist. This hook increment makes no change to the frozen thirteen-tool catalog.

## Approved minimum increment

1. Register only `./hooks/session.json`.

2. Retain only `SessionStart` with matcher `startup|resume|clear|compact`.

3. Implement one H01-owned source entrypoint:

   ```text
   adapters/codex/hook-runner.mjs
   ```

4. Generate the T03-owned artifact:

   ```text
   plugins/epistemic-foundry/dist/hook-runner.mjs
   ```

5. Reuse the existing Codex adapter and read-only status/health producers.

6. Emit only bounded `SessionStart` additional context.

7. Perform no writes, policy decisions, approvals, session restoration, capsule reconstruction, ledger append, or subagent adjudication.

8. Remove `prompt.json`, `tools.json`, and `delegation.json` from the installed plugin and active binding.

9. Keep structural binding status separate from host trust and observed execution.

10. Leave the FORGE session store for its own complete state-contract increment.

No shared canonical schema change or thirteen-tool catalog change is required for this selected profile. No execution or test result is claimed here.

[1]: https://developers.openai.com/plugins/build/plugins "https://developers.openai.com/plugins/build/plugins"
[2]: https://learn.chatgpt.com/docs/hooks "https://learn.chatgpt.com/docs/hooks"
[3]: https://developers.openai.com/codex/hooks "https://developers.openai.com/codex/hooks"
