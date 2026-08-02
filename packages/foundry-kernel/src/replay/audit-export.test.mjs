// audit_export_test — the export is complete or it fails.
//
// Exit criterion under test: "audit export complete".  Completeness is a
// reconciliation: every referenced id must be bundled or carry a typed
// exclusion reason, every bundled entry must be reachable from the run, the
// counts must add up, and every entry must carry a content hash.

import assert from "node:assert/strict";
import test from "node:test";

import {
  AuditExportError,
  EXCLUSION_REASONS,
  EXPORT_SECTIONS,
  buildAuditExport,
  reconcileExport,
  validateAuditExport,
} from "./audit-export.mjs";
import { ReplayDriftError, compareReplay } from "./drift.mjs";

const RUN = "RUN-1";
const PLAN_HASH = `sha256:${"1".repeat(64)}`;
const CREATED_AT = "2026-08-01T15:30:00Z";

const hashFor = (id) =>
  `sha256:${id
    .split("")
    .map((char) => char.charCodeAt(0).toString(16).padStart(2, "0"))
    .join("")
    .padEnd(64, "0")
    .slice(0, 64)}`;

function driftReport(mutate = null) {
  const original = { outcome: "SUCCEEDED", metrics: { duration_ms: 10 } };
  const replayed = structuredClone(original);
  if (mutate !== null) mutate(replayed);
  return compareReplay({ original, replayed, run_id: RUN });
}

function referenced(overrides = {}) {
  return {
    artifacts: ["ART-1", "ART-2"],
    checkpoints: ["CP-1"],
    effect_receipts: ["ER-1"],
    gate_decisions: ["GD-1"],
    ...overrides,
  };
}

function bundled(overrides = {}) {
  const base = referenced();
  const sections = Object.fromEntries(
    EXPORT_SECTIONS.map((section) => [
      section,
      base[section].map((id) => ({ content_hash: hashFor(id), id })),
    ]),
  );
  return { ...sections, ...overrides };
}

function build(options = {}) {
  return buildAuditExport({
    bundled: bundled(),
    command_count: 7,
    created_at: CREATED_AT,
    drift_report: driftReport(),
    plan_hash: PLAN_HASH,
    referenced: referenced(),
    run_id: RUN,
    ...options,
  });
}

