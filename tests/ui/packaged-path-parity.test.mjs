/**
 * U04 packaged_ui_parity_test.
 *
 * The U-phase packaged-path parity gate asserts that the console the package
 * ships behaves identically whether a view is reached through the source path a
 * Vite build compiles (`*-view.mjs`, `app/*.mjs`) or through the packaged export
 * surface the console imports (the `index.mjs` barrels).  Concretely:
 *
 *   * export parity - every packaged barrel re-exports exactly the source
 *     implementations, never a hand-written packaged fork, and adds nothing
 *     that traces to no source module;
 *   * behavioural parity - for every U02/U03 view, the record and the rendered
 *     HTML built through the packaged path are byte-for-byte identical to the
 *     ones built through the source path, and their canonical hash re-derives;
 *   * route-asset parity - the packaged generated client's route table matches
 *     the recorded route manifest it was generated from, and the packaged
 *     navigation binds only operations that manifest declares.
 *
 * No running server or site is claimed; this is a deterministic identity proof
 * over two import paths into the same sealed code and the same frozen data.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  canonicalJson,
  canonicalJsonSha256,
  moduleParityCases,
  moduleParityViolations,
  packagedClient,
  projectRecord,
  projectRendered,
  recordSurfaces,
  renderedSurfaces,
  routeManifest,
} from "./ui-surface.mjs";

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;

// ---------------------------------------------------------------------------
// Export-surface parity.
// ---------------------------------------------------------------------------

for (const parityCase of moduleParityCases) {
  test(`packaged_ui_parity_test: the ${parityCase.feature} barrel re-exports the source implementations`, () => {
    const violations = moduleParityViolations(parityCase.sources, parityCase.barrel);
    assert.deepEqual(violations, [], `${parityCase.feature} packaged path diverges`);
    // The barrel is a real re-export surface, not an empty shim.
    const barrelKeys = Object.keys(parityCase.barrel).filter((key) => key !== "default");
    assert.ok(barrelKeys.length > 0, `${parityCase.feature} barrel exports nothing`);
  });
}

// ---------------------------------------------------------------------------
// Behavioural parity: identical records, identical HTML, re-derivable hashes.
// ---------------------------------------------------------------------------

for (const surface of renderedSurfaces) {
  test(`packaged_ui_parity_test: ${surface.id} record and HTML are identical across paths`, () => {
    const source = projectRendered(surface, "source");
    const packaged = projectRendered(surface, "packaged");

    assert.equal(source.record.kind, surface.kind);
    assert.equal(canonicalJson(packaged.record), canonicalJson(source.record));
    assert.equal(packaged.html, source.html);

    const sourceHash = canonicalJsonSha256(source.record);
    const packagedHash = canonicalJsonSha256(packaged.record);
    assert.equal(packagedHash, sourceHash);
    assert.match(packagedHash, SHA256_PATTERN);
  });

  test(`packaged_ui_parity_test: ${surface.id} projection hash re-derives deterministically`, () => {
    const first = canonicalJsonSha256(projectRendered(surface, "packaged").record);
    const second = canonicalJsonSha256(projectRendered(surface, "packaged").record);
    assert.equal(first, second);
  });
}

for (const surface of recordSurfaces) {
  test(`packaged_ui_parity_test: ${surface.id} record is identical across paths`, () => {
    const sourceRecord = projectRecord(surface, "source");
    const packagedRecord = projectRecord(surface, "packaged");
    assert.equal(sourceRecord.kind, surface.kind);
    assert.equal(canonicalJson(packagedRecord), canonicalJson(sourceRecord));
    assert.equal(
      canonicalJsonSha256(packagedRecord),
      canonicalJsonSha256(sourceRecord),
    );
  });
}

// ---------------------------------------------------------------------------
// Route-asset parity: the packaged client matches its recorded source manifest.
// ---------------------------------------------------------------------------

test("packaged_ui_parity_test: the packaged client route table matches the recorded manifest", () => {
  assert.equal(packagedClient.SOURCE_DOCUMENT.routeTableSha256, routeManifest.routeTableSha256);
  assert.equal(packagedClient.SOURCE_DOCUMENT.operationCount, routeManifest.operationCount);
  assert.match(packagedClient.SOURCE_DOCUMENT.routeTableSha256, SHA256_PATTERN);
  assert.deepEqual(
    [...packagedClient.OPERATION_IDS].sort(),
    [...routeManifest.operationIds].sort(),
  );
});

test("packaged_ui_parity_test: the packaged navigation binds only manifest-declared operations", () => {
  const nav = projectRecord(
    recordSurfaces.find((surface) => surface.id === "shell-navigation"),
    "packaged",
  );
  const declared = new Set(routeManifest.operationIds);
  for (const view of nav.views) {
    assert.ok(declared.has(view.operation_id), `${view.operation_id} is not a declared route`);
  }
});

// ---------------------------------------------------------------------------
// The gate must actually refuse: the comparator detects a divergent barrel.
// ---------------------------------------------------------------------------

test("packaged_ui_parity_test: a barrel that forks a source export is refused", () => {
  const original = () => 1;
  const fork = () => 1;
  const source = { buildAtlasView: original };
  const divergent = { buildAtlasView: fork };
  assert.ok(
    moduleParityViolations([source], divergent).some((v) => v.includes("not the source")),
  );
});

test("packaged_ui_parity_test: a barrel export that traces to no source module is refused", () => {
  const shared = () => 1;
  const source = { buildAtlasView: shared };
  const withExtra = { buildAtlasView: shared, sneakyExport: () => 2 };
  assert.ok(
    moduleParityViolations([source], withExtra).some((v) => v.includes("traces to no source")),
  );
});
