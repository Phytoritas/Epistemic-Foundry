// provenance_and_receipt_audit — the surface can prove what it read.
//
// A routing surface that cannot name its inputs is an opinion.  The receipt
// binds every declaring source by digest, re-derives its own hash from exactly
// the fields it publishes, and carries no clock and no randomness, so the same
// repository always produces the same receipt and a changed input always
// produces a different one.

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { computeSkillRoutingDecisionHash } from "../../../packages/plugin-host/src/skill-router/skill-router.mjs";
import {
  FAMILY_INDEX_PATH,
  INVENTORY_PATH,
  loadSurface,
  REPOSITORY_ROOT,
  ROUTING_DECISION_SCHEMA_PATH,
  routeEvolutionRequest,
  SPEC_PATH,
  SURFACE_PATH,
  surfaceReceipt,
} from "./index.mjs";
import { ROUTE_TEMPLATE, stageSurface } from "./surface-fixtures.mjs";

const loaded = loadSurface();
const receipt = surfaceReceipt(loaded);
const digestOf = (relative) =>
  `sha256:${createHash("sha256").update(readFileSync(join(REPOSITORY_ROOT, relative))).digest("hex")}`;

test("g05_receipt: the receipt re-derives its own hash from the fields it publishes", () => {
  const preimage = { ...receipt };
  delete preimage.receipt_id;
  delete preimage.receipt_hash;

  assert.equal(computeSkillRoutingDecisionHash(preimage), receipt.receipt_hash);
});

test("g05_receipt: the receipt identifier is derived from the hash", () => {
  assert.equal(receipt.receipt_id, `EFG05-SURFACE-${receipt.receipt_hash.slice(7, 23)}`);
  assert.match(receipt.receipt_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("g05_receipt: the same repository yields the same receipt", () => {
  assert.deepEqual(surfaceReceipt(loadSurface()), receipt);
});

test("g05_receipt: every declaring source is bound by its actual digest", () => {
  const expected = [
    FAMILY_INDEX_PATH,
    INVENTORY_PATH,
    ROUTING_DECISION_SCHEMA_PATH,
    SPEC_PATH,
    SURFACE_PATH,
  ].sort();

  assert.deepEqual(
    receipt.sources.map((row) => row.path),
    expected,
  );
  for (const row of receipt.sources) assert.equal(row.sha256, digestOf(row.path));
});

test("g05_receipt: a changed declaration changes the receipt", (t) => {
  const root = stageSurface(t, (surface) => {
    surface.surface_version = "4.0.0-g05.2";
  });
  const changed = surfaceReceipt(loadSurface({ root }));

  assert.notEqual(changed.receipt_hash, receipt.receipt_hash);
  assert.equal(changed.surface_version, "4.0.0-g05.2");
});

test("g05_receipt: the receipt records the CLI reality it found", () => {
  assert.equal(receipt.proposed_command_count, 25);
  assert.equal(receipt.projected_command_count, 22);
  assert.deepEqual(receipt.proposed_commands_projected, []);
  assert.equal(receipt.skill_count, 15);
});

test("g05_receipt: every available command is published with its effect class", () => {
  assert.deepEqual(receipt.available_commands, [
    { command: "parliament execute", side_effect_class: "MUTATING_EFFECT" },
    { command: "parliament plan", side_effect_class: "NON_MUTATING" },
    { command: "replay diff", side_effect_class: "NON_MUTATING" },
    { command: "validation execute", side_effect_class: "MUTATING_EFFECT" },
    { command: "validation plan", side_effect_class: "NON_MUTATING" },
  ]);
});

test("g05_receipt: the authority the surface denies and the commands that carry it are both named", () => {
  assert.deepEqual(receipt.denied_authority, [
    "evaluator_mutation",
    "holdout_read",
    "promotion",
  ]);
  assert.deepEqual(receipt.authority_bearing_commands, ["claim promote", "passport publish"]);
  for (const command of receipt.authority_bearing_commands) {
    assert.ok(!receipt.available_commands.some((row) => row.command === command));
  }
});

test("g05_receipt: the genome kinds no skill claims are recorded rather than implied", () => {
  assert.deepEqual(receipt.mutable_kinds_unclaimed, ["schemas/prompt-genome.schema.json"]);
  assert.deepEqual(receipt.mutable_kinds_claimed, [
    "schemas/challenge-genome.schema.json",
    "schemas/experiment-genome.schema.json",
    "schemas/hypothesis-genome.schema.json",
  ]);
});

test("g05_receipt: the absence of implicit reachability is recorded, not assumed", () => {
  assert.deepEqual(receipt.implicitly_reachable_skill_ids, []);
  for (const skill of loaded.surface.skills) {
    assert.equal(loaded.agentCards.get(skill.skill_id).triggerPhrases.length, 0);
  }
});

test("g05_receipt: the receipt binds the sealed inventory hash", () => {
  assert.equal(receipt.inventory_hash, loaded.inventory.inventory_hash);
  assert.equal(receipt.parent_skill_id, "foundry");
});

test("g05_receipt: a routing decision re-derives its own hash", () => {
  const routed = routeEvolutionRequest(loaded, {
    ...ROUTE_TEMPLATE,
    explicitSkillId: "foundry-evolve-setup",
  });
  const preimage = { ...routed.decision };
  delete preimage.decision_id;
  delete preimage.decision_hash;

  assert.equal(computeSkillRoutingDecisionHash(preimage), routed.decision.decision_hash);
});

test("g05_receipt: each routed candidate is bound to the sealed content hash of its skill", () => {
  const routed = routeEvolutionRequest(loaded, {
    ...ROUTE_TEMPLATE,
    explicitSkillId: "foundry-evolve-setup",
  });
  const bindings = routed.decision.authority_notes.filter((note) =>
    note.startsWith("SKILL_METADATA:"),
  );

  assert.equal(bindings.length, loaded.surface.skills.length);
  for (const skill of loaded.surface.skills) {
    const projection = loaded.inventory.skills.find((row) => row.skill_id === skill.skill_id);
    assert.ok(
      bindings.includes(`SKILL_METADATA:${skill.skill_id}:bundled:${projection.sha256}`),
      skill.skill_id,
    );
  }
});

test("g05_receipt: the decision states that routing carries no authority", () => {
  const routed = routeEvolutionRequest(loaded, {
    ...ROUTE_TEMPLATE,
    explicitSkillId: "foundry-challenge",
  });

  assert.ok(routed.decision.authority_notes.includes("ROUTING_DECISION_HAS_NO_STATE_OR_AUTHORITY"));
  assert.ok(routed.decision.authority_notes.includes("FULL_SKILL_INSTRUCTIONS_NOT_LOADED"));
});

test("g05_receipt: the surface holds no clock and no randomness", () => {
  const source = readFileSync(
    join(REPOSITORY_ROOT, "plugin_blueprint/epistemic-foundry/v4_g05/surface.mjs"),
    "utf8",
  );

  for (const forbidden of ["Date.now", "new Date", "Math.random", "process.env"]) {
    assert.ok(!source.includes(forbidden), forbidden);
  }
});

test("g05_receipt: the receipt is canonical JSON", () => {
  assert.deepEqual(JSON.parse(JSON.stringify(receipt)), { ...receipt });
});
