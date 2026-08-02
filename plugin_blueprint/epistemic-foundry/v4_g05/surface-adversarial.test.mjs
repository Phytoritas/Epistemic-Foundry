// negative_and_adversarial_tests — every way the surface can lie, refused.
//
// A routing surface fails quietly: it claims a command that does not exist, or
// keeps describing a skill that was renamed, and nothing notices until a user
// is told to run something impossible.  So each hostile input is staged as a
// copy of the declaring sources that is wrong in exactly one way, and each must
// be refused by its own code.
//
// The CLI projection is imported code rather than a staged file, so it is the
// real sealed projection in every case below.

import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  EvolutionSurfaceError,
  INVENTORY_PATH,
  loadSurface,
  PAYLOAD_ROOT,
  resolveDisclosure,
  routeEvolutionRequest,
  SPEC_PATH,
} from "./index.mjs";
import {
  readStaged,
  refusal,
  ROUTE_TEMPLATE,
  stageInventory,
  stageRoot,
  stageSurface,
  writeStaged,
} from "./surface-fixtures.mjs";

const loaded = loadSurface();
const bySkill = (surface, skillId) => surface.skills.find((row) => row.skill_id === skillId);
const refused = (root) => {
  const error = refusal(() => loadSurface({ root }));
  assert.ok(error instanceof EvolutionSurfaceError, error.message);
  return error;
};

test("g05_refuse: a command the specification never proposes is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    bySkill(surface, "foundry-evolve").proposed_commands = ["evolve teleport"];
  });

  const error = refused(root);
  assert.equal(error.code, "COMMAND_UNPROPOSED");
  assert.equal(error.context.command, "evolve teleport");
});

test("g05_refuse: declaring an existing command as merely proposed is refused", (t) => {
  const root = stageRoot(t);
  // A future in which the specification proposes a command the tool surface
  // already projects: the surface must promote it, not keep understating it.
  const spec = readStaged(root, SPEC_PATH).replace(
    "efoundry promote evolved\n",
    "efoundry promote evolved\nefoundry parliament plan\n",
  );
  writeStaged(root, SPEC_PATH, spec);
  const surface = JSON.parse(readStaged(root, "plugin_blueprint/epistemic-foundry/v4_g05/evolution-surface.json"));
  bySkill(surface, "foundry-parliament").proposed_commands = ["parliament plan"];
  writeStaged(
    root,
    "plugin_blueprint/epistemic-foundry/v4_g05/evolution-surface.json",
    `${JSON.stringify(surface, null, 2)}\n`,
  );

  const error = refused(root);
  assert.equal(error.code, "COMMAND_MISDECLARED");
  assert.equal(error.context.command, "parliament plan");
});

test("g05_refuse: two skills claiming one command is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    bySkill(surface, "foundry-evolve").proposed_commands = ["evolve run"];
  });

  const error = refused(root);
  assert.equal(error.code, "COMMAND_CLAIMED_TWICE");
  assert.deepEqual(error.context.skill_ids, ["foundry-evolve", "foundry-evolve-run"]);
});

test("g05_refuse: a proposed command nobody owns is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    bySkill(surface, "foundry-evolve-setup").proposed_commands = [];
  });

  const error = refused(root);
  assert.equal(error.code, "PROPOSED_COMMAND_UNROUTED");
  assert.deepEqual(error.context.unrouted, ["evolve setup"]);
});

test("g05_refuse: naming a command the tool surface does not project is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    bySkill(surface, "foundry-parliament").available_commands = [
      "parliament dance",
      "parliament execute",
      "parliament plan",
    ];
  });

  const error = refused(root);
  assert.equal(error.code, "COMMAND_UNPROJECTED");
  assert.equal(error.context.command, "parliament dance");
});

test("g05_refuse: naming the promotion command is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    bySkill(surface, "foundry-promote-evolved").available_commands = ["claim promote"];
  });

  const error = refused(root);
  assert.equal(error.code, "AUTHORITY_CLAIMED");
  assert.equal(error.context.command, "claim promote");
});

