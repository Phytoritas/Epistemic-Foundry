import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { routeSkillRequest } from "../../packages/plugin-host/src/skill-router/skill-router.mjs";
import {
  buildInitialMetadataProjection,
  errorCodeOf,
  loadSkillInventory,
  resolveSkillContext,
  selectReferences,
  verifyInventoryFiles,
} from "../../packages/plugin-host/src/skill-context/index.ts";


const repositoryRoot = path.resolve(import.meta.dirname, "../..");
const pluginRoot = path.join(repositoryRoot, "plugins", "epistemic-foundry");
const inventory = await loadSkillInventory(pluginRoot);
const POLICY_HASH = `sha256:${"d".repeat(64)}`;
const DECIDED_AT = "2026-07-29T12:30:00.000Z";


const decisionFor = (skillId, caseId = skillId) => {
  const skill = inventory.skills.find((entry) => entry.skill_id === skillId);
  return routeSkillRequest({
    request_id: `REQ-J02-LOADER-${caseId}`,
    request_text: `Explicit loader fixture route for ${skillId}.`,
    explicit_skill_id: skillId,
    candidates: [
      {
        skill_id: skillId,
        description: skill.description,
        content_hash: skill.sha256,
        source: "bundled",
        allow_implicit_invocation: skill.allow_implicit_invocation,
        sensitive: false,
        side_effecting: false,
        trigger_phrases: [],
        exclusion_phrases: [],
      },
    ],
    context_budget_tokens: 7168,
    policy_hash: POLICY_HASH,
    decided_at: DECIDED_AT,
  });
};

const expectSyncCode = (expected, operation) => {
  assert.throws(operation, (error) => {
    assert.equal(errorCodeOf(error), expected);
    return true;
  });
};


test("loader verifies all sealed production files and authority pointers", async () => {
  const result = await verifyInventoryFiles(inventory, pluginRoot, repositoryRoot);
  assert.deepEqual(result, {
    skill_files_verified: 29,
    reference_files_verified: 17,
    authority_sources_verified: 51,
    agent_projections_verified: 29,
  });
});

test("metadata projection uses exact limits and explicit-parent-only degradation", () => {
  const normal = buildInitialMetadataProjection(inventory);
  assert.equal(normal.degraded_mode, "NONE");
  assert.equal(normal.byte_count, 4767);
  assert.equal(normal.token_count, 1112);
  assert.equal(normal.skill_count, 29);
  assert.equal(Buffer.byteLength(normal.text, "utf8"), normal.byte_count);

  expectSyncCode("HOST_SKILL_METADATA_BUDGET_INSUFFICIENT", () =>
    buildInitialMetadataProjection(
      inventory,
      { byte_budget: 4766, token_budget: 1112, parent_explicitly_reachable: true },
      false,
    ),
  );
  const degraded = buildInitialMetadataProjection(
    inventory,
    { byte_budget: 1, token_budget: 1, parent_explicitly_reachable: true },
    true,
  );
  assert.equal(degraded.degraded_mode, "EXPLICIT_PARENT_ONLY");
  assert.equal(degraded.text, "");
  assert.deepEqual(degraded.warnings, ["HOST_SKILL_METADATA_BUDGET_INSUFFICIENT"]);
});

test("known LLM proposal remains non-authoritative and cannot add a reference", () => {
  const decision = decisionFor("foundry", "LLM-NON-AUTHORITY");
  const selection = selectReferences({
    inventory,
    routingDecision: decision,
    llmProposals: [
      {
        reference_id: "EFREF-PLUGIN-SECURITY-ADMIN-V4",
        reason: "model suggests an unrelated reference",
      },
    ],
  });
  assert.deepEqual(selection.ordered_reference_ids, [
    "EFREF-CORE-CONSTITUTION-V4",
    "EFREF-ROUTER-E0-E5-V4",
  ]);
  assert.deepEqual(selection.warnings, [
    "LLM_PROPOSAL_NOT_AUTHORIZED:EFREF-PLUGIN-SECURITY-ADMIN-V4",
  ]);
});

