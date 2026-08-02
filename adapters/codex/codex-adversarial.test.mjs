// codex_hook_coverage_test / negative and adversarial tests — one broken input
// at a time.
//
// Each case stages the declaring inputs into a temporary root and damages
// exactly one of them, so the refusal that follows can only be caused by that
// damage.  The real payload is never written to.  The positive control at the
// end builds the two runtime files the payload lacks and shows the binding turn
// BOUND, so DEGRADED is a derived status rather than a constant.

import assert from "node:assert/strict";
import test from "node:test";

import {
  HOOK_HOSTS,
  HookGatewayError,
} from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  BINDING_DECLARATION_PATH,
  BINDING_STATUS,
  CodexAdapterError,
  dispatchRawCodexEvent,
  loadCodexBinding,
  PAYLOAD_ROOT,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_PATH,
  toHookRequest,
  verifyBridgedEnvelope,
} from "./index.mjs";
import {
  addStaged,
  asyncRefusal,
  rawEventFor,
  refusal,
  removeStaged,
  RUNTIME_TEMPLATE,
  stageDeclaration,
  stageHookFile,
  stageManifest,
  stageRoot,
  stageText,
  writeStaged,
} from "./codex-fixtures.mjs";

const binding = loadCodexBinding();
const loadFrom = (root) => refusal(() => loadCodexBinding({ root }));

test("x01_adversarial: an event type the gateway does not declare is refused", (t) => {
  const root = stageHookFile(t, "hooks/prompt.json", (document) => {
    document.hooks.UserPromptSubmitted = document.hooks.UserPromptSubmit;
    delete document.hooks.UserPromptSubmit;
  });

  const error = loadFrom(root);
  assert.equal(error.code, "HOOK_EVENT_UNDECLARED");
  assert.equal(error.context.candidate, "UserPromptSubmitted");
});

test("x01_adversarial: a host the gateway does not declare is refused", (t) => {
  const root = stageDeclaration(t, (declaration) => {
    declaration.declared_host = `${declaration.declared_host}-cli`;
  });

  const error = loadFrom(root);
  assert.equal(error.code, "HOOK_HOST_UNDECLARED");
  assert.deepEqual(error.context.declared, [...HOOK_HOSTS]);
});

test("x01_adversarial: a coverage class the gateway does not declare is refused", (t) => {
  const root = stageDeclaration(t, (declaration) => {
    declaration.coverage_restricted = "SOMETIMES";
  });

  assert.equal(loadFrom(root).code, "COVERAGE_UNDECLARED");
});

test("x01_adversarial: a declared hook file the payload does not ship is refused", (t) => {
  const root = stageRoot(t);
  removeStaged(root, `${PAYLOAD_ROOT}/hooks/prompt.json`);

  const error = loadFrom(root);
  assert.equal(error.code, "HOOK_FILE_MISSING");
  assert.equal(error.context.path, "hooks/prompt.json");
});

test("x01_adversarial: an unsorted declaration is refused before it can be hashed", (t) => {
  const root = stageDeclaration(t, (declaration) => {
    declaration.hook_files = [...declaration.hook_files].reverse();
  });

  assert.equal(loadFrom(root).code, "DECLARATION_NONCANONICAL");
});

test("x01_adversarial: a dispatcher that is not a declared entrypoint is refused", (t) => {
  const root = stageDeclaration(t, (declaration) => {
    declaration.dispatcher = "bin/other.mjs";
  });

  assert.equal(loadFrom(root).code, "DECLARATION_NONCANONICAL");
});

test("x01_adversarial: a manifest that is not JSON is refused", (t) => {
  const root = stageRoot(t);
  writeStaged(root, `${PAYLOAD_ROOT}/.codex-plugin/plugin.json`, "{ not json");

  assert.equal(loadFrom(root).code, "MANIFEST_UNREADABLE");
});

test("x01_adversarial: a manifest naming another package is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.name = "other-foundry";
  });

  const error = loadFrom(root);
  assert.equal(error.code, "PLUGIN_NAME_DRIFT");
  assert.equal(error.context.manifest, "other-foundry");
});

test("x01_adversarial: a manifest asset the payload does not ship is refused", (t) => {
  const root = stageManifest(t, (manifest) => {
    manifest.interface.logo = "./assets/absent.svg";
  });

  const error = loadFrom(root);
  assert.equal(error.code, "ENTRYPOINT_MISSING");
  assert.equal(error.context.field, "logo");
});

