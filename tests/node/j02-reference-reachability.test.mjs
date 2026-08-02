import assert from "node:assert/strict";
import { cp, mkdtemp, mkdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { routeSkillRequest } from "../../packages/plugin-host/src/skill-router/skill-router.mjs";
import {
  analyzeReachability,
  assertReachability,
  canonicalizeJson,
  errorCodeOf,
  loadSkillInventory,
  selectReferences,
  sha256Text,
  validateSkillInventory,
  verifyInventoryFiles,
} from "../../packages/plugin-host/src/skill-context/index.ts";


const repositoryRoot = path.resolve(import.meta.dirname, "../..");
const pluginRoot = path.join(repositoryRoot, "plugins", "epistemic-foundry");
const fixtureRoot = path.join(repositoryRoot, "tests", "fixtures", "j02");
const inventory = await loadSkillInventory(pluginRoot);
const expectedInventory = JSON.parse(
  await readFile(path.join(fixtureRoot, "skill-inventory.expected.json"), "utf8"),
);
const selectionFixture = JSON.parse(
  await readFile(path.join(fixtureRoot, "reference-selection-cases.json"), "utf8"),
);
const reachabilityFixture = JSON.parse(
  await readFile(path.join(fixtureRoot, "reference-reachability-cases.json"), "utf8"),
);
const POLICY_HASH = `sha256:${"a".repeat(64)}`;
const DECIDED_AT = "2026-07-29T12:00:00.000Z";


const clone = (value) => structuredClone(value);

const decisionFor = (skillId, caseId = skillId) => {
  const skill = inventory.skills.find((entry) => entry.skill_id === skillId);
  const candidate = skill ?? {
    skill_id: skillId,
    description: "Unknown skill target used by an adversarial J02 fixture.",
    sha256: `sha256:${"b".repeat(64)}`,
    allow_implicit_invocation: false,
  };
  return routeSkillRequest({
    request_id: `REQ-J02-${caseId}`,
    request_text: `Explicit J02 fixture route for ${skillId}.`,
    explicit_skill_id: skillId,
    candidates: [
      {
        skill_id: skillId,
        description: candidate.description,
        content_hash: candidate.sha256,
        source: "bundled",
        allow_implicit_invocation: candidate.allow_implicit_invocation,
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

const authorityFor = (skillId, caseId = skillId) => {
  const skill = inventory.skills.find((entry) => entry.skill_id === skillId);
  return skill?.invocation_disposition === "PARENT_ROUTED"
    ? {
        kind: "PARENT_PLAN",
        skill_id: skillId,
        exact_authorized: true,
        authority_id: `PLAN-J02-${caseId}`,
      }
    : undefined;
};

const selectionFor = (skillInventory, skillId, caseId, conditions = {}, extra = {}) =>
  selectReferences({
    inventory: skillInventory,
    routingDecision: decisionFor(skillId, caseId),
    conditions,
    invocationAuthority: authorityFor(skillId, caseId),
    ...extra,
  });

const expectSyncCode = (expected, operation) => {
  assert.throws(operation, (error) => {
    assert.equal(errorCodeOf(error), expected);
    return true;
  });
};

const expectAsyncCode = async (expected, operation) => {
  await assert.rejects(operation, (error) => {
    assert.equal(errorCodeOf(error), expected);
    return true;
  });
};


test("J02 graph reaches exactly 1 parent, 28 children, and 17 references", () => {
  const observed = analyzeReachability(inventory);
  assert.deepEqual(observed, reachabilityFixture.expected_graph);
  assert.deepEqual(assertReachability(inventory), reachabilityFixture.expected_graph);
  assert.equal(inventory.inventory_id, expectedInventory.inventory_id);
  assert.equal(inventory.inventory_hash, expectedInventory.inventory_hash);
  assert.deepEqual(
    inventory.skills.map((entry) => [entry.skill_id, entry.invocation_disposition]),
    Object.entries(expectedInventory.skill_dispositions),
  );
  assert.deepEqual(
    inventory.references.map((entry) => entry.reference_id).sort(),
    [...expectedInventory.reference_ids].sort(),
  );
});

test("all 35 fixed selection cases match sealed IDs, order, reasons, and totals", () => {
  assert.equal(selectionFixture.case_count, 35);
  assert.equal(selectionFixture.inventory_hash, inventory.inventory_hash);
  assert.deepEqual(
    selectionFixture.cases.reduce((counts, current) => {
      counts[current.category] = (counts[current.category] ?? 0) + 1;
      return counts;
    }, {}),
    { DEFAULT: 29, CONDITIONAL_POSITIVE: 3, CONDITIONAL_NEGATIVE: 3 },
  );
  const references = new Map(inventory.references.map((entry) => [entry.reference_id, entry]));
  for (const fixtureCase of selectionFixture.cases) {
    const selection = selectionFor(
      inventory,
      fixtureCase.skill_id,
      fixtureCase.case_id,
      fixtureCase.conditions,
    );
    const preimage = {
      ordered_reference_ids: selection.ordered_reference_ids,
      reference_selection_reasons: selection.reference_selection_reasons,
      transitive_depth: selection.transitive_depth,
      total_reference_bytes: selection.ordered_reference_ids.reduce(
        (total, referenceId) => total + references.get(referenceId).byte_count,
        0,
      ),
      total_reference_tokens: selection.ordered_reference_ids.reduce(
        (total, referenceId) => total + references.get(referenceId).token_count,
        0,
      ),
      warnings: selection.warnings,
    };
    assert.equal(sha256Text(canonicalizeJson(preimage)), fixtureCase.selection_hash);
    assert.equal(preimage.transitive_depth, fixtureCase.transitive_depth);
    assert.equal(preimage.total_reference_bytes, fixtureCase.total_reference_bytes);
    assert.equal(preimage.total_reference_tokens, fixtureCase.total_reference_tokens);
    assert.equal(new Set(preimage.ordered_reference_ids).size, preimage.ordered_reference_ids.length);
  }
});

test("all 16 adversarial reachability cases fail closed with their exact code", async (t) => {
  assert.equal(reachabilityFixture.adversarial_case_count, 16);
  assert.equal(reachabilityFixture.adversarial_cases.length, 16);

  for (const fixtureCase of reachabilityFixture.adversarial_cases) {
    await t.test(fixtureCase.case_id, async () => {
      switch (fixtureCase.operation) {
        case "missing_skill_target":
          expectSyncCode(fixtureCase.expected_error, () =>
            selectionFor(inventory, "foundry-missing", fixtureCase.case_id),
          );
          break;
        case "missing_reference_target": {
          const candidate = clone(inventory);
          candidate.skills.find((entry) => entry.skill_id === "foundry").direct_references.push(
            "EFREF-MISSING-V4",
          );
          expectSyncCode(fixtureCase.expected_error, () =>
            selectionFor(candidate, "foundry", fixtureCase.case_id),
          );
          break;
        }
        case "orphan_reference": {
          const candidate = clone(inventory);
          candidate.references.push({
            ...clone(candidate.references[0]),
            reference_id: "EFREF-ORPHAN-V4",
            path: "skills/foundry/references/orphan.md",
            sha256: `sha256:${"c".repeat(64)}`,
          });
          expectSyncCode(fixtureCase.expected_error, () => assertReachability(candidate));
          break;
        }
        case "self_cycle": {
          const candidate = clone(inventory);
          const router = candidate.references.find(
            (entry) => entry.reference_id === "EFREF-ROUTER-E0-E5-V4",
          );
          router.depends_on = [router.reference_id];
          expectSyncCode(fixtureCase.expected_error, () =>
            selectionFor(candidate, "foundry", fixtureCase.case_id),
          );
          break;
        }
        case "multi_node_cycle": {
          const candidate = clone(inventory);
          const constitution = candidate.references.find(
            (entry) => entry.reference_id === "EFREF-CORE-CONSTITUTION-V4",
          );
          const router = candidate.references.find(
            (entry) => entry.reference_id === "EFREF-ROUTER-E0-E5-V4",
          );
          constitution.depends_on = [router.reference_id];
          router.depends_on = [constitution.reference_id];
          expectSyncCode(fixtureCase.expected_error, () =>
            selectionFor(candidate, "foundry", fixtureCase.case_id),
          );
          break;
        }
        case "depth_overflow": {
          const candidate = clone(inventory);
          const chain = candidate.references.slice(0, 7);
          chain[0].depends_on = [];
          for (let index = 1; index < chain.length; index += 1) {
            chain[index].depends_on = [chain[index - 1].reference_id];
          }
          candidate.skills.find((entry) => entry.skill_id === "foundry").direct_references = [
            chain.at(-1).reference_id,
          ];
          expectSyncCode(fixtureCase.expected_error, () =>
            selectionFor(candidate, "foundry", fixtureCase.case_id),
          );
          break;
        }
        case "duplicate_skill_id": {
          const candidate = clone(inventory);
          candidate.skills[1].skill_id = candidate.skills[0].skill_id;
          expectSyncCode(fixtureCase.expected_error, () => validateSkillInventory(candidate));
          break;
        }
        case "duplicate_reference_id": {
          const candidate = clone(inventory);
          candidate.references[1].reference_id = candidate.references[0].reference_id;
          expectSyncCode(fixtureCase.expected_error, () => validateSkillInventory(candidate));
          break;
        }
        case "duplicate_path": {
          const candidate = clone(inventory);
          candidate.references[1].path = candidate.references[0].path;
          expectSyncCode(fixtureCase.expected_error, () => validateSkillInventory(candidate));
          break;
        }
        case "content_hash_mismatch": {
          const temp = await mkdtemp(path.join(os.tmpdir(), "ef-j02-drift-"));
          const copiedPlugin = path.join(temp, "epistemic-foundry");
          try {
            await cp(pluginRoot, copiedPlugin, { recursive: true });
            const target = path.join(
              copiedPlugin,
              ...inventory.references[0].path.split("/"),
            );
            await writeFile(target, "content drift\n", "utf8");
            await expectAsyncCode(fixtureCase.expected_error, () =>
              verifyInventoryFiles(inventory, copiedPlugin, repositoryRoot),
            );
          } finally {
            await rm(temp, { recursive: true, force: true });
          }
          break;
        }
        case "path_variants":
          for (const maliciousPath of fixtureCase.paths) {
            const candidate = clone(inventory);
            candidate.references[0].path = maliciousPath;
            expectSyncCode(fixtureCase.expected_error, () => validateSkillInventory(candidate));
          }
          break;
        case "symlink_escape": {
          const temp = await mkdtemp(path.join(os.tmpdir(), "ef-j02-link-"));
          const copiedPlugin = path.join(temp, "epistemic-foundry");
          const outside = path.join(temp, "outside-backends");
          try {
            await cp(pluginRoot, copiedPlugin, { recursive: true });
            await mkdir(outside);
            const backendDirectory = path.join(
              copiedPlugin,
              "skills",
              "foundry",
              "references",
              "backends",
            );
            const source = path.join(backendDirectory, "shinka.md");
            const bytes = await readFile(source);
            await writeFile(path.join(outside, "shinka.md"), bytes);
            await rm(backendDirectory, { recursive: true });
            await symlink(outside, backendDirectory, "junction");
            await expectAsyncCode(fixtureCase.expected_error, () =>
              verifyInventoryFiles(inventory, copiedPlugin, repositoryRoot),
            );
          } finally {
            await rm(temp, { recursive: true, force: true });
          }
          break;
        }
        case "disabled_explicit_reference": {
          const candidate = clone(inventory);
          const reference = candidate.references.find(
            (entry) => entry.reference_id === "EFREF-BACKEND-SHINKA-V4",
          );
          reference.mode = "DISABLED";
          reference.status = "DISABLED";
          expectSyncCode(fixtureCase.expected_error, () =>
            selectionFor(candidate, "foundry", fixtureCase.case_id, {}, {
              explicitReferenceIds: [reference.reference_id],
              explicitReferenceAuthorityIds: [reference.reference_id],
            }),
          );
          break;
        }
        case "unknown_llm_proposal":
          expectSyncCode(fixtureCase.expected_error, () =>
            selectionFor(inventory, "foundry", fixtureCase.case_id, {}, {
              llmProposals: [
                { reference_id: "EFREF-UNKNOWN-V4", reason: "untrusted model proposal" },
              ],
            }),
          );
          break;
        default:
          assert.fail(`unknown adversarial operation: ${fixtureCase.operation}`);
      }
    });
  }
});

