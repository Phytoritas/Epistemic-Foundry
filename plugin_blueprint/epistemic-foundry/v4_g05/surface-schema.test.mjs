// schema_and_type_check — the surface reads its vocabulary, it never restates it.
//
// Every set this surface binds has a declaring source: the skills and their
// reference closure come from the payload inventory, the CLI commands from the
// sealed tool-surface projection, the proposed evolution CLI from the section
// of the specification that proposes it, and the mutable search space from the
// sealed C05 index.  A declaring source that changes must break this suite
// rather than leave a surface describing a plugin that no longer exists.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  deriveAuthorityBearingCommands,
  deriveEvolutionSkillIds,
  FAMILY_INDEX_PATH,
  FINDING_CODES,
  INVENTORY_PATH,
  loadSurface,
  MAXIMAL_DISCLOSURE_CONTEXT,
  parseAgentCard,
  parseProposedCommands,
  PAYLOAD_ROOT,
  REPOSITORY_ROOT,
  resolveDisclosure,
  ROUTING_DECISION_SCHEMA_PATH,
  routeEvolutionRequest,
  SPEC_PATH,
} from "./index.mjs";
import { ROUTE_TEMPLATE } from "./surface-fixtures.mjs";

const loaded = loadSurface();
const readRepo = (relative) => readFileSync(join(REPOSITORY_ROOT, relative), "utf8");

test("g05_surface: the declared skills are the ones the membership rule derives", () => {
  const derived = deriveEvolutionSkillIds(loaded.inventory, loaded.surface.membership);

  assert.deepEqual(
    loaded.surface.skills.map((row) => row.skill_id),
    [...derived],
  );
  assert.equal(derived.length, 15);
});

test("g05_surface: every declared skill exists in the payload inventory", () => {
  const declared = new Set(loaded.inventory.skills.map((row) => row.skill_id));

  for (const skill of loaded.surface.skills) {
    assert.ok(declared.has(skill.skill_id), skill.skill_id);
  }
});

test("g05_surface: the parent router is the inventory's parent and is not in the surface", () => {
  assert.equal(loaded.surface.parent_skill_id, loaded.inventory.parent_skill_id);
  assert.ok(!loaded.surface.skills.some((row) => row.skill_id === "foundry"));
});

test("g05_surface: the proposed CLI comes from the section that proposes it", () => {
  const proposed = parseProposedCommands(readRepo(SPEC_PATH));

  assert.deepEqual([...loaded.proposedCommands], [...proposed]);
  assert.equal(proposed.length, 25);
  assert.ok(proposed.includes("evolve run"));
  assert.ok(proposed.includes("backend shinka qualify"));
});

test("g05_surface: no proposed evolution command is projected by the tool surface", () => {
  const projected = new Set(loaded.projectedCommands.map((row) => row.command));

  assert.deepEqual(
    loaded.proposedCommands.filter((command) => projected.has(command)),
    [],
  );
  assert.equal(projected.size, 22);
});

test("g05_surface: every available command is one the tool surface projects", () => {
  const projected = new Set(loaded.projectedCommands.map((row) => row.command));

  for (const skill of loaded.surface.skills) {
    for (const command of skill.available_commands) {
      assert.ok(projected.has(command), `${skill.skill_id}: ${command}`);
    }
  }
});

test("g05_surface: the authority-bearing set is derived from the sealed catalog", () => {
  const derived = deriveAuthorityBearingCommands(
    loaded.projectedCommands,
    loaded.surface.authority_objects,
  );

  assert.deepEqual([...derived], ["claim promote", "passport publish"]);
  for (const command of derived) {
    const entry = loaded.projectedCommands.find((row) => row.command === command);
    assert.equal(entry.mutating, true);
  }
});

test("g05_surface: no evolution skill names an authority-bearing command", () => {
  for (const skill of loaded.surface.skills) {
    for (const command of skill.available_commands) {
      assert.ok(!loaded.authorityBearingCommands.includes(command), command);
    }
  }
});

test("g05_surface: the denied authority set is exactly the one the exit criteria name", () => {
  assert.deepEqual(loaded.surface.denied_authority, [
    "evaluator_mutation",
    "holdout_read",
    "promotion",
  ]);
});

test("g05_surface: every mutable kind is a member of the sealed search space", () => {
  const sealed = JSON.parse(readRepo(FAMILY_INDEX_PATH)).mutable_search_space;

  assert.deepEqual([...loaded.mutableSearchSpace], sealed);
  for (const skill of loaded.surface.skills) {
    for (const kind of skill.mutable_kinds) assert.ok(sealed.includes(kind), kind);
  }
});

test("g05_surface: the inventory hashes the files it describes", () => {
  const inventory = JSON.parse(readRepo(INVENTORY_PATH));

  assert.equal(inventory.inventory_hash, loaded.inventory.inventory_hash);
  assert.equal(inventory.skills.length, 29);
  assert.equal(inventory.references.length, 17);
});