test("x01_adversarial: a declared entrypoint the payload does not ship is refused", (t) => {
  const root = stageRoot(t);
  removeStaged(root, `${PAYLOAD_ROOT}/bin/efoundry.mjs`);

  const error = loadFrom(root);
  assert.equal(error.code, "ENTRYPOINT_MISSING");
  assert.equal(error.context.path, "bin/efoundry.mjs");
});

test("x01_adversarial: a hook command the adapter cannot resolve is refused", (t) => {
  const root = stageHookFile(t, "hooks/prompt.json", (document) => {
    document.hooks.UserPromptSubmit[0].hooks[0].command = "bash -c 'run the hook'";
  });

  assert.equal(loadFrom(root).code, "HOOK_COMMAND_UNPARSEABLE");
});

test("x01_adversarial: a registration carrying an unsupported field is refused", (t) => {
  const root = stageHookFile(t, "hooks/tools.json", (document) => {
    document.hooks.PreToolUse[0].priority = 1;
  });

  const error = loadFrom(root);
  assert.equal(error.code, "HOOK_REGISTRATION_UNREADABLE");
  assert.deepEqual(error.context.fields, ["priority"]);
});

test("x01_adversarial: two event types sharing one verb are refused", (t) => {
  const root = stageHookFile(t, "hooks/prompt.json", (document) => {
    document.hooks.UserPromptSubmit[0].hooks[0].command =
      'node "${PLUGIN_ROOT}/dist/hook-runner.mjs" post-tool-use';
  });

  const error = loadFrom(root);
  assert.equal(error.code, "HOOK_VERB_AMBIGUOUS");
  assert.equal(error.context.verb, "post-tool-use");
});

test("x01_adversarial: a dispatcher naming no payload target is refused", (t) => {
  const root = stageRoot(t);
  writeStaged(root, `${PAYLOAD_ROOT}/bin/efoundry.mjs`, "#!/usr/bin/env node\nprocess.exit(0);\n");

  assert.equal(loadFrom(root).code, "DISPATCHER_UNREADABLE");
});

test("x01_adversarial: a mapping row for an undeclared role is refused", (t) => {
  const root = stageText(t, ROLE_MAPPING_PATH, (text) =>
    text.replace(
      "constraints:",
      [
        "  shadow_promoter:",
        "    agent_type: explorer",
        "    prompt_source: manifests/role_registry.yaml#shadow_promoter",
        "    result_schema: schemas/result-envelope.schema.json",
        "constraints:",
      ].join("\n"),
    ),
  );

  const error = loadFrom(root);
  assert.equal(error.code, "ROLE_UNDECLARED");
  assert.equal(error.context.role_id, "shadow_promoter");
});

test("x01_adversarial: a declared role the mapping does not carry is refused", (t) => {
  const root = stageText(t, ROLE_MAPPING_PATH, (text) =>
    text.replace(/ {2}judge:\n(?: {4}.+\n)+/u, ""),
  );

  const error = loadFrom(root);
  assert.equal(error.code, "ROLE_UNMAPPED");
  assert.equal(error.context.role_id, "judge");
});

test("x01_adversarial: a mapping that disagrees with the registry is refused", (t) => {
  const root = stageText(t, ROLE_MAPPING_PATH, (text) =>
    text.replace(/( {2}claim_extractor:\n {4}agent_type: )worker/u, "$1explorer"),
  );

  const error = loadFrom(root);
  assert.equal(error.code, "MAPPING_DRIFT");
  assert.equal(error.context.role_id, "claim_extractor");
  assert.deepEqual(
    error.context.fields.map((row) => row.field),
    ["agent_type"],
  );
});

test("x01_adversarial: two roles resolving to one descriptor name are refused", (t) => {
  const root = stageText(t, ROLE_REGISTRY_PATH, (text) => {
    const block = /- role_id: evidence_scout\n[\s\S]*?(?=- role_id: claim_extractor)/u.exec(text)[0];
    return text.replace(block, `${block}${block}`);
  });

  const error = loadFrom(root);
  assert.equal(error.code, "DESCRIPTOR_NAME_COLLISION");
  assert.deepEqual(error.context.role_ids, ["evidence_scout", "evidence_scout"]);
});

