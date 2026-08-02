// Provenance and receipt integrity for the OpenAPI-derived surface.
//
// Three claims are checked here rather than asserted in prose:
//   1. every digest this component emits is re-derivable from the artefact it
//      describes, so a receipt cannot drift from its subject unnoticed;
//   2. the committed generated client is byte-identical to a fresh generation
//      from the same document, so it cannot have been hand-edited;
//   3. the generated tree names the generator and the exact document bytes it
//      came from, so any artefact can be traced back to its declaring source.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  CANONICAL_OPENAPI_PATH,
  PACKAGED_OPENAPI_PATH,
  REPOSITORY_ROOT,
  bindServerSurface,
  bytesSha256,
  canonicalJson,
  canonicalJsonSha256,
  loadRouteTable,
  readRepositoryDocument,
  recomputeCoverageSha256,
} from "./index.mjs";

const TABLE = loadRouteTable();
const GENERATOR = "artifacts/work_packages/U01/attempts/0001/generate_client.py";
const GENERATED_DIRECTORY = "web/src/generated/ui-client";
const GENERATED_FILES = ["index.d.ts", "index.mjs", "route-manifest.json"];

/** Run the generator, refusing to pass if no interpreter could run it. */
const runGenerator = (args) => {
  const attempts = [
    ["uv", ["run", "--locked", "python", "-B", GENERATOR, ...args]],
    ["python", ["-B", GENERATOR, ...args]],
  ];
  const failures = [];
  for (const [command, argv] of attempts) {
    const result = spawnSync(command, argv, { cwd: REPOSITORY_ROOT, encoding: "utf8" });
    if (result.error === undefined && result.status !== null) {
      return { argv: [command, ...argv], ...result };
    }
    failures.push(`${command}: ${result.error?.message ?? "no exit status"}`);
  }
  assert.fail(`the client generator could not be run: ${failures.join("; ")}`);
  return null;
};

test("the bound document digest matches the bytes on disk", () => {
  const source = readRepositoryDocument(CANONICAL_OPENAPI_PATH);
  assert.equal(TABLE.documentSha256, source.sha256);
  assert.equal(TABLE.documentSha256, bytesSha256(fs.readFileSync(
    path.resolve(REPOSITORY_ROOT, CANONICAL_OPENAPI_PATH),
  )));
});

test("the packaged canonical projection is byte-identical to the source authority", () => {
  // `src/epistemic_foundry/contracts/registry.py` treats repository-root
  // `openapi/` as the source authority and the packaged copy as a build-time
  // projection of it.  If those two ever diverge, the Node surface and the
  // Python runtime would be serving different contracts.
  const source = readRepositoryDocument(CANONICAL_OPENAPI_PATH);
  const packaged = readRepositoryDocument(PACKAGED_OPENAPI_PATH);
  assert.equal(packaged.sha256, source.sha256);
});

