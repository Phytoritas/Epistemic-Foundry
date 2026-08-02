// Test scaffolding: a staged repository root the adversarial suite may damage.
//
// Every hostile case needs an input that is wrong in exactly one way, so the
// declaring inputs are copied into a temporary root and mutated there.  The real
// repository is never written to by a test.  The hook gateway is imported code
// rather than a staged file, so its vocabulary is the sealed one in every case.

import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

import {
  EVOLUTION_BUNDLE_PATH,
  HOLDOUT_BUNDLE_PATH,
  HOLDOUT_MANIFEST_SCHEMA_PATH,
  HOOK_EVENT_ENVELOPE_SCHEMA_PATH,
  PLUGIN_MANIFEST_PATH,
  REGISTRATIONS_PATH,
  REPOSITORY_ROOT,
} from "./observability.mjs";

/** Exactly the paths `loadObservability` and its receipt read. */
const STAGED_PATHS = Object.freeze([
  EVOLUTION_BUNDLE_PATH,
  HOLDOUT_BUNDLE_PATH,
  HOLDOUT_MANIFEST_SCHEMA_PATH,
  HOOK_EVENT_ENVELOPE_SCHEMA_PATH,
  PLUGIN_MANIFEST_PATH,
  REGISTRATIONS_PATH,
]);

export const stageRoot = (t) => {
  const root = mkdtempSync(join(tmpdir(), "ef-h05-"));
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

/** Stage a root whose registration set has been mutated in one way. */
export const stageRegistrations = (t, mutate) => {
  const root = stageRoot(t);
  const declaration = readStagedJson(root, REGISTRATIONS_PATH);
  mutate(declaration, root);
  writeStagedJson(root, REGISTRATIONS_PATH, declaration);
  return root;
};

/** Stage a root whose evolution or holdout hook bundle has been mutated. */
export const stageBundle = (t, path, mutate) => {
  const root = stageRoot(t);
  const bundle = readStagedJson(root, path);
  mutate(bundle, root);
  writeStagedJson(root, path, bundle);
  return root;
};

/** Stage a root whose sealed holdout manifest schema has been mutated. */
export const stageHoldoutSchema = (t, mutate) => {
  const root = stageRoot(t);
  const schema = readStagedJson(root, HOLDOUT_MANIFEST_SCHEMA_PATH);
  mutate(schema, root);
  writeStagedJson(root, HOLDOUT_MANIFEST_SCHEMA_PATH, schema);
  return root;
};

export const byId = (declaration, registrationId) =>
  declaration.registrations.find((row) => row.registration_id === registrationId);

/** Run `run` and return the refusal it raises, or fail loudly if it does not. */
export const refusal = (run) => {
  try {
    run();
  } catch (error) {
    return error;
  }
  throw new Error("expected a refusal, but the call succeeded");
};

/** The asynchronous form of `refusal`, for the observation path. */
export const asyncRefusal = async (run) => {
  try {
    await run();
  } catch (error) {
    return error;
  }
  throw new Error("expected a refusal, but the call succeeded");
};

/** One observation the registration set actually declares. */
export const OBSERVATION_TEMPLATE = Object.freeze({
  eventId: "EFH05-EVENT-0001",
  eventType: "PreToolUse",
  host: "codex",
  observedAt: "2026-08-02T07:00:00Z",
  registrationId: "EFH05-OBS-EVOLUTION-PRE-TOOL",
  sessionId: "SESSION-H05-0001",
  toolName: "Bash",
});

/** A payload that names no holdout-flagged field. */
export const CLEAN_PAYLOAD = Object.freeze({
  candidate_id: "CAND-0001",
  command: "efoundry evolve inspect",
  run_id: "RUN-0001",
});
