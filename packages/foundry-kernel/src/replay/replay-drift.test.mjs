// replay_drift_test — strict and semantic drift stay separated.
//
// Exit criterion under test: "strict/semantic drift separated".  Every
// difference is typed into exactly one bucket, the verdict follows from the
// semantic bucket alone, an unclassified difference blocks the seal, and the
// allowlist that makes a difference harmless can never cover a semantic field.

import assert from "node:assert/strict";
import test from "node:test";

import {
  DRIFT_CLASSES,
  REPLAY_VERDICTS,
  ReplayDriftError,
  SEMANTIC_FIELDS,
  VOLATILE_FIELDS,
  classifyDifference,
  compareReplay,
  differences,
  sealDriftReport,
} from "./drift.mjs";

const RUN = "RUN-1";

function record(overrides = {}) {
  return {
    checkpoint: {
      checkpoint_hash: `sha256:${"a".repeat(64)}`,
      created_at: "2026-08-01T15:00:00Z",
      replay_verified: true,
      state_hash: `sha256:${"b".repeat(64)}`,
      terminal_node_ids: ["ingest", "probe"],
    },
    metrics: { duration_ms: 1200, worker_id: "worker-a" },
    outcome: "SUCCEEDED",
    ...overrides,
  };
}

function compare(mutate) {
  const original = record();
  const replayed = record();
  mutate(replayed);
  return compareReplay({ original, replayed, run_id: RUN });
}

test("replay_drift_test: an exact replay is reproducible with no differences", () => {
  const report = compareReplay({ original: record(), replayed: record(), run_id: RUN });

  assert.equal(report.verdict, "REPRODUCIBLE");
  assert.equal(report.difference_count, 0);
  assert.deepEqual(report.strict_differences, []);
  assert.deepEqual(report.semantic_differences, []);
  assert.equal(sealDriftReport(report).verdict, "REPRODUCIBLE");
});

test("replay_drift_test: a moved timestamp is strict drift, not divergence", () => {
  const report = compare((replayed) => {
    replayed.checkpoint.created_at = "2026-08-02T09:00:00Z";
  });

  assert.equal(report.verdict, "REPRODUCIBLE_WITH_STRICT_DRIFT");
  assert.equal(report.strict_difference_count, 1);
  assert.equal(report.semantic_difference_count, 0);
  assert.equal(report.strict_differences[0].path, "checkpoint.created_at");
  assert.equal(report.strict_differences[0].drift_class, "STRICT");
});

test("replay_drift_test: a different duration and worker are strict drift", () => {
  const report = compare((replayed) => {
    replayed.metrics.duration_ms = 4800;
    replayed.metrics.worker_id = "worker-b";
  });

  assert.equal(report.verdict, "REPRODUCIBLE_WITH_STRICT_DRIFT");
  assert.equal(report.strict_difference_count, 2);
  assert.deepEqual(
    report.strict_differences.map((entry) => entry.path),
    ["metrics.duration_ms", "metrics.worker_id"],
  );
});

test("replay_drift_test: a changed state hash is semantic divergence", () => {
  const report = compare((replayed) => {
    replayed.checkpoint.state_hash = `sha256:${"c".repeat(64)}`;
  });

  assert.equal(report.verdict, "DIVERGED");
  assert.equal(report.semantic_difference_count, 1);
  assert.equal(report.semantic_differences[0].path, "checkpoint.state_hash");
});

test("replay_drift_test: strict drift never downgrades a clean semantic result", () => {
  const report = compare((replayed) => {
    replayed.checkpoint.created_at = "2026-08-02T09:00:00Z";
    replayed.metrics.duration_ms = 9;
  });

  assert.equal(report.verdict, "REPRODUCIBLE_WITH_STRICT_DRIFT");
  assert.equal(report.semantic_difference_count, 0);
});

test("replay_drift_test: one semantic difference outweighs any amount of strict drift", () => {
  const report = compare((replayed) => {
    replayed.checkpoint.created_at = "2026-08-02T09:00:00Z";
    replayed.metrics.duration_ms = 9;
    replayed.metrics.worker_id = "worker-z";
    replayed.outcome = "FAILED";
  });

  assert.equal(report.verdict, "DIVERGED");
  assert.equal(report.strict_difference_count, 3);
  assert.equal(report.semantic_difference_count, 1);
});

test("replay_drift_test: every semantic field is actually treated as semantic", () => {
  for (const field of SEMANTIC_FIELDS) {
    assert.equal(classifyDifference(`section.${field}`), "SEMANTIC", field);
  }
});

test("replay_drift_test: every volatile field is actually treated as strict", () => {
  for (const field of VOLATILE_FIELDS) {
    assert.equal(classifyDifference(`section.${field}`), "STRICT", field);
  }
});

