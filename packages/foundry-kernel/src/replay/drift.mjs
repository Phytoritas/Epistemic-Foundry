// W04 replay drift classification.
//
// Replaying a run almost never reproduces it byte for byte, and that is fine:
// timestamps move, durations differ, ids are freshly minted.  What matters is
// whether anything that changes the *meaning* of the run differed.  So every
// difference is classified into exactly one of two buckets and the verdict is
// derived from the semantic bucket alone.
//
// The separation is load-bearing, so it is enforced rather than trusted.  The
// volatile-field allowlist that makes a difference "strict" is closed and may
// never name a semantic field; a difference matching neither bucket is
// UNCLASSIFIED and fails the seal rather than defaulting to harmless.

import {
  canonicalizeSchedulerJson,
  sha256SchedulerJson,
} from "../scheduler/dag-scheduler.mjs";

/** Difference classes. UNCLASSIFIED is never a resting state. */
export const DRIFT_CLASSES = Object.freeze(["STRICT", "SEMANTIC", "UNCLASSIFIED"]);

/** Replay verdicts, strongest first. */
export const REPLAY_VERDICTS = Object.freeze([
  "REPRODUCIBLE",
  "REPRODUCIBLE_WITH_STRICT_DRIFT",
  "DIVERGED",
]);

/**
 * Fields whose value may differ without changing what happened.
 *
 * This list is the entire definition of "strict drift". It is closed on
 * purpose: adding a field here is a decision that the field carries no meaning,
 * and the semantic guard below refuses the decision if it is wrong.
 */
export const VOLATILE_FIELDS = Object.freeze([
  "created_at",
  "duration_ms",
  "ended_at",
  "generated_at",
  "hostname",
  "observed_at",
  "recorded_at",
  "started_at",
  "wall_clock_ms",
  "worker_id",
]);

/**
 * Fields that decide what the run concluded.
 *
 * A difference here is semantic no matter what, and no allowlist may cover it.
 */
export const SEMANTIC_FIELDS = Object.freeze([
  "artifact_ids",
  "artifact_hash",
  "checkpoint_hash",
  "effect_status",
  "expected_node_ids",
  "gate_decision_ids",
  "outcome",
  "pending_effect_ids",
  "replay_verified",
  "state_hash",
  "terminal_node_ids",
  "verdict",
]);

const SHA256 = /^sha256:[0-9a-f]{64}$/;

export class ReplayDriftError extends Error {
  constructor(code, message, details = null) {
    super(message);
    this.name = "ReplayDriftError";
    this.code = code;
    this.details = details === null ? null : structuredClone(details);
    Object.freeze(this);
  }
}

const fail = (code, message, details = null) => {
  throw new ReplayDriftError(code, message, details);
};

const isPlainObject = (value) =>
  typeof value === "object" &&
  value !== null &&
  !Array.isArray(value) &&
  Object.getPrototypeOf(value) === Object.prototype;

const requireObject = (value, label) => {
  if (!isPlainObject(value)) fail("DRIFT_INPUT_INVALID", `${label} must be an object`);
  return value;
};

const requireText = (value, label) => {
  if (typeof value !== "string" || value.trim() === "") {
    fail("DRIFT_INPUT_INVALID", `${label} must be a non-empty string`);
  }
  return value;
};

const leafName = (path) => {
  const segments = path.split(".");
  return segments[segments.length - 1];
};

function assertAllowlistIsSound() {
  const overlap = VOLATILE_FIELDS.filter((field) => SEMANTIC_FIELDS.includes(field));
  if (overlap.length > 0) {
    fail(
      "DRIFT_ALLOWLIST_UNSOUND",
      "a volatile field may never also be a semantic field",
      { fields: overlap.sort() },
    );
  }
}

assertAllowlistIsSound();

/**
 * Classify one differing path.
 *
 * The semantic list wins over the volatile list, so a field cannot be made
 * harmless by adding it to the allowlist; the pair is checked for overlap at
 * load, which makes that impossible rather than merely unlikely.
 */