test("x01_adversarial: an unreadable registry line is refused, not skipped", (t) => {
  const root = stageText(t, ROLE_REGISTRY_PATH, (text) =>
    text.replace("roles:\n", "extra_block:\nroles:\n"),
  );

  const error = loadFrom(root);
  assert.equal(error.code, "REGISTRY_UNREADABLE");
  assert.ok(error instanceof CodexAdapterError);
});

test("x01_adversarial: a registry role missing a RoleSpec field is refused", (t) => {
  const root = stageText(t, ROLE_REGISTRY_PATH, (text) =>
    text.replace("  claude_agent_name: ef-judge\n", ""),
  );

  assert.equal(loadFrom(root).code, "REGISTRY_UNREADABLE");
});

test("x01_adversarial: a raw event from another host is not translated", () => {
  const foreign = HOOK_HOSTS.find((entry) => entry !== binding.adapterHost);
  const error = refusal(() => toHookRequest(binding, rawEventFor(binding, { host: foreign })));

  assert.equal(error.code, "RAW_EVENT_HOST_FOREIGN");
  assert.equal(error.context.raw_host, foreign);
  assert.equal(error.context.adapter_host, binding.adapterHost);
});

test("x01_adversarial: a raw event whose verb no registration passes is refused", () => {
  const error = refusal(() => toHookRequest(binding, rawEventFor(binding, { hook: "session-end" })));

  assert.equal(error.code, "HOOK_VERB_UNREGISTERED");
  assert.equal(error.context.verb, "session-end");
});

test("x01_adversarial: a raw event that is not the exact minimal record is refused", () => {
  const complete = rawEventFor(binding);
  const { tool_name: _dropped, ...missing } = complete;

  assert.equal(refusal(() => toHookRequest(binding, missing)).code, "RAW_EVENT_UNREADABLE");
  assert.equal(
    refusal(() => toHookRequest(binding, { ...complete, decision: "ALLOW" })).code,
    "RAW_EVENT_UNREADABLE",
  );
  assert.equal(refusal(() => toHookRequest(binding, null)).code, "RAW_EVENT_UNREADABLE");
});

test("x01_adversarial: a gateway refusal is not repaired by the bridge", async () => {
  const error = await asyncRefusal(() =>
    dispatchRawCodexEvent(binding, rawEventFor(binding, { received_at: "yesterday" }), RUNTIME_TEMPLATE),
  );

  assert.ok(error instanceof HookGatewayError);
  assert.equal(error.code, "INVALID_INPUT");
});

test("x01_adversarial: a tampered envelope is refused by the gateway validator", async () => {
  const envelope = await dispatchRawCodexEvent(binding, rawEventFor(binding), RUNTIME_TEMPLATE);
  const tampered = { ...envelope, decision: "ALLOW", reasons: [...envelope.reasons] };

  const error = refusal(() => verifyBridgedEnvelope(tampered));
  assert.ok(error instanceof HookGatewayError);
  assert.equal(error.code, "HOOK_ENVELOPE_HASH_MISMATCH");
});

test("x01_adversarial: a callback failure never becomes an allow", async () => {
  const envelope = await dispatchRawCodexEvent(binding, rawEventFor(binding), {
    decide: () => {
      throw new Error("decision layer unavailable");
    },
    timeout_ms: 5000,
  });

  assert.equal(envelope.decision, "ERROR");
  assert.deepEqual(envelope.reasons, ["HOOK_DECISION_CALLBACK_ERROR"]);
});

test("x01_adversarial: building the missing runtime files turns the binding BOUND", (t) => {
  const root = stageRoot(t);
  addStaged(root, `${PAYLOAD_ROOT}/dist/cli.mjs`, "export default null;\n");
  addStaged(root, `${PAYLOAD_ROOT}/dist/hook-runner.mjs`, "export default null;\n");

  const built = loadCodexBinding({ root });

  assert.equal(built.status, BINDING_STATUS.BOUND);
  assert.deepEqual(built.findings, []);
  assert.deepEqual(built.registeredEventTypes, [...binding.registeredEventTypes]);
});

test("x01_adversarial: a declaration the adapter cannot read refuses rather than defaults", (t) => {
  const root = stageRoot(t);
  removeStaged(root, BINDING_DECLARATION_PATH);

  assert.equal(loadFrom(root).code, "DECLARATION_NONCANONICAL");
});