test("replay_drift_test: the two field lists cannot overlap", () => {
  const overlap = VOLATILE_FIELDS.filter((field) => SEMANTIC_FIELDS.includes(field));

  assert.deepEqual(overlap, []);
});

test("replay_drift_test: an unrecognised field is unclassified, not assumed harmless", () => {
  const report = compare((replayed) => {
    replayed.mystery_field = "surprise";
  });

  assert.equal(report.unclassified_difference_count, 1);
  assert.equal(report.unclassified_differences[0].drift_class, "UNCLASSIFIED");
  assert.deepEqual(DRIFT_CLASSES, ["STRICT", "SEMANTIC", "UNCLASSIFIED"]);
});

test("replay_drift_test: an unclassified difference blocks the seal", () => {
  const report = compare((replayed) => {
    replayed.mystery_field = "surprise";
  });

  assert.throws(
    () => sealDriftReport(report),
    (error) => error instanceof ReplayDriftError && error.code === "DRIFT_UNCLASSIFIED",
  );
});

test("replay_drift_test: a semantic field filed as strict is refused", () => {
  const report = compare((replayed) => {
    replayed.checkpoint.state_hash = `sha256:${"c".repeat(64)}`;
  });
  const forged = structuredClone(report);
  forged.strict_differences = [
    { ...forged.semantic_differences[0], drift_class: "STRICT" },
  ];
  forged.semantic_differences = [];
  forged.strict_difference_count = 1;
  forged.semantic_difference_count = 0;
  forged.verdict = "REPRODUCIBLE_WITH_STRICT_DRIFT";

  assert.throws(
    () => sealDriftReport(forged),
    (error) =>
      error instanceof ReplayDriftError && error.code === "DRIFT_SEMANTIC_MISFILED",
  );
});

test("replay_drift_test: a verdict that does not follow from the buckets is refused", () => {
  const report = compare((replayed) => {
    replayed.outcome = "FAILED";
  });
  const forged = { ...structuredClone(report), verdict: "REPRODUCIBLE" };

  assert.throws(
    () => sealDriftReport(forged),
    (error) =>
      error instanceof ReplayDriftError && error.code === "DRIFT_VERDICT_MISMATCH",
  );
});

test("replay_drift_test: counts must reconcile with the records", () => {
  const report = compare((replayed) => {
    replayed.metrics.duration_ms = 9;
  });
  const forged = { ...structuredClone(report), strict_difference_count: 5 };

  assert.throws(
    () => sealDriftReport(forged),
    (error) => error instanceof ReplayDriftError && error.code === "DRIFT_COUNT_MISMATCH",
  );
});

test("replay_drift_test: a tampered report is rejected by its own hash", () => {
  const report = compare((replayed) => {
    replayed.metrics.duration_ms = 9;
  });
  const forged = { ...structuredClone(report), run_id: "RUN-other" };

  assert.throws(
    () => sealDriftReport(forged),
    (error) => error instanceof ReplayDriftError && error.code === "DRIFT_HASH_MISMATCH",
  );
});

test("replay_drift_test: an added or removed field is reported with both sides", () => {
  const added = compare((replayed) => {
    replayed.checkpoint.gate_decision_ids = ["G01"];
  });

  const entry = added.semantic_differences[0];
  assert.equal(entry.path, "checkpoint.gate_decision_ids");
  assert.equal(entry.present_in_expected, false);
  assert.equal(entry.present_in_actual, true);
  assert.equal(entry.expected, null);
});

test("replay_drift_test: differences are reported in deterministic path order", () => {
  const found = differences(
    { a: 1, b: { y: 1, x: 1 }, c: 1 },
    { a: 2, b: { y: 2, x: 2 }, c: 2 },
  );

  assert.deepEqual(
    found.map((entry) => entry.path),
    ["a", "b.x", "b.y", "c"],
  );
});

test("replay_drift_test: the verdict vocabulary is closed and ordered", () => {
  assert.deepEqual(REPLAY_VERDICTS, [
    "REPRODUCIBLE",
    "REPRODUCIBLE_WITH_STRICT_DRIFT",
    "DIVERGED",
  ]);
});

test("replay_drift_test: a non-canonical verdict is refused", () => {
  const report = compare((replayed) => {
    replayed.metrics.duration_ms = 9;
  });
  const forged = { ...structuredClone(report), verdict: "PROBABLY_FINE" };

  assert.throws(
    () => sealDriftReport(forged),
    (error) => error instanceof ReplayDriftError && error.code === "DRIFT_VERDICT_INVALID",
  );
});

test("replay_drift_test: the report is deterministic and content-addressed", () => {
  const first = compare((replayed) => {
    replayed.metrics.duration_ms = 9;
  });
  const second = compare((replayed) => {
    replayed.metrics.duration_ms = 9;
  });

  assert.deepEqual(first, second);
  assert.match(first.report_hash, /^sha256:[0-9a-f]{64}$/u);
});
