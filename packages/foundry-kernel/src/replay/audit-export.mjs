// W04 audit export bundling.
//
// An audit export is complete when someone else can re-verify the run from it
// alone.  "Complete" is therefore a reconciliation, not a claim: every id the
// run references must be present or carry a typed exclusion reason, every entry
// present must be reachable from the run, and the counts must add up exactly.
//
// Silence is the failure this guards against.  An artifact that is simply
// absent from a bundle is indistinguishable from one that was deliberately
// withheld, so an omission without a reason fails the seal.

import { sha256SchedulerJson } from "../scheduler/dag-scheduler.mjs";
import { sealDriftReport } from "./drift.mjs";

/** The artifact classes an audit export must account for. */
export const EXPORT_SECTIONS = Object.freeze([
  "artifacts",
  "checkpoints",
  "effect_receipts",
  "gate_decisions",
]);

/** Reasons an entry may be referenced but absent. Silence is not one of them. */
export const EXCLUSION_REASONS = Object.freeze([
  "CONFIDENTIAL_WITHHELD",
  "EXTERNAL_SYSTEM_OWNED",
  "SUPERSEDED_REVISION",
]);

const SHA256 = /^sha256:[0-9a-f]{64}$/;

export class AuditExportError extends Error {
  constructor(code, message, details = null) {
    super(message);
    this.name = "AuditExportError";
    this.code = code;
    this.details = details === null ? null : structuredClone(details);
    Object.freeze(this);
  }
}

const fail = (code, message, details = null) => {
  throw new AuditExportError(code, message, details);
};

const isPlainObject = (value) =>
  typeof value === "object" &&
  value !== null &&
  !Array.isArray(value) &&
  Object.getPrototypeOf(value) === Object.prototype;

const requireObject = (value, label) => {
  if (!isPlainObject(value)) fail("EXPORT_INPUT_INVALID", `${label} must be an object`);
  return value;
};

const requireText = (value, label) => {
  if (typeof value !== "string" || value.trim() === "") {
    fail("EXPORT_INPUT_INVALID", `${label} must be a non-empty string`);
  }
  return value;
};

const requireIdArray = (value, label) => {
  if (!Array.isArray(value)) fail("EXPORT_INPUT_INVALID", `${label} must be an array`);
  const ids = value.map((entry, index) => requireText(entry, `${label}[${index}]`));
  if (new Set(ids).size !== ids.length) {
    fail("EXPORT_INPUT_INVALID", `${label} must not contain duplicates`);
  }
  return [...ids].sort();
};

function sectionEntries(section, entries) {
  if (!Array.isArray(entries)) {
    fail("EXPORT_INPUT_INVALID", `${section} entries must be an array`);
  }
  const byId = new Map();
  for (const [index, entry] of entries.entries()) {
    const record = requireObject(entry, `${section}[${index}]`);
    const id = requireText(record.id, `${section}[${index}].id`);
    const contentHash = requireText(record.content_hash, `${section}[${index}].content_hash`);
    if (!SHA256.test(contentHash)) {
      fail("EXPORT_CONTENT_HASH_INVALID", `${section}[${index}].content_hash must be a sha256 id`);
    }
    if (byId.has(id)) {
      fail("EXPORT_DUPLICATE_ENTRY", `${section} carries ${id} twice`, { id, section });
    }
    byId.set(id, { content_hash: contentHash, id });
  }
  return byId;
}

function exclusionIndex(exclusions) {
  if (!Array.isArray(exclusions)) {
    fail("EXPORT_INPUT_INVALID", "exclusions must be an array");
  }
  const byId = new Map();
  for (const [index, entry] of exclusions.entries()) {
    const record = requireObject(entry, `exclusions[${index}]`);
    const id = requireText(record.id, `exclusions[${index}].id`);
    const section = requireText(record.section, `exclusions[${index}].section`);
    const reason = requireText(record.reason, `exclusions[${index}].reason`);
    if (!EXPORT_SECTIONS.includes(section)) {
      fail("EXPORT_SECTION_UNKNOWN", `exclusions[${index}].section is not canonical`, {
        section,
      });
    }
    if (!EXCLUSION_REASONS.includes(reason)) {
      fail("EXPORT_EXCLUSION_REASON_INVALID", `${id} carries a non-canonical reason`, {
        reason,
      });
    }
    if (byId.has(id)) {
      fail("EXPORT_DUPLICATE_ENTRY", `${id} is excluded twice`, { id });
    }
    byId.set(id, { id, reason, section });
  }
  return byId;
}

