import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  REQUIRED_METADATA_KEYS,
  REQUIRED_SECTIONS,
  lintRunbookDirectory,
  lintRunbookText,
  parseDurationToMs,
} from "./runbook-lint.mjs";

const repositoryRoot = path.resolve(import.meta.dirname, "../../..");
const runbookDirectory = path.join(repositoryRoot, "ops", "runbooks");

const EXPECTED_RUNBOOKS = ["backup.md", "corruption-response.md", "disaster-recovery.md"];

test("runbook_lint: every shipped operational runbook is structurally clean", () => {
  const results = lintRunbookDirectory(runbookDirectory);
  assert.deepEqual([...results.keys()].sort(), EXPECTED_RUNBOOKS);
  for (const [name, parsed] of results) {
    assert.ok(parsed.metadata.id.startsWith("RB-"), `${name} has an RB- id`);
    assert.equal(parsed.metadata.title, parsed.title, `${name} title matches H1`);
    assert.ok(parsed.steps.length >= 2, `${name} has actionable procedure steps`);
    // Every documented RPO/RTO is a measured duration the drill can enforce.
    assert.ok(parseDurationToMs(parsed.metadata.rpo) > 0, `${name} RPO is measured`);
    assert.ok(parseDurationToMs(parsed.metadata.rto) > 0, `${name} RTO is measured`);
  }
});

test("runbook_lint: the shipped disaster-recovery runbook binds RPO and RTO budgets", () => {
  const results = lintRunbookDirectory(runbookDirectory);
  const dr = results.get("disaster-recovery.md");
  assert.ok(dr, "disaster-recovery runbook is present");
  assert.equal(dr.metadata.id, "RB-Y03-DR-RESTORE");
  assert.equal(parseDurationToMs(dr.metadata.rpo), 15 * 60_000);
  assert.equal(parseDurationToMs(dr.metadata.rto), 30 * 60_000);
});

// --- Negative fixtures: prove the lint is fail-closed, not vacuous. ---------

const CLEAN = readFileSync(path.join(runbookDirectory, "backup.md"), "utf8");

test("runbook_lint: the clean reference runbook lints without error", () => {
  const parsed = lintRunbookText(CLEAN, "backup.md");
  assert.equal(parsed.metadata.id, "RB-Y03-BACKUP");
});

test("runbook_lint: a placeholder token is rejected", () => {
  const broken = CLEAN.replace("the backup service principal", "TODO the owner");
  assert.throws(() => lintRunbookText(broken, "todo.md"), /placeholder token/u);
});

test("runbook_lint: an angle-bracket placeholder is rejected", () => {
  const broken = CLEAN.replace("Foundry Operations on-call", "<owner name here>");
  assert.throws(() => lintRunbookText(broken, "angle.md"), /placeholder token/u);
});

test("runbook_lint: a vague, unmeasured RPO is rejected", () => {
  const broken = CLEAN.replace("rpo: at most 15 minutes", "rpo: as soon as possible");
  assert.throws(() => lintRunbookText(broken, "vague-rpo.md"), /rpo .* measured duration/u);
});

test("runbook_lint: a missing required section is rejected", () => {
  const broken = CLEAN.replace("## Rollback", "## Notes");
  assert.throws(() => lintRunbookText(broken, "no-rollback.md"), /sections must be exactly/u);
});

test("runbook_lint: out-of-order sections are rejected", () => {
  const broken = CLEAN
    .replace("## Preconditions", "@@PRE@@")
    .replace("## Procedure", "## Preconditions")
    .replace("@@PRE@@", "## Procedure");
  assert.throws(() => lintRunbookText(broken, "reordered.md"), /in order/u);
});

test("runbook_lint: a non-imperative procedure step is rejected", () => {
  const broken = CLEAN.replace(
    "1. Snapshot the live SQLite state store",
    "1. the live SQLite state store is snapshotted",
  );
  assert.throws(() => lintRunbookText(broken, "passive.md"), /imperative verb/u);
});

test("runbook_lint: a procedure step without a Verify line is rejected", () => {
  // Drop the first step's Verify detail block only.
  const broken = CLEAN.replace(
    /   Verify: the backup call returns a positive page count and the destination\n   file exists\.\n/u,
    "",
  );
  assert.throws(() => lintRunbookText(broken, "unverifiable.md"), /missing a "Verify:"/u);
});

test("runbook_lint: mis-numbered procedure steps are rejected", () => {
  const broken = CLEAN.replace(
    "2. Record the SHA-256 digest",
    "3. Record the SHA-256 digest",
  );
  assert.throws(() => lintRunbookText(broken, "misnumbered.md"), /1\.\.N in order/u);
});

test("runbook_lint: a missing required metadata key is rejected", () => {
  const broken = CLEAN.replace(/- owner: .+\n/u, "");
  assert.throws(() => lintRunbookText(broken, "no-owner.md"), /required metadata key "owner"/u);
});

test("runbook_lint: a metadata title that disagrees with the H1 is rejected", () => {
  const broken = CLEAN.replace(
    "- title: State and Artifact Backup",
    "- title: Something Else",
  );
  assert.throws(() => lintRunbookText(broken, "title-mismatch.md"), /must match H1/u);
});

test("runbook_lint: an empty runbook is rejected", () => {
  assert.throws(() => lintRunbookText("   \n", "empty.md"), /runbook is empty/u);
});

test("runbook_lint: contract constants are stable", () => {
  assert.deepEqual(REQUIRED_SECTIONS, [
    "Metadata",
    "Preconditions",
    "Procedure",
    "Verification",
    "Rollback",
    "Escalation",
  ]);
  assert.ok(REQUIRED_METADATA_KEYS.includes("rpo"));
  assert.ok(REQUIRED_METADATA_KEYS.includes("rto"));
});