export function classifyDifference(path) {
  const field = leafName(requireText(path, "path"));
  if (SEMANTIC_FIELDS.includes(field)) return "SEMANTIC";
  if (VOLATILE_FIELDS.includes(field)) return "STRICT";
  return "UNCLASSIFIED";
}

// A key present on one side only is reported as a difference at that path; it
// is never canonicalized, because `undefined` is not JSON data.
function collectDifferences(expected, actual, prefix, out) {
  const missingSide = expected === undefined || actual === undefined;
  if (
    !missingSide &&
    canonicalizeSchedulerJson(expected) === canonicalizeSchedulerJson(actual)
  ) {
    return;
  }
  if (!missingSide && isPlainObject(expected) && isPlainObject(actual)) {
    for (const key of [...new Set([...Object.keys(expected), ...Object.keys(actual)])].sort()) {
      collectDifferences(
        Object.hasOwn(expected, key) ? expected[key] : undefined,
        Object.hasOwn(actual, key) ? actual[key] : undefined,
        prefix === "" ? key : `${prefix}.${key}`,
        out,
      );
    }
    return;
  }
  out.push({
    actual: actual === undefined ? null : structuredClone(actual),
    expected: expected === undefined ? null : structuredClone(expected),
    path: prefix === "" ? "$" : prefix,
    present_in_actual: actual !== undefined,
    present_in_expected: expected !== undefined,
  });
}

/** Every leaf path at which two records differ, in deterministic order. */
export function differences(expected, actual) {
  const out = [];
  collectDifferences(
    requireObject(expected, "expected"),
    requireObject(actual, "actual"),
    "",
    out,
  );
  return out.sort((left, right) => (left.path < right.path ? -1 : left.path > right.path ? 1 : 0));
}

/**
 * Compare an original run record with its replay and classify every difference.
 *
 * The verdict is a function of the semantic bucket only: strict drift never
 * downgrades it, and an unclassified difference blocks a verdict entirely
 * rather than being counted as either.
 */
export function compareReplay({ original, replayed, run_id: runId }) {
  requireObject(original, "original");
  requireObject(replayed, "replayed");
  requireText(runId, "run_id");

  const found = differences(original, replayed);
  const strict = [];
  const semantic = [];
  const unclassified = [];
  for (const difference of found) {
    const driftClass = classifyDifference(difference.path);
    const record = Object.freeze({ ...difference, drift_class: driftClass });
    if (driftClass === "SEMANTIC") semantic.push(record);
    else if (driftClass === "STRICT") strict.push(record);
    else unclassified.push(record);
  }
  let verdict;
  if (semantic.length > 0) verdict = "DIVERGED";
  else if (strict.length > 0) verdict = "REPRODUCIBLE_WITH_STRICT_DRIFT";
  else verdict = "REPRODUCIBLE";

  const report = {
    difference_count: found.length,
    run_id: runId,
    semantic_difference_count: semantic.length,
    semantic_differences: semantic,
    strict_difference_count: strict.length,
    strict_differences: strict,
    unclassified_difference_count: unclassified.length,
    unclassified_differences: unclassified,
    verdict,
  };
  report.report_hash = sha256SchedulerJson(report);
  return Object.freeze(report);
}

/**
 * Seal a drift report, refusing one that cannot stand on its own.
 *
 * An unclassified difference is refused here rather than at comparison time so
 * a caller can inspect what could not be typed before deciding what to do.
 */