/**
 * Reconcile what the run references against what the bundle carries.
 *
 * Returned rather than thrown so a caller sees the whole picture at once: the
 * sealing path turns any missing or orphaned id into a failure.
 */
export function reconcileExport({ referenced, bundled, exclusions = [] }) {
  requireObject(referenced, "referenced");
  requireObject(bundled, "bundled");
  const excluded = exclusionIndex(exclusions);
  const sections = {};
  let missingTotal = 0;
  let orphanTotal = 0;
  let presentTotal = 0;
  let referencedTotal = 0;
  for (const section of EXPORT_SECTIONS) {
    const wanted = requireIdArray(referenced[section] ?? [], `referenced.${section}`);
    const present = sectionEntries(section, bundled[section] ?? []);
    const excludedHere = [...excluded.values()]
      .filter((entry) => entry.section === section)
      .map((entry) => entry.id);
    const missing = wanted
      .filter((id) => !present.has(id) && !excludedHere.includes(id))
      .sort();
    const orphaned = [...present.keys()].filter((id) => !wanted.includes(id)).sort();
    const bothPresentAndExcluded = excludedHere.filter((id) => present.has(id)).sort();
    if (bothPresentAndExcluded.length > 0) {
      fail(
        "EXPORT_EXCLUSION_CONTRADICTED",
        `${section} carries entries it also declares excluded`,
        { ids: bothPresentAndExcluded, section },
      );
    }
    const unreferencedExclusions = excludedHere.filter((id) => !wanted.includes(id)).sort();
    if (unreferencedExclusions.length > 0) {
      fail(
        "EXPORT_EXCLUSION_UNREFERENCED",
        `${section} excludes entries the run never referenced`,
        { ids: unreferencedExclusions, section },
      );
    }
    sections[section] = {
      excluded_ids: [...excludedHere].sort(),
      missing_ids: missing,
      orphaned_ids: orphaned,
      present_ids: [...present.keys()].sort(),
      referenced_ids: wanted,
    };
    missingTotal += missing.length;
    orphanTotal += orphaned.length;
    presentTotal += present.size;
    referencedTotal += wanted.length;
  }
  return {
    complete: missingTotal === 0 && orphanTotal === 0,
    excluded_count: excluded.size,
    missing_count: missingTotal,
    orphaned_count: orphanTotal,
    present_count: presentTotal,
    referenced_count: referencedTotal,
    sections,
  };
}

/**
 * Build an audit export bundle for one run.
 *
 * The drift report is sealed as part of the bundle rather than attached to it:
 * an export that carries an unsealed or unclassified drift report would let a
 * reader believe the run was checked when it was not.
 */