test("typed trigger comparison is semantic rather than object-key-order dependent", () => {
  const decision = decisionFor("foundry-passport", "TYPED-TRIGGER-ORDER");
  const typedTrigger = Object.create(null);
  typedTrigger.value = ["ValidationResult", "ReplicationResult"];
  typedTrigger.operator = "ANY_OF";
  typedTrigger.key = "artifact_kind";

  // Null-prototype objects are intentionally rejected at the input boundary.
  expectSyncCode("INVALID_SKILL_CONTEXT_INPUT", () =>
    selectReferences({
      inventory,
      routingDecision: decision,
      conditions: { artifact_kind: ["ValidationResult"] },
      llmProposals: [
        {
          reference_id: "EFREF-VALIDATION-REPLICATION-V4",
          reason: "same typed predicate with a non-data object",
          typed_trigger_candidate: typedTrigger,
        },
      ],
    }),
  );

  const reorderedPlain = {};
  reorderedPlain.value = ["ValidationResult", "ReplicationResult"];
  reorderedPlain.operator = "ANY_OF";
  reorderedPlain.key = "artifact_kind";
  const selection = selectReferences({
    inventory,
    routingDecision: decision,
    conditions: { artifact_kind: ["ValidationResult"] },
    llmProposals: [
      {
        reference_id: "EFREF-VALIDATION-REPLICATION-V4",
        reason: "same declared typed predicate in another key order",
        typed_trigger_candidate: reorderedPlain,
      },
    ],
  });
  assert.ok(selection.ordered_reference_ids.includes("EFREF-VALIDATION-REPLICATION-V4"));
  assert.deepEqual(selection.warnings, []);
});

test("plain-data input boundary rejects proxies, accessors, sparse arrays, and unknown keys", () => {
  const decision = decisionFor("foundry", "INPUT-BOUNDARY");
  expectSyncCode("INVALID_SKILL_CONTEXT_INPUT", () =>
    selectReferences({
      inventory,
      routingDecision: decision,
      conditions: new Proxy({}, {}),
    }),
  );
  const accessor = {};
  Object.defineProperty(accessor, "backend_id", {
    enumerable: true,
    get: () => "shinka",
  });
  expectSyncCode("INVALID_SKILL_CONTEXT_INPUT", () =>
    selectReferences({ inventory, routingDecision: decision, conditions: accessor }),
  );
  const sparse = new Array(1);
  expectSyncCode("INVALID_ROUTING_DECISION", () =>
    selectReferences({
      inventory,
      routingDecision: { ...decision, selected_skill_ids: sparse },
    }),
  );
  expectSyncCode("INVALID_SKILL_CONTEXT_INPUT", () =>
    selectReferences({
      inventory,
      routingDecision: decision,
      conditions: { noncanonical: "value" },
    }),
  );
});

test("ResolvedSkillContext is identical across 100 repeated sealed loads", async () => {
  const routingDecision = decisionFor("foundry-passport", "DETERMINISM-100");
  const options = {
    plugin_root: pluginRoot,
    repository_root: repositoryRoot,
    routing_decision: routingDecision,
    conditions: { artifact_kind: ["ValidationResult"] },
    explicit_reference_ids: [],
    explicit_reference_authority_ids: [],
  };
  const first = await resolveSkillContext(options);
  assert.equal(first.selected_skill_id, "foundry-passport");
  assert.equal(first.errors.length, 0);
  assert.equal(first.ordered_reference_ids.length, 7);
  assert.equal(first.total_reference_bytes, 4865);
  assert.equal(first.total_reference_tokens, 962);
  assert.ok(Object.isFrozen(first));

  for (let iteration = 1; iteration < 100; iteration += 1) {
    const repeated = await resolveSkillContext(options);
    assert.equal(repeated.context_hash, first.context_hash);
    assert.deepEqual(repeated.ordered_reference_ids, first.ordered_reference_ids);
    assert.deepEqual(repeated.reference_selection_reasons, first.reference_selection_reasons);
    assert.equal(repeated.total_reference_bytes, first.total_reference_bytes);
    assert.equal(repeated.total_reference_tokens, first.total_reference_tokens);
    assert.equal(repeated.total_activation_bytes, first.total_activation_bytes);
    assert.equal(repeated.total_activation_tokens, first.total_activation_tokens);
  }
});