export function sealDriftReport(report) {
  requireObject(report, "drift report");
  const expectedKeys = [
    "difference_count",
    "report_hash",
    "run_id",
    "semantic_difference_count",
    "semantic_differences",
    "strict_difference_count",
    "strict_differences",
    "unclassified_difference_count",
    "unclassified_differences",
    "verdict",
  ];
  const keys = Object.keys(report).sort();
  if (keys.join(" ") !== expectedKeys.join(" ")) {
    fail("DRIFT_FIELD_SET_INVALID", "drift report field set is not canonical", {
      missing: expectedKeys.filter((key) => !keys.includes(key)),
      unknown: keys.filter((key) => !expectedKeys.includes(key)),
    });
  }
  if (!REPLAY_VERDICTS.includes(report.verdict)) {
    fail("DRIFT_VERDICT_INVALID", "verdict is not canonical", {
      verdict: report.verdict,
    });
  }
  const expectedRecordKeys = [
    "actual",
    "drift_class",
    "expected",
    "path",
    "present_in_actual",
    "present_in_expected",
  ];
  const buckets = [
    ["semantic_differences", "SEMANTIC"],
    ["strict_differences", "STRICT"],
    ["unclassified_differences", "UNCLASSIFIED"],
  ];
  for (const [bucket, bucketClass] of buckets) {
    const records = report[bucket];
    if (!Array.isArray(records)) {
      fail("DRIFT_INPUT_INVALID", `${bucket} must be an array`);
    }
    for (const [index, record] of records.entries()) {
      requireObject(record, `${bucket}[${index}]`);
      const recordKeys = Object.keys(record).sort();
      if (recordKeys.join(" ") !== expectedRecordKeys.join(" ")) {
        fail("DRIFT_FIELD_SET_INVALID", "difference record field set is not canonical", {
          bucket,
          index,
          missing: expectedRecordKeys.filter((key) => !recordKeys.includes(key)),
          unknown: recordKeys.filter((key) => !expectedRecordKeys.includes(key)),
        });
      }
      requireText(record.path, `${bucket}[${index}].path`);
      for (const flag of ["present_in_actual", "present_in_expected"]) {
        if (typeof record[flag] !== "boolean") {
          fail("DRIFT_INPUT_INVALID", `${bucket}[${index}].${flag} must be a boolean`);
        }
      }

      const derivedClass = classifyDifference(record.path);
      const classDetails = {
        bucket: bucketClass,
        declared: record.drift_class,
        derived: derivedClass,
        path: record.path,
      };
      if (derivedClass === "UNCLASSIFIED") {
        fail(
          "DRIFT_UNCLASSIFIED",
          "every replay difference must be typed strict or semantic before sealing",
          classDetails,
        );
      }
      if (record.drift_class !== derivedClass || derivedClass !== bucketClass) {
        if (bucketClass === "STRICT" && derivedClass === "SEMANTIC") {
          fail(
            "DRIFT_SEMANTIC_MISFILED",
            "a semantic field was filed as strict drift",
            classDetails,
          );
        }
        fail(
          "DRIFT_CLASS_MISMATCH",
          "a replay difference class does not match its bucket",
          classDetails,
        );
      }
    }
  }
  const semanticCount = report.semantic_differences.length;
  const strictCount = report.strict_differences.length;
  if (
    semanticCount !== report.semantic_difference_count ||
    strictCount !== report.strict_difference_count ||
    report.unclassified_differences.length !== report.unclassified_difference_count ||
    semanticCount + strictCount + report.unclassified_difference_count !==
      report.difference_count
  ) {
    fail("DRIFT_COUNT_MISMATCH", "the drift counts do not reconcile with the records");
  }
  const expectedVerdict =
    semanticCount > 0 ? "DIVERGED" : strictCount > 0 ? "REPRODUCIBLE_WITH_STRICT_DRIFT" : "REPRODUCIBLE";
  if (report.verdict !== expectedVerdict) {
    fail("DRIFT_VERDICT_MISMATCH", "the verdict does not follow from the semantic bucket", {
      declared: report.verdict,
      derived: expectedVerdict,
    });
  }
  const { report_hash: asserted, ...content } = report;
  if (!SHA256.test(String(asserted))) {
    fail("DRIFT_FIELD_SET_INVALID", "report_hash must be a sha256 id");
  }
  if (asserted !== sha256SchedulerJson(content)) {
    fail("DRIFT_HASH_MISMATCH", "report_hash does not match canonical content");
  }
  return Object.freeze(structuredClone(report));
}
