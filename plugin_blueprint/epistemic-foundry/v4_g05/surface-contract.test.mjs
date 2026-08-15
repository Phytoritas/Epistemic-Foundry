// unit_and_contract_tests — what the surface does when the plugin is intact.
//
// The happy paths are the ones a real request takes: name an evolution skill,
// get the minimum disclosure its context justifies, and be told which commands
// exist and which are only proposed.  Progressive disclosure is the point, so
// a conditional reference must appear exactly when its predicate holds and not
// otherwise.

import assert from "node:assert/strict";
import test from "node:test";

import {
  assertWithinBudget,
  loadSurface,
  MAXIMAL_DISCLOSURE_CONTEXT,
  resolveDisclosure,
  routeEvolutionRequest,
  surfaceReceipt,
} from "./index.mjs";
import { ROUTE_TEMPLATE } from "./surface-fixtures.mjs";

const loaded = loadSurface();
const route = (overrides) => routeEvolutionRequest(loaded, { ...ROUTE_TEMPLATE, ...overrides });

test("g05_route: a named evolution skill is routed explicitly", () => {
  const routed = route({ explicitSkillId: "foundry-evolve-run" });

  assert.equal(routed.decision.mode, "explicit");
  assert.equal(routed.selected_skill_id, "foundry-evolve-run");
  assert.deepEqual(routed.decision.selected_skill_ids, ["foundry-evolve-run"]);
});

test("g05_route: every skill in the surface can be named", () => {
  for (const skill of loaded.surface.skills) {
    const routed = route({ explicitSkillId: skill.skill_id });
    assert.equal(routed.selected_skill_id, skill.skill_id);
    assert.equal(routed.decision.rejected_skill_ids.length, loaded.surface.skills.length - 1);
  }
});

test("g05_route: an unnamed request selects nothing, because no evolution skill triggers", () => {
  const routed = route({ requestText: "run governed evolution now" });

  assert.equal(routed.decision.mode, "none");
  assert.equal(routed.selected_skill_id, null);
  assert.equal(routed.disclosure, null);
  assert.equal(routed.decision.context_budget_tokens, 0);
});

test("g05_route: the decision binds the exact surface it was routed against", () => {
  const routed = route({ explicitSkillId: "foundry-archive" });

  assert.equal(routed.decision.policy_hash, surfaceReceipt(loaded).receipt_hash);
});

test("g05_route: routing the same request twice yields the same decision", () => {
  const first = route({ explicitSkillId: "foundry-challenge" });
  const second = route({ explicitSkillId: "foundry-challenge" });

  assert.equal(first.decision.decision_hash, second.decision.decision_hash);
  assert.deepEqual(first.decision, second.decision);
});

test("g05_route: a selected skill discloses within the declared context budget", () => {
  const routed = route({
    context: MAXIMAL_DISCLOSURE_CONTEXT,
    explicitSkillId: "foundry-promote-evolved",
  });

  assert.equal(
    routed.decision.context_budget_tokens,
    loaded.inventory.budgets.activation_max_o200k_tokens,
  );
  assert.ok(
    routed.disclosure.activation_o200k_tokens <=
      loaded.inventory.budgets.activation_max_o200k_tokens,
  );
});

test("g05_route: the routed skill reports the commands that exist and those that do not", () => {
  const replay = route({ explicitSkillId: "foundry-evolution-replay" });

  assert.deepEqual([...replay.available_commands], ["replay diff"]);
  assert.deepEqual([...replay.proposed_commands_unavailable], ["evolve replay"]);
});

test("g05_route: a router skill claims no command of its own", () => {
  const router = route({ explicitSkillId: "foundry-evolve" });

  assert.deepEqual([...router.available_commands], []);
  assert.deepEqual([...router.proposed_commands_unavailable], []);
});

test("g05_disclosure: a conditional reference appears only when its predicate holds", () => {
  const without = resolveDisclosure(loaded, "foundry-evolve-convert", {});
  const with_ = resolveDisclosure(loaded, "foundry-evolve-convert", { backend_id: "shinka" });

  assert.ok(!without.reference_ids.includes("EFREF-BACKEND-SHINKA-V4"));
  assert.ok(with_.reference_ids.includes("EFREF-BACKEND-SHINKA-V4"));
  assert.ok(with_.reference_ids.length > without.reference_ids.length);
});

test("g05_disclosure: an unrelated predicate value does not open the reference", () => {
  const plan = resolveDisclosure(loaded, "foundry-evolve-convert", { backend_id: "other" });

  assert.ok(!plan.reference_ids.includes("EFREF-BACKEND-SHINKA-V4"));
});