test("g05_surface: an agent card yields its policy and its activation phrases", () => {
  const parent = parseAgentCard(
    readRepo(`${PAYLOAD_ROOT}/skills/foundry/agents/openai.yaml`),
    "foundry",
  );

  assert.equal(parent.policy.invocation_disposition, "PARENT_ROUTER");
  assert.equal(parent.policy.allow_implicit_invocation, true);
  assert.equal(parent.triggerPhrases.length, 6);
  assert.equal(parent.exclusionPhrases.length, 5);
});

test("g05_surface: no evolution skill declares an activation phrase", () => {
  for (const skill of loaded.surface.skills) {
    const card = loaded.agentCards.get(skill.skill_id);
    assert.deepEqual(card.triggerPhrases, []);
    assert.deepEqual(card.exclusionPhrases, []);
  }
});

test("g05_surface: each skill's payload policy matches its inventory projection", () => {
  for (const skill of loaded.surface.skills) {
    const card = loaded.agentCards.get(skill.skill_id);
    const projection = loaded.inventory.skills.find((row) => row.skill_id === skill.skill_id);
    assert.equal(card.policy.invocation_disposition, projection.invocation_disposition);
    assert.equal(card.policy.allow_implicit_invocation, projection.allow_implicit_invocation);
  }
});

test("g05_surface: a disclosure plan is sorted, unique and closed over dependencies", () => {
  for (const skill of loaded.surface.skills) {
    const plan = resolveDisclosure(loaded, skill.skill_id, MAXIMAL_DISCLOSURE_CONTEXT);
    assert.deepEqual([...plan.reference_ids], [...plan.reference_ids].sort());
    assert.equal(new Set(plan.reference_ids).size, plan.reference_ids.length);
    for (const id of plan.reference_ids) {
      for (const next of loaded.referencesById.get(id).depends_on) {
        assert.ok(plan.reference_ids.includes(next), `${id} -> ${next}`);
      }
    }
  }
});

test("g05_surface: every budget this surface enforces is declared by the inventory", () => {
  for (const key of [
    "reference_closure_max_count",
    "reference_closure_max_depth",
    "reference_closure_max_utf8_bytes",
    "reference_closure_max_o200k_tokens",
    "activation_max_utf8_bytes",
    "activation_max_o200k_tokens",
  ]) {
    assert.equal(typeof loaded.inventory.budgets[key], "number", key);
  }
});

test("g05_surface: every finding code carries a code and a reason", () => {
  assert.equal(Object.keys(FINDING_CODES).length, 18);
  for (const [code, reason] of Object.entries(FINDING_CODES)) {
    assert.equal(code, code.toUpperCase());
    assert.ok(reason.length > 50, code);
  }
});

test("g05_surface: the emitted decision validates against the canonical schema", (t) => {
  const routed = routeEvolutionRequest(loaded, {
    ...ROUTE_TEMPLATE,
    explicitSkillId: "foundry-evolve-run",
  });
  const temporaryRoot = mkdtempSync(join(tmpdir(), "ef-g05-schema-"));
  t.after(() => rmSync(temporaryRoot, { force: true, recursive: true }));
  const instancePath = join(temporaryRoot, "skill-routing-decision.json");
  writeFileSync(instancePath, JSON.stringify(routed.decision), "utf8");
  const script = `
import json
import pathlib
import sys
from jsonschema import Draft202012Validator, FormatChecker

schema = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
instance = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
Draft202012Validator.check_schema(schema)
errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance))
if errors:
    raise SystemExit("; ".join(error.message for error in errors))
print("SkillRoutingDecision valid")
`;
  const result = spawnSync(
    "uv",
    [
      "run",
      "--locked",
      "python",
      "-",
      join(REPOSITORY_ROOT, ROUTING_DECISION_SCHEMA_PATH),
      instancePath,
    ],
    { cwd: REPOSITORY_ROOT, encoding: "utf8", input: script },
  );

  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  assert.equal(result.stdout.trim(), "SkillRoutingDecision valid");
});

test("g05_surface: the surface declaration is exactly the fields the loader requires", () => {
  assert.deepEqual(Object.keys(loaded.surface).sort(), [
    "authority_objects",
    "denied_authority",
    "membership",
    "parent_skill_id",
    "skills",
    "surface_id",
    "surface_version",
  ]);
  for (const skill of loaded.surface.skills) {
    assert.deepEqual(Object.keys(skill).sort(), [
      "available_commands",
      "mutable_kinds",
      "proposed_commands",
      "skill_id",
    ]);
  }
});

test("g05_surface: the membership rule is data, not a hard-coded skill list", () => {
  assert.deepEqual(loaded.surface.membership.reference_id_prefixes, ["EFREF-EVOLUTION-"]);
  assert.deepEqual(loaded.surface.membership.reference_ids, ["EFREF-BACKEND-SHINKA-V4"]);
  const widened = deriveEvolutionSkillIds(loaded.inventory, {
    reference_id_prefixes: ["EFREF-"],
    reference_ids: [],
  });
  assert.equal(widened.length, loaded.inventory.skills.length);
});