test("audit_export_test: a complete bundle reconciles and seals", () => {
  const bundle = build();

  assert.equal(bundle.reconciliation.complete, true);
  assert.equal(bundle.reconciliation.missing_count, 0);
  assert.equal(bundle.reconciliation.orphaned_count, 0);
  assert.equal(bundle.reconciliation.referenced_count, 5);
  assert.equal(bundle.reconciliation.present_count, 5);
  assert.match(bundle.export_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.deepEqual(validateAuditExport(bundle), bundle);
});

test("audit_export_test: every section is accounted for", () => {
  const bundle = build();

  assert.deepEqual(Object.keys(bundle.reconciliation.sections).sort(), [
    ...EXPORT_SECTIONS,
  ].sort());
  assert.deepEqual(Object.keys(bundle.entry_hashes).sort(), [...EXPORT_SECTIONS].sort());
});

test("audit_export_test: a referenced artifact that is simply absent fails", () => {
  const incomplete = bundled({
    artifacts: [{ content_hash: hashFor("ART-1"), id: "ART-1" }],
  });

  assert.throws(
    () => build({ bundled: incomplete }),
    (error) =>
      error instanceof AuditExportError &&
      error.code === "EXPORT_INCOMPLETE" &&
      error.details.sections.artifacts.includes("ART-2"),
  );
});

test("audit_export_test: an absence with a typed reason is allowed and recorded", () => {
  const incomplete = bundled({
    artifacts: [{ content_hash: hashFor("ART-1"), id: "ART-1" }],
  });

  const bundle = build({
    bundled: incomplete,
    exclusions: [
      { id: "ART-2", reason: "CONFIDENTIAL_WITHHELD", section: "artifacts" },
    ],
  });

  assert.equal(bundle.reconciliation.complete, true);
  assert.deepEqual(bundle.reconciliation.sections.artifacts.excluded_ids, ["ART-2"]);
  assert.equal(bundle.reconciliation.excluded_count, 1);
  assert.deepEqual(bundle.exclusions, [
    { id: "ART-2", reason: "CONFIDENTIAL_WITHHELD", section: "artifacts" },
  ]);
});

test("audit_export_test: an exclusion reason must be canonical", () => {
  const incomplete = bundled({
    artifacts: [{ content_hash: hashFor("ART-1"), id: "ART-1" }],
  });

  assert.throws(
    () =>
      build({
        bundled: incomplete,
        exclusions: [{ id: "ART-2", reason: "too_big", section: "artifacts" }],
      }),
    (error) =>
      error instanceof AuditExportError &&
      error.code === "EXPORT_EXCLUSION_REASON_INVALID",
  );
  assert.deepEqual(EXCLUSION_REASONS, [
    "CONFIDENTIAL_WITHHELD",
    "EXTERNAL_SYSTEM_OWNED",
    "SUPERSEDED_REVISION",
  ]);
});

test("audit_export_test: an entry cannot be both bundled and excluded", () => {
  assert.throws(
    () =>
      build({
        exclusions: [
          { id: "ART-2", reason: "CONFIDENTIAL_WITHHELD", section: "artifacts" },
        ],
      }),
    (error) =>
      error instanceof AuditExportError &&
      error.code === "EXPORT_EXCLUSION_CONTRADICTED",
  );
});

test("audit_export_test: excluding something the run never referenced is refused", () => {
  assert.throws(
    () =>
      build({
        exclusions: [
          { id: "ART-ghost", reason: "SUPERSEDED_REVISION", section: "artifacts" },
        ],
      }),
    (error) =>
      error instanceof AuditExportError &&
      error.code === "EXPORT_EXCLUSION_UNREFERENCED",
  );
});

test("audit_export_test: an entry the run never referenced is an orphan", () => {
  const extra = bundled();
  extra.artifacts.push({ content_hash: hashFor("ART-9"), id: "ART-9" });

  assert.throws(
    () => build({ bundled: extra }),
    (error) =>
      error instanceof AuditExportError &&
      error.code === "EXPORT_ORPHANED" &&
      error.details.sections.artifacts.includes("ART-9"),
  );
});

test("audit_export_test: a duplicated bundle entry is refused", () => {
  const duplicated = bundled();
  duplicated.artifacts.push({ content_hash: hashFor("ART-1"), id: "ART-1" });

  assert.throws(
    () => build({ bundled: duplicated }),
    (error) =>
      error instanceof AuditExportError && error.code === "EXPORT_DUPLICATE_ENTRY",
  );
});

test("audit_export_test: every bundled entry must carry a sha256 content hash", () => {
  const unhashed = bundled();
  unhashed.artifacts[0].content_hash = "not-a-hash";

  assert.throws(
    () => build({ bundled: unhashed }),
    (error) =>
      error instanceof AuditExportError && error.code === "EXPORT_CONTENT_HASH_INVALID",
  );
});

test("audit_export_test: the reconciliation counts add up", () => {
  const bundle = build();
  const { sections } = bundle.reconciliation;

  const referencedTotal = EXPORT_SECTIONS.reduce(
    (total, section) => total + sections[section].referenced_ids.length,
    0,
  );
  const presentTotal = EXPORT_SECTIONS.reduce(
    (total, section) => total + sections[section].present_ids.length,
    0,
  );

  assert.equal(referencedTotal, bundle.reconciliation.referenced_count);
  assert.equal(presentTotal, bundle.reconciliation.present_count);
});

test("audit_export_test: reconcileExport reports rather than throws for a caller", () => {
  const report = reconcileExport({
    bundled: bundled({ artifacts: [{ content_hash: hashFor("ART-1"), id: "ART-1" }] }),
    referenced: referenced(),
  });

  assert.equal(report.complete, false);
  assert.equal(report.missing_count, 1);
  assert.deepEqual(report.sections.artifacts.missing_ids, ["ART-2"]);
});

test("audit_export_test: the drift report must belong to the same run", () => {
  const foreign = compareReplay({ original: {}, replayed: {}, run_id: "RUN-other" });

  assert.throws(
    () => build({ drift_report: foreign }),
    (error) =>
      error instanceof AuditExportError && error.code === "EXPORT_RUN_MISMATCH",
  );
});

test("audit_export_test: an unsealed drift report cannot be exported", () => {
  const unclassified = driftReport((replayed) => {
    replayed.mystery = "surprise";
  });

  assert.throws(
    () => build({ drift_report: unclassified }),
    (error) =>
      error instanceof ReplayDriftError && error.code === "DRIFT_UNCLASSIFIED",
  );
});

test("audit_export_test: a diverged run can still be exported, and says so", () => {
  const diverged = driftReport((replayed) => {
    replayed.outcome = "FAILED";
  });

  const bundle = build({ drift_report: diverged });

  assert.equal(bundle.drift_report.verdict, "DIVERGED");
  assert.equal(bundle.reconciliation.complete, true);
});

test("audit_export_test: a sealed export may not record missing entries", () => {
  const bundle = structuredClone(build());
  bundle.reconciliation.missing_count = 1;

  assert.throws(
    () => validateAuditExport(bundle),
    (error) => error instanceof AuditExportError && error.code === "EXPORT_INCOMPLETE",
  );
});

test("audit_export_test: hash coverage must match the present entries exactly", () => {
  const bundle = structuredClone(build());
  delete bundle.entry_hashes.artifacts["ART-2"];

  assert.throws(
    () => validateAuditExport(bundle),
    (error) =>
      error instanceof AuditExportError &&
      error.code === "EXPORT_HASH_COVERAGE_INCOMPLETE",
  );
});

test("audit_export_test: a tampered export is rejected by its own hash", () => {
  const bundle = structuredClone(build());
  bundle.command_count = 99;

  assert.throws(
    () => validateAuditExport(bundle),
    (error) => error instanceof AuditExportError && error.code === "EXPORT_HASH_MISMATCH",
  );
});

test("audit_export_test: a non-canonical field set is refused", () => {
  const bundle = structuredClone(build());
  delete bundle.plan_hash;

  assert.throws(
    () => validateAuditExport(bundle),
    (error) =>
      error instanceof AuditExportError && error.code === "EXPORT_FIELD_SET_INVALID",
  );
});

test("audit_export_test: an unknown section cannot be excluded", () => {
  assert.throws(
    () =>
      build({
        exclusions: [
          { id: "ART-2", reason: "CONFIDENTIAL_WITHHELD", section: "receipts" },
        ],
      }),
    (error) =>
      error instanceof AuditExportError && error.code === "EXPORT_SECTION_UNKNOWN",
  );
});

test("audit_export_test: the export is deterministic and content-addressed", () => {
  assert.deepEqual(build(), build());
});