test("the route table digest is re-derivable from the route table", () => {
  const { routeTableSha256, ...preimage } = TABLE;
  assert.equal(
    canonicalJsonSha256(JSON.parse(JSON.stringify(preimage))),
    routeTableSha256,
  );
  assert.match(routeTableSha256, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(loadRouteTable().routeTableSha256, routeTableSha256);
});

test("the coverage record digest is re-derivable from the record", () => {
  const handlers = Object.fromEntries(
    TABLE.operationIds.slice(0, 5).map((name) => [name, () => name]),
  );
  const { coverage } = bindServerSurface(TABLE, handlers);
  assert.equal(recomputeCoverageSha256(coverage), coverage.coverageSha256);
  assert.match(coverage.coverageSha256, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(coverage.documentSha256, TABLE.documentSha256);
  assert.equal(coverage.routeTableSha256, TABLE.routeTableSha256);
});

test("changing any field of a coverage record changes its digest", () => {
  const { coverage } = bindServerSurface(TABLE, { getRun: () => null });
  const { coverageSha256, ...preimage } = coverage;
  const perturbations = [
    { ...preimage, boundOperationIds: ["getRunEvents"] },
    { ...preimage, coverageState: "COMPLETE" },
    { ...preimage, declaredOperationCount: preimage.declaredOperationCount + 1 },
    { ...preimage, documentSha256: `sha256:${"0".repeat(64)}` },
    { ...preimage, missingOperationCount: 0 },
  ];
  for (const perturbed of perturbations) {
    assert.notEqual(
      canonicalJsonSha256(JSON.parse(JSON.stringify(perturbed))),
      coverageSha256,
    );
  }
});

test("canonical JSON is key-order independent and whitespace-free", () => {
  assert.equal(canonicalJson({ b: 1, a: 2 }), canonicalJson({ a: 2, b: 1 }));
  assert.equal(canonicalJson({ b: [1, { d: 4, c: 3 }], a: null }), '{"a":null,"b":[1,{"c":3,"d":4}]}');
  assert.notEqual(canonicalJson([1, 2]), canonicalJson([2, 1]));
  assert.throws(() => canonicalJson({ a: Number.NaN }), /non-finite/u);
  assert.equal(bytesSha256(""), `sha256:${"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}`);
});

test("every generated file names its generator and its source document bytes", () => {
  for (const name of GENERATED_FILES) {
    const generated = readRepositoryDocument(`${GENERATED_DIRECTORY}/${name}`);
    assert.ok(generated.text.includes(GENERATOR), `${name} does not name its generator`);
    assert.ok(
      generated.text.includes(TABLE.documentSha256),
      `${name} does not carry the source document digest`,
    );
    assert.ok(
      generated.text.includes(TABLE.routeTableSha256),
      `${name} does not carry the route table digest`,
    );
    assert.ok(
      generated.text.includes(CANONICAL_OPENAPI_PATH),
      `${name} does not name its source document`,
    );
  }
});

test("the generated route manifest agrees with the Node projection field for field", () => {
  const manifest = JSON.parse(
    readRepositoryDocument(`${GENERATED_DIRECTORY}/route-manifest.json`).text,
  );
  assert.equal(manifest.generator, GENERATOR);
  assert.deepEqual(manifest.routeTable, JSON.parse(JSON.stringify(TABLE)));
  assert.equal(manifest.routeTable.routeTableSha256, TABLE.routeTableSha256);
});

test("regenerating the client reproduces the committed bytes exactly", () => {
  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "u01-client-parity-"));
  try {
    const generated = runGenerator(["--out-dir", outDir]);
    assert.equal(
      generated.status,
      0,
      `generator failed: ${generated.stdout}\n${generated.stderr}`,
    );
    const produced = fs.readdirSync(outDir).sort();
    assert.deepEqual(produced, GENERATED_FILES);
    for (const name of GENERATED_FILES) {
      const fresh = fs.readFileSync(path.join(outDir, name));
      const committed = fs.readFileSync(
        path.resolve(REPOSITORY_ROOT, GENERATED_DIRECTORY, name),
      );
      assert.equal(
        bytesSha256(fresh),
        bytesSha256(committed),
        `${name} differs from a fresh generation; the committed file was edited by hand`,
      );
      assert.ok(fresh.equals(committed), `${name} is not byte-identical`);
    }
  } finally {
    fs.rmSync(outDir, { force: true, recursive: true });
  }
});

test("the generator refuses the committed tree when it drifts", () => {
  const clean = runGenerator(["--check"]);
  assert.equal(clean.status, 0, `parity check failed: ${clean.stdout}\n${clean.stderr}`);
  const report = JSON.parse(clean.stdout);
  assert.equal(report.status, "PASS");
  assert.deepEqual(report.drift, []);
  assert.deepEqual(report.files, GENERATED_FILES);

  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "u01-client-drift-"));
  try {
    fs.writeFileSync(path.join(outDir, "index.mjs"), "// hand-edited\n");
    const drifted = runGenerator(["--check", "--out-dir", outDir]);
    assert.equal(drifted.status, 1, "a hand-edited tree passed the parity check");
    const driftReport = JSON.parse(drifted.stderr);
    assert.equal(driftReport.status, "FAIL");
    assert.deepEqual(
      driftReport.drift.map((entry) => entry.file).sort(),
      GENERATED_FILES,
    );
    assert.equal(
      driftReport.drift.find((entry) => entry.file === "index.mjs").reason,
      "BYTES_DIFFER",
    );
  } finally {
    fs.rmSync(outDir, { force: true, recursive: true });
  }
});

test("no product module reads a clock or a random source", () => {
  const productModules = [
    "canonical-hash.mjs",
    "index.mjs",
    "openapi-source.mjs",
    "route-table.mjs",
    "server-surface.mjs",
    "surface-errors.mjs",
    "yaml-subset.mjs",
  ];
  const sources = productModules.map((name) =>
    readRepositoryDocument(`packages/ui-api/src/openapi/${name}`),
  );
  sources.push(readRepositoryDocument(`${GENERATED_DIRECTORY}/index.mjs`));
  for (const source of sources) {
    for (const forbidden of ["Date.now", "Math.random", "new Date(", "process.env"]) {
      assert.ok(
        !source.text.includes(forbidden),
        `${source.relativePath} reads ${forbidden} on a product path`,
      );
    }
  }
});