test("g05_refuse: naming the passport publication command is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    bySkill(surface, "foundry-promote-evolved").available_commands = ["passport publish"];
  });

  const error = refused(root);
  assert.equal(error.code, "AUTHORITY_CLAIMED");
  assert.equal(error.context.command, "passport publish");
});

test("g05_refuse: weakening the denied-authority set is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    surface.denied_authority = ["evaluator_mutation", "holdout_read"];
  });

  const error = refused(root);
  assert.equal(error.code, "AUTHORITY_CLAIMED");
});

test("g05_refuse: an authority predicate that matches nothing is refused as vacuous", (t) => {
  const root = stageSurface(t, (surface) => {
    surface.authority_objects = [];
  });

  const error = refused(root);
  assert.equal(error.code, "AUTHORITY_PREDICATE_EMPTY");
});

test("g05_refuse: mutating a genome outside the sealed search space is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    bySkill(surface, "foundry-archive").mutable_kinds = [
      "schemas/evolution-candidate.schema.json",
    ];
  });

  const error = refused(root);
  assert.equal(error.code, "SEARCH_SPACE_VIOLATION");
  assert.equal(error.context.kind, "schemas/evolution-candidate.schema.json");
});

test("g05_refuse: dropping an evolution skill from the surface is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    surface.skills = surface.skills.filter((row) => row.skill_id !== "foundry-shinka-adapter");
  });

  const error = refused(root);
  assert.equal(error.code, "MEMBERSHIP_DRIFT");
  assert.ok(error.context.derived.includes("foundry-shinka-adapter"));
});

test("g05_refuse: adding a skill the membership rule excludes is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    surface.skills = [
      ...surface.skills,
      {
        available_commands: [],
        mutable_kinds: [],
        proposed_commands: [],
        skill_id: "foundry-recall",
      },
    ].sort((left, right) => (left.skill_id < right.skill_id ? -1 : 1));
  });

  const error = refused(root);
  assert.equal(error.code, "MEMBERSHIP_DRIFT");
  assert.ok(error.context.declared.includes("foundry-recall"));
});

test("g05_refuse: an unsorted declaration is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    surface.skills = [...surface.skills].reverse();
  });

  const error = refused(root);
  assert.equal(error.code, "DECLARATION_NONCANONICAL");
});

test("g05_refuse: a repeated command entry is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    bySkill(surface, "foundry-evolution-stop").proposed_commands = ["evolve stop", "evolve stop"];
  });

  const error = refused(root);
  assert.equal(error.code, "DECLARATION_NONCANONICAL");
});

test("g05_refuse: an unexpected field on a skill row is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    bySkill(surface, "foundry-archive").may_promote = true;
  });

  const error = refused(root);
  assert.equal(error.code, "SURFACE_UNREADABLE");
});

test("g05_refuse: a surface whose parent is not the inventory parent is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    surface.parent_skill_id = "foundry-evolve";
  });

  const error = refused(root);
  assert.equal(error.code, "PARENT_UNDECLARED");
});

test("g05_refuse: a payload skill edited after the inventory was sealed is refused", (t) => {
  const root = stageRoot(t);
  appendFileSync(
    join(root, `${PAYLOAD_ROOT}/skills/foundry-evolve-run/SKILL.md`),
    "\nAn instruction nobody sealed.\n",
    "utf8",
  );

  const error = refused(root);
  assert.equal(error.code, "INVENTORY_HASH_DRIFT");
  assert.equal(error.context.path, "skills/foundry-evolve-run/SKILL.md");
});

test("g05_refuse: an inventory whose stated hash was rewritten is refused", (t) => {
  const root = stageRoot(t);
  const inventory = JSON.parse(readStaged(root, INVENTORY_PATH));
  inventory.inventory_hash = `sha256:${"0".repeat(64)}`;
  writeStaged(root, INVENTORY_PATH, `${JSON.stringify(inventory, null, 2)}\n`);

  const error = refused(root);
  assert.equal(error.code, "INVENTORY_HASH_DRIFT");
  assert.equal(error.context.stated, `sha256:${"0".repeat(64)}`);
});

