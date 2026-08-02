// Test scaffolding: a staged repository root the adversarial suite may damage.
//
// Every hostile case needs an input that is wrong in exactly one way, so the
// declaring inputs are copied into a temporary root and mutated there.  The
// real repository is never written to by a test.

import { createHash } from "node:crypto";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

import { canonicalizeSkillRoutingJson } from "../../../packages/plugin-host/src/skill-router/skill-router.mjs";
import { INVENTORY_PATH, PAYLOAD_ROOT, REPOSITORY_ROOT, SPEC_PATH, SURFACE_PATH } from "./surface.mjs";

/** The inputs `loadSurface` reads by path; the CLI projection is imported code. */
const STAGED_PATHS = Object.freeze([
  SPEC_PATH,
  "schemas/skill-routing-decision.schema.json",
  "schemas/v4_c05/family-index.json",
  `${PAYLOAD_ROOT}/skills`,
  SURFACE_PATH,
]);

export const stageRoot = (t) => {
  const root = mkdtempSync(join(tmpdir(), "ef-g05-"));
  t.after(() => rmSync(root, { force: true, recursive: true }));
  for (const relative of STAGED_PATHS) {
    const target = join(root, relative);
    mkdirSync(dirname(target), { recursive: true });
    cpSync(join(REPOSITORY_ROOT, relative), target, { recursive: true });
  }
  return root;
};

export const readStaged = (root, relative) => readFileSync(join(root, relative), "utf8");

export const writeStaged = (root, relative, text) =>
  writeFileSync(join(root, relative), text, "utf8");

export const readStagedJson = (root, relative) => JSON.parse(readStaged(root, relative));

export const writeStagedJson = (root, relative, value) =>
  writeStaged(root, relative, `${JSON.stringify(value, null, 2)}\n`);

/** Stage a root whose surface declaration has been mutated in one way. */
export const stageSurface = (t, mutate) => {
  const root = stageRoot(t);
  const surface = readStagedJson(root, SURFACE_PATH);
  mutate(surface, root);
  writeStagedJson(root, SURFACE_PATH, surface);
  return root;
};

/**
 * Stage a root whose skill inventory has been mutated and re-sealed.
 *
 * The inventory carries its own hash, so a test that only edited the content
 * would be caught by the integrity check before reaching the case it meant to
 * exercise; re-sealing keeps each hostile input wrong in exactly one way.
 */
export const stageInventory = (t, mutate) => {
  const root = stageRoot(t);
  const inventory = readStagedJson(root, INVENTORY_PATH);
  mutate(inventory, root);
  writeStagedJson(root, INVENTORY_PATH, resealed(inventory));
  return root;
};

export const resealed = (inventory) => {
  const withoutHash = { ...inventory };
  delete withoutHash.inventory_hash;
  const digest = createHash("sha256")
    .update(Buffer.from(canonicalizeSkillRoutingJson(withoutHash), "utf8"))
    .digest("hex");
  return { ...inventory, inventory_hash: `sha256:${digest}` };
};

/** Run `run` and return the refusal it raises, or fail loudly if it does not. */
export const refusal = (run) => {
  try {
    run();
  } catch (error) {
    return error;
  }
  throw new Error("expected a refusal, but the call succeeded");
};

export const ROUTE_TEMPLATE = Object.freeze({
  decidedAt: "2026-08-02T07:00:00.000Z",
  requestId: "REQ-G05-0001-FIXTURE",
  requestText: "run governed evolution for this hypothesis family",
});