test("g05_disclosure: an evolution-origin candidate opens the Parliament statistics reference", () => {
  const ordinary = resolveDisclosure(loaded, "foundry-parliament", {});
  const evolved = resolveDisclosure(loaded, "foundry-parliament", {
    candidate_origin: "EVOLUTION",
  });

  assert.ok(!ordinary.reference_ids.includes("EFREF-EVOLUTION-VERIFIER-STATISTICS-V4"));
  assert.ok(evolved.reference_ids.includes("EFREF-EVOLUTION-VERIFIER-STATISTICS-V4"));
});

test("g05_disclosure: a transitive dependency is disclosed with the reference that needs it", () => {
  const plan = resolveDisclosure(loaded, "foundry-evolve", {});

  assert.ok(plan.reference_ids.includes("EFREF-ROUTER-E0-E5-V4"));
  assert.ok(plan.reference_ids.includes("EFREF-CORE-CONSTITUTION-V4"));
  assert.ok(plan.closure_depth >= 2);
});

test("g05_disclosure: every skill stays within every declared budget at maximal context", () => {
  for (const skill of loaded.surface.skills) {
    const plan = resolveDisclosure(loaded, skill.skill_id, MAXIMAL_DISCLOSURE_CONTEXT);
    assert.equal(assertWithinBudget(loaded, plan), plan);
  }
});

test("g05_disclosure: the plan reports sizes taken from the inventory, not from bodies", () => {
  const plan = resolveDisclosure(loaded, "foundry-archive", {});
  const expectedBytes = plan.reference_ids.reduce(
    (total, id) => total + loaded.referencesById.get(id).byte_count,
    0,
  );

  assert.equal(plan.closure_utf8_bytes, expectedBytes);
  assert.equal(
    plan.activation_utf8_bytes,
    loaded.inventory.metadata_projection.byte_count +
      loaded.inventory.skills.find((row) => row.skill_id === "foundry-archive").byte_count +
      expectedBytes,
  );
});

test("g05_surface: each proposed command has exactly one owner", () => {
  const owners = new Map();
  for (const skill of loaded.surface.skills) {
    for (const command of skill.proposed_commands) {
      assert.ok(!owners.has(command), command);
      owners.set(command, skill.skill_id);
    }
  }

  assert.equal(owners.size, loaded.proposedCommands.length);
  assert.deepEqual([...owners.keys()].sort(), [...loaded.proposedCommands]);
});

test("g05_surface: the loaded surface is frozen", () => {
  assert.ok(Object.isFrozen(loaded));
  assert.throws(() => {
    loaded.surface = null;
  }, TypeError);

  const skill = loaded.surface.skills[0];
  const authorityCommand = loaded.authorityBearingCommands[0];
  assert.ok(Object.isFrozen(loaded.surface));
  assert.ok(Object.isFrozen(skill.available_commands));
  assert.ok(Object.isFrozen(loaded.inventory.budgets));
  assert.ok(Object.isFrozen(loaded.projectedCommands[0]));
  assert.throws(() => skill.available_commands.push(authorityCommand), TypeError);
  assert.throws(() => {
    loaded.inventory.budgets.activation_max_o200k_tokens = 0;
  }, TypeError);
  assert.equal("set" in loaded.agentCards, false);
  assert.equal("set" in loaded.referencesById, false);
  assert.throws(() => Map.prototype.set.call(loaded.agentCards, "forged", {}), TypeError);
  assert.throws(() => Map.prototype.set.call(loaded.referencesById, "forged", {}), TypeError);

  const immutableReceipt = surfaceReceipt(loaded);
  assert.ok(Object.isFrozen(immutableReceipt));
  assert.ok(Object.isFrozen(immutableReceipt.sources));
  assert.ok(immutableReceipt.sources.every((row) => Object.isFrozen(row)));
});

test("g05_surface: the surface claims three of the four mutable genome kinds", () => {
  const claimed = new Set(loaded.surface.skills.flatMap((row) => row.mutable_kinds));

  assert.equal(claimed.size, 3);
  assert.ok(!claimed.has("schemas/prompt-genome.schema.json"));
  assert.equal(loaded.mutableSearchSpace.length, 4);
});

test("g05_surface: skills that mutate nothing declare nothing", () => {
  const mutating = loaded.surface.skills
    .filter((row) => row.mutable_kinds.length > 0)
    .map((row) => row.skill_id);

  assert.deepEqual(mutating, ["foundry-challenge", "foundry-evolve-run", "foundry-evolve-setup"]);
});