test("g05_refuse: a payload policy that contradicts its inventory projection is refused", (t) => {
  const root = stageRoot(t);
  const card = `${PAYLOAD_ROOT}/skills/foundry-evolve-run/agents/openai.yaml`;
  writeStaged(
    root,
    card,
    readStaged(root, card).replace(
      "  invocation_disposition: EXPLICIT_ONLY",
      "  invocation_disposition: IMPLICIT_SAFE",
    ),
  );

  const error = refused(root);
  assert.equal(error.code, "POLICY_DRIFT");
  assert.equal(error.context.skill_id, "foundry-evolve-run");
});

test("g05_refuse: an unreadable policy line is refused rather than skipped", (t) => {
  const root = stageRoot(t);
  const card = `${PAYLOAD_ROOT}/skills/foundry-archive/agents/openai.yaml`;
  writeStaged(
    root,
    card,
    readStaged(root, card).replace("policy:\n", "policy:\n  side_effecting true\n"),
  );

  const error = refused(root);
  assert.equal(error.code, "POLICY_DRIFT");
});

test("g05_refuse: a specification without the proposed CLI block is refused", (t) => {
  const root = stageRoot(t);
  writeStaged(root, SPEC_PATH, readStaged(root, SPEC_PATH).replace("## 35. Proposed CLI", "## 35. Removed"));

  const error = refused(root);
  assert.equal(error.code, "SPEC_BLOCK_MISSING");
});

test("g05_refuse: a reference a skill depends on but the inventory dropped is refused", (t) => {
  const root = stageInventory(t, (inventory) => {
    inventory.references = inventory.references.filter(
      (row) => row.reference_id !== "EFREF-CORE-STATUS-RECEIPTS-V4",
    );
  });

  const error = refused(root);
  assert.equal(error.code, "REFERENCE_UNDECLARED");
  assert.equal(error.context.reference_id, "EFREF-CORE-STATUS-RECEIPTS-V4");
});

test("g05_refuse: a closure that outgrows its declared budget is refused", (t) => {
  const root = stageInventory(t, (inventory) => {
    inventory.budgets.reference_closure_max_count = 3;
  });

  const error = refused(root);
  assert.equal(error.code, "DISCLOSURE_BUDGET_EXCEEDED");
  assert.equal(error.context.budget, "reference_closure_max_count");
  assert.equal(error.context.limit, 3);
});

test("g05_refuse: a missing budget is refused rather than treated as unbounded", (t) => {
  const root = stageInventory(t, (inventory) => {
    delete inventory.budgets.activation_max_utf8_bytes;
  });

  const error = refused(root);
  assert.equal(error.code, "DISCLOSURE_BUDGET_EXCEEDED");
  assert.equal(error.context.budget, "activation_max_utf8_bytes");
});

test("g05_refuse: routing a skill outside the surface is refused", () => {
  const error = refusal(() =>
    routeEvolutionRequest(loaded, { ...ROUTE_TEMPLATE, explicitSkillId: "foundry-recall" }),
  );

  assert.equal(error.code, "SKILL_OUT_OF_SURFACE");
  assert.equal(error.context.skill_id, "foundry-recall");
});

test("g05_refuse: disclosing for a skill the payload does not declare is refused", () => {
  const error = refusal(() => resolveDisclosure(loaded, "foundry-invented", {}));

  assert.equal(error.code, "SKILL_OUT_OF_SURFACE");
});

test("g05_refuse: a surface file that is not the declared object is refused", (t) => {
  const root = stageSurface(t, (surface) => {
    delete surface.membership;
  });

  const error = refused(root);
  assert.equal(error.code, "SURFACE_UNREADABLE");
});