export function buildAuditExport({
  run_id: runId,
  plan_hash: planHash,
  command_count: commandCount,
  drift_report: driftReport,
  referenced,
  bundled,
  exclusions = [],
  created_at: createdAt,
}) {
  requireText(runId, "run_id");
  requireText(planHash, "plan_hash");
  requireText(createdAt, "created_at");
  if (!SHA256.test(planHash)) {
    fail("EXPORT_INPUT_INVALID", "plan_hash must be a sha256 id");
  }
  if (!Number.isSafeInteger(commandCount) || commandCount < 0) {
    fail("EXPORT_INPUT_INVALID", "command_count must be a non-negative integer");
  }
  const drift = sealDriftReport(driftReport);
  if (drift.run_id !== runId) {
    fail("EXPORT_RUN_MISMATCH", "the drift report belongs to a different run", {
      drift_run_id: drift.run_id,
      run_id: runId,
    });
  }
  const reconciliation = reconcileExport({ bundled, exclusions, referenced });
  if (reconciliation.missing_count > 0) {
    fail("EXPORT_INCOMPLETE", "the bundle omits entries the run references without a reason", {
      sections: Object.fromEntries(
        Object.entries(reconciliation.sections)
          .filter(([, value]) => value.missing_ids.length > 0)
          .map(([section, value]) => [section, value.missing_ids]),
      ),
    });
  }
  if (reconciliation.orphaned_count > 0) {
    fail("EXPORT_ORPHANED", "the bundle carries entries the run never referenced", {
      sections: Object.fromEntries(
        Object.entries(reconciliation.sections)
          .filter(([, value]) => value.orphaned_ids.length > 0)
          .map(([section, value]) => [section, value.orphaned_ids]),
      ),
    });
  }
  const content = {
    command_count: commandCount,
    created_at: createdAt,
    drift_report: drift,
    entry_hashes: Object.fromEntries(
      EXPORT_SECTIONS.map((section) => [
        section,
        Object.fromEntries(
          [...sectionEntries(section, bundled[section] ?? []).values()]
            .sort((left, right) => (left.id < right.id ? -1 : 1))
            .map((entry) => [entry.id, entry.content_hash]),
        ),
      ]),
    ),
    exclusions: [...exclusionIndex(exclusions).values()].sort((left, right) =>
      left.id < right.id ? -1 : 1,
    ),
    plan_hash: planHash,
    reconciliation,
    run_id: runId,
  };
  const bundle = {
    ...content,
    export_hash: sha256SchedulerJson(content),
  };
  return Object.freeze(structuredClone(bundle));
}

/** Validate a stored audit export: shape, reconciliation, and self-hash. */
export function validateAuditExport(bundle) {
  requireObject(bundle, "audit export");
  const expectedKeys = [
    "command_count",
    "created_at",
    "drift_report",
    "entry_hashes",
    "exclusions",
    "export_hash",
    "plan_hash",
    "reconciliation",
    "run_id",
  ];
  const keys = Object.keys(bundle).sort();
  if (keys.join(" ") !== expectedKeys.join(" ")) {
    fail("EXPORT_FIELD_SET_INVALID", "audit export field set is not canonical", {
      missing: expectedKeys.filter((key) => !keys.includes(key)),
      unknown: keys.filter((key) => !expectedKeys.includes(key)),
    });
  }
  sealDriftReport(bundle.drift_report);
  const reconciliation = requireObject(bundle.reconciliation, "reconciliation");
  if (reconciliation.missing_count > 0 || reconciliation.orphaned_count > 0) {
    fail(
      "EXPORT_INCOMPLETE",
      "a sealed export may not record missing or orphaned entries",
      {
        missing_count: reconciliation.missing_count,
        orphaned_count: reconciliation.orphaned_count,
      },
    );
  }
  if (reconciliation.complete !== true) {
    fail("EXPORT_INCOMPLETE", "a sealed export must reconcile as complete");
  }
  let hashed = 0;
  for (const section of EXPORT_SECTIONS) {
    const entries = requireObject(bundle.entry_hashes[section] ?? {}, `entry_hashes.${section}`);
    const presentIds = reconciliation.sections[section].present_ids;
    if (Object.keys(entries).sort().join(" ") !== [...presentIds].sort().join(" ")) {
      fail(
        "EXPORT_HASH_COVERAGE_INCOMPLETE",
        `${section} content hashes do not cover exactly the present entries`,
        { section },
      );
    }
    for (const [id, contentHash] of Object.entries(entries)) {
      if (!SHA256.test(String(contentHash))) {
        fail("EXPORT_CONTENT_HASH_INVALID", `${section}.${id} is not a sha256 id`);
      }
      hashed += 1;
    }
  }
  if (hashed !== reconciliation.present_count) {
    fail(
      "EXPORT_HASH_COVERAGE_INCOMPLETE",
      "every bundled entry must carry a content hash",
      { hashed, present_count: reconciliation.present_count },
    );
  }
  const { export_hash: asserted, ...content } = bundle;
  if (!SHA256.test(String(asserted))) {
    fail("EXPORT_FIELD_SET_INVALID", "export_hash must be a sha256 id");
  }
  if (asserted !== sha256SchedulerJson(content)) {
    fail("EXPORT_HASH_MISMATCH", "export_hash does not match canonical content");
  }
  return Object.freeze(structuredClone(bundle));
}
