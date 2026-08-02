/**
 * U04 shared U-phase surface registry for the accessibility and
 * packaged-path parity gates.
 *
 * This module owns no view logic of its own.  It composes the sealed U02 and
 * U03 vocabularies exactly as they are shipped, importing each view twice:
 *
 *   * the *source* path, the `*-view.mjs` (and `app/*.mjs`) modules a Vite
 *     build compiles from, and
 *   * the *packaged* path, the `index.mjs` barrels the console imports as the
 *     package export surface.
 *
 * The U02/U03 fixtures are reused verbatim; no fixture data is restated here
 * except the Evidence Atlas snapshot, which ships no shared fixture module.
 * Everything below is a pure, deterministic projection: no clock, no random
 * source, no environment read, so two runs hash identically.
 */

import { readFileSync } from "node:fs";

// ---------------------------------------------------------------------------
// Packaged export surface (the barrels the console ships and imports).
// ---------------------------------------------------------------------------
import * as appBarrel from "../../web/src/app/index.mjs";
import * as healthBarrel from "../../web/src/features/health/index.mjs";
import * as atlasBarrel from "../../web/src/features/atlas/index.mjs";
import * as parliamentBarrel from "../../web/src/features/parliament/index.mjs";
import * as aporiaBarrel from "../../web/src/features/aporia/index.mjs";
import * as passportBarrel from "../../web/src/features/passport/index.mjs";

// ---------------------------------------------------------------------------
// Source path (the modules a Vite build would compile from).
// ---------------------------------------------------------------------------
import * as authSource from "../../web/src/app/auth.mjs";
import * as shellSource from "../../web/src/app/shell.mjs";
import * as recordHashSource from "../../web/src/app/record-hash.mjs";
import * as healthSource from "../../web/src/features/health/health-view.mjs";
import * as atlasSource from "../../web/src/features/atlas/atlas-view.mjs";
import * as parliamentSource from "../../web/src/features/parliament/parliament-view.mjs";
import * as aporiaSource from "../../web/src/features/aporia/aporia-view.mjs";
import * as passportSource from "../../web/src/features/passport/passport-view.mjs";

// The generated UI client is the packaged route asset; the route manifest is
// the generator's recorded source of truth for that asset.
import * as generatedClient from "../../web/src/generated/ui-client/index.mjs";

// ---------------------------------------------------------------------------
// Reused U02/U03 fixtures (composed, never restated).
// ---------------------------------------------------------------------------
import {
  authenticatedSession as healthAuthenticatedSession,
  livenessReceipt,
  readinessReceipt,
} from "../../web/src/features/health/health-test-fixtures.mjs";
import { parliamentInput } from "../../web/src/features/parliament/parliament-test-fixtures.mjs";
import { aporiaInput } from "../../web/src/features/aporia/aporia-test-fixtures.mjs";
import { passportInput } from "../../web/src/features/passport/passport-test-fixtures.mjs";

/** Canonical, key-order-independent hashing composed from the U02 app barrel. */
export const canonicalJson = appBarrel.canonicalJson;
export const canonicalJsonSha256 = appBarrel.canonicalJsonSha256;

const REPO = new URL("../../", import.meta.url);
const readJson = (relative) => JSON.parse(readFileSync(new URL(relative, REPO), "utf8"));

/** The recorded route manifest the generated client is derived from. */
export const routeManifest = readJson("web/src/generated/ui-client/route-manifest.json").routeTable;

/**
 * The one Atlas coverage snapshot U03 ships no shared fixture for.  Field for
 * field this mirrors the sealed `atlas-view.test.mjs` snapshot: three cells that
 * exercise SEARCHED_WITH_RESULTS, SEARCHED_NONE and UNSEARCHED, one declared
 * cell deliberately absent so a coverage limitation is visible.
 */
const HASH_A = `sha256:${"a".repeat(64)}`;
const HASH_B = `sha256:${"b".repeat(64)}`;
const atlasSnapshot = () => ({
  snapshot_id: "CS-0001",
  insight_id: "INS-0001",
  insight_revision: 3,
  corpus_snapshot_hash: HASH_A,
  axes: [
    { axis_id: "method", label: "Method", buckets: ["observational", "experimental"] },
    { axis_id: "population", label: "Population", buckets: ["greenhouse", "field"] },
  ],
  cells: [
    {
      coordinate: { method: "observational", population: "greenhouse" },
      search_state: "SEARCHED_WITH_RESULTS",
      support_count: 2,
      counter_count: 1,
      null_count: 0,
      boundary_count: 0,
      method_count: 1,
      independent_cluster_count: 2,
      evidence_ids: ["EV-0001", "EV-0002"],
      gap_labels: [],
    },
    {
      coordinate: { method: "experimental", population: "greenhouse" },
      search_state: "SEARCHED_NONE",
      support_count: 0,
      counter_count: 0,
      null_count: 0,
      boundary_count: 0,
      method_count: 0,
      independent_cluster_count: 0,
      evidence_ids: [],
      gap_labels: ["no controlled trial"],
    },
    {
      coordinate: { method: "observational", population: "field" },
      search_state: "UNSEARCHED",
      support_count: 0,
      counter_count: 0,
      null_count: 0,
      boundary_count: 0,
      method_count: 0,
      independent_cluster_count: 0,
      evidence_ids: [],
      gap_labels: ["never searched"],
    },
  ],
  lens_entropy: null,
  dominant_lens: null,
  unsearched_scopes: ["publications before 2019"],
  created_at: "2026-01-02T03:04:05Z",
  provenance_manifest_id: "PM-0001",
  search_lane_receipt_ids: ["SLR-0001"],
  bias_risk_register_id: "BRR-0001",
  coverage_certificate_hash: HASH_B,
  effective_independent_evidence_count: 2,
  stale: false,
});

/** The U02 health view input: authenticated session with liveness and readiness. */
const healthInput = () => ({
  auth: healthAuthenticatedSession(),
  liveness_receipt: livenessReceipt(),
  readiness_receipt: readinessReceipt(),
});

/**
 * The U03 rendered surfaces: each is built and rendered through both the source
 * path and the packaged path so parity can compare them byte for byte and the
 * accessibility gate can read the packaged rendered HTML.
 */
export const renderedSurfaces = [
  {
    id: "atlas",
    kind: "EpistemicFoundryAtlasView",
    input: atlasSnapshot,
    source: { buildView: atlasSource.buildAtlasView, renderPanel: atlasSource.renderAtlasPanel },
    packaged: { buildView: atlasBarrel.buildAtlasView, renderPanel: atlasBarrel.renderAtlasPanel },
  },
  {
    id: "parliament",
    kind: "EpistemicFoundryParliamentView",
    input: parliamentInput,
    source: {
      buildView: parliamentSource.buildParliamentView,
      renderPanel: parliamentSource.renderParliamentPanel,
    },
    packaged: {
      buildView: parliamentBarrel.buildParliamentView,
      renderPanel: parliamentBarrel.renderParliamentPanel,
    },
  },
  {
    id: "aporia",
    kind: "EpistemicFoundryAporiaView",
    input: aporiaInput,
    source: {
      buildView: aporiaSource.buildAporiaView,
      renderPanel: aporiaSource.renderAporiaPanel,
    },
    packaged: {
      buildView: aporiaBarrel.buildAporiaView,
      renderPanel: aporiaBarrel.renderAporiaPanel,
    },
  },
  {
    id: "passport",
    kind: "EpistemicFoundryPassportView",
    input: passportInput,
    source: {
      buildView: passportSource.buildPassportView,
      renderPanel: passportSource.renderPassportPanel,
    },
    packaged: {
      buildView: passportBarrel.buildPassportView,
      renderPanel: passportBarrel.renderPassportPanel,
    },
  },
];

/**
 * The U02 record surfaces: a health view record that carries titled, textual
 * sections, and the console navigation registry whose read-model states are all
 * text tokens.  These have no rendered HTML panel; their accessibility is a
 * property of the frozen projection.
 */
export const recordSurfaces = [
  {
    id: "health",
    kind: "EpistemicFoundryConsoleHealthView",
    input: healthInput,
    source: { buildView: healthSource.buildHealthView },
    packaged: { buildView: healthBarrel.buildHealthView },
  },
  {
    id: "shell-navigation",
    kind: "EpistemicFoundryConsoleNavigation",
    input: () => undefined,
    source: { buildView: () => shellSource.buildShellNavigation() },
    packaged: { buildView: () => appBarrel.buildShellNavigation() },
  },
];

/**
 * The module parity cases: each names the source module(s) a Vite build would
 * compile and the barrel the console imports instead.  The console must import
 * the same implementations, never a hand-written packaged fork.
 */
export const moduleParityCases = [
  { feature: "health", sources: [healthSource], barrel: healthBarrel },
  { feature: "atlas", sources: [atlasSource], barrel: atlasBarrel },
  { feature: "parliament", sources: [parliamentSource], barrel: parliamentBarrel },
  { feature: "aporia", sources: [aporiaSource], barrel: aporiaBarrel },
  { feature: "passport", sources: [passportSource], barrel: passportBarrel },
  { feature: "app", sources: [authSource, shellSource, recordHashSource], barrel: appBarrel },
];

/** The packaged route asset (generated client) exposed for route-parity checks. */
export const packagedClient = generatedClient;

// ---------------------------------------------------------------------------
// Deterministic HTML structural analysis (no DOM; the panels are generated by
// known code, so a byte-level parse is exact and reproducible).
// ---------------------------------------------------------------------------

const firstIndex = (html, pattern) => {
  const match = pattern.exec(html);
  return match === null ? -1 : match.index;
};

const countMatches = (html, pattern) => {
  let count = 0;
  for (let match = pattern.exec(html); match !== null; match = pattern.exec(html)) count += 1;
  return count;
};

/** Parse a rendered panel into the structure the accessibility contract reads. */
export function analyzeHtml(html) {
  const sectionOpen = /<section\b[^>]*>/g;
  const sectionWithId = /<section\b[^>]*\bdata-section="([^"]*)"[^>]*>/g;
  const sections = [];
  for (let match = sectionWithId.exec(html); match !== null; match = sectionWithId.exec(html)) {
    sections.push({ id: match[1], index: match.index });
  }
  const dataStates = [];
  const dataStatePattern = /\bdata-state="([^"]*)"/g;
  for (
    let match = dataStatePattern.exec(html);
    match !== null;
    match = dataStatePattern.exec(html)
  ) {
    dataStates.push(match[1]);
  }
  return {
    mainCount: countMatches(html, /<main\b/g),
    headerCount: countMatches(html, /<header\b/g),
    h1Count: countMatches(html, /<h1\b/g),
    h1Index: firstIndex(html, /<h1\b/g),
    sectionOpenCount: countMatches(html, sectionOpen),
    sections,
    dataStates,
    hasSkippedHeadingLevel: /<h[3-6]\b/.test(html),
    hasEmptyList: /<ol>\s*<\/ol>/.test(html),
  };
}

const h2CountInSlice = (slice) => countMatches(slice, /<h2\b/g);
const firstH2Text = (slice) => {
  const match = /<h2\b[^>]*>([^<]*)<\/h2>/.exec(slice);
  return match === null ? null : match[1].trim();
};

/**
 * The accessibility contract over one rendered panel and its projected sections.
 * Returns a (possibly empty) list of WCAG-critical structural violations.  Zero
 * violations is the passing condition; any entry refuses the render.
 */
export function panelAccessibilityViolations(html, sectionRecord) {
  const analysis = analyzeHtml(html);
  const violations = [];

  if (analysis.mainCount !== 1) {
    violations.push(`expected exactly one <main> landmark, found ${analysis.mainCount}`);
  }
  if (analysis.headerCount !== 1) {
    violations.push(`expected exactly one <header>, found ${analysis.headerCount}`);
  }
  if (analysis.h1Count !== 1) {
    violations.push(`expected exactly one <h1>, found ${analysis.h1Count}`);
  }
  if (analysis.hasSkippedHeadingLevel) {
    violations.push("a heading below <h2> is used, skipping the h1/h2 hierarchy");
  }
  if (analysis.sections.length === 0) {
    violations.push("no content section carries a data-section landmark id");
  }
  if (analysis.sectionOpenCount !== analysis.sections.length) {
    violations.push("a <section> is present without a data-section landmark id");
  }
  if (analysis.sections.length > 0 && analysis.h1Index >= analysis.sections[0].index) {
    violations.push("the <h1> does not precede the first content section");
  }

  const ids = analysis.sections.map((section) => section.id);
  ids.forEach((id, position) => {
    if (id.length === 0) violations.push(`section ${position} has an empty data-section id`);
  });
  if (new Set(ids).size !== ids.length) {
    violations.push("two content sections share the same data-section id");
  }

  // Every section needs one <h2> accessible name; state is never colour-only,
  // so wherever a data-state attribute appears its token must be non-empty text.
  analysis.sections.forEach((section, position) => {
    const end =
      position + 1 < analysis.sections.length
        ? analysis.sections[position + 1].index
        : html.length;
    const slice = html.slice(section.index, end);
    const headingCount = h2CountInSlice(slice);
    if (headingCount < 1) {
      violations.push(`section ${section.id} has no <h2> accessible name`);
    } else if ((firstH2Text(slice) ?? "").length === 0) {
      violations.push(`section ${section.id} has an empty <h2> accessible name`);
    }
  });
  analysis.dataStates.forEach((state, position) => {
    if (state.length === 0) {
      violations.push(`data-state ${position} conveys status with no text token`);
    }
  });
  if (analysis.hasEmptyList) {
    violations.push("an empty <ol></ol> is rendered with no textual alternative");
  }

  // The rendered focus order must be the accessible projection's section order,
  // so a screen-reader traversal and the frozen record agree exactly.
  if (sectionRecord !== undefined) {
    const recordViolations = sectionRecordViolations(sectionRecord);
    for (const entry of recordViolations) violations.push(`projection: ${entry}`);
    const recordIds = sectionRecord.map((section) => section.id);
    if (recordIds.length !== ids.length || recordIds.some((id, i) => id !== ids[i])) {
      violations.push(
        `focus order ${JSON.stringify(ids)} does not match the projection ${JSON.stringify(
          recordIds,
        )}`,
      );
    }
  }
  return violations;
}

/** The accessibility contract over a titled, textual section record. */
export function sectionRecordViolations(sections) {
  const violations = [];
  if (!Array.isArray(sections) || sections.length === 0) {
    violations.push("the section projection is empty");
    return violations;
  }
  const ids = [];
  for (const section of sections) {
    const id = section?.id;
    const title = section?.title;
    const state = section?.state;
    if (typeof id !== "string" || id.length === 0) {
      violations.push("a section has no landmark id");
    } else {
      ids.push(id);
    }
    if (typeof title !== "string" || title.trim().length === 0) {
      violations.push(`section ${String(id)} has no text accessible name`);
    }
    if (typeof state !== "string" || state.trim().length === 0) {
      violations.push(`section ${String(id)} conveys status with no text token`);
    }
    if (section?.visible !== true) {
      violations.push(`section ${String(id)} is not marked visible`);
    }
  }
  if (new Set(ids).size !== ids.length) {
    violations.push("two sections share the same landmark id");
  }
  return violations;
}

/** The accessibility contract over the console navigation registry. */
export function navigationAccessibilityViolations(navigation) {
  const violations = [];
  const states = navigation?.read_model_states;
  if (!Array.isArray(states) || states.length === 0) {
    violations.push("navigation declares no textual read-model states");
  } else {
    states.forEach((state, position) => {
      if (typeof state !== "string" || state.trim().length === 0) {
        violations.push(`read-model state ${position} is not a text token`);
      }
    });
    if (new Set(states).size !== states.length) {
      violations.push("navigation read-model states are not distinct");
    }
  }
  const views = navigation?.views;
  if (!Array.isArray(views) || views.length === 0) {
    violations.push("navigation exposes no views");
  } else {
    for (const view of views) {
      if (typeof view?.title !== "string" || view.title.trim().length === 0) {
        violations.push(`view ${String(view?.view_id)} has no text accessible name`);
      }
      if (typeof view?.view_id !== "string" || view.view_id.trim().length === 0) {
        violations.push("a view has no landmark id");
      }
    }
  }
  return violations;
}

// ---------------------------------------------------------------------------
// Packaged-path parity comparators (pure, so the gate itself is self-testable).
// ---------------------------------------------------------------------------

/**
 * Report every way a packaged barrel diverges from its source module(s): a
 * missing re-export, a re-export that is a different object than the source's,
 * or a packaged export that traces to no source module.
 */
export function moduleParityViolations(sources, barrel) {
  const violations = [];
  const sourceExports = new Map();
  for (const source of sources) {
    for (const key of Object.keys(source)) {
      if (key === "default") continue;
      if (!sourceExports.has(key)) sourceExports.set(key, source[key]);
      if (!Object.is(barrel[key], source[key])) {
        violations.push(`barrel export ${key} is not the source implementation`);
      }
    }
  }
  for (const key of Object.keys(barrel)) {
    if (key === "default") continue;
    if (!sourceExports.has(key)) {
      violations.push(`barrel export ${key} traces to no source module`);
    } else if (!Object.is(barrel[key], sourceExports.get(key))) {
      violations.push(`barrel export ${key} diverges from the source implementation`);
    }
  }
  return violations;
}

/** Build a rendered surface through one path and return its record and HTML. */
export function projectRendered(surface, path) {
  const input = surface.input();
  return {
    record: surface[path].buildView(input),
    html: surface[path].renderPanel(input),
  };
}

/** Build a record surface through one path and return its record. */
export function projectRecord(surface, path) {
  return surface[path].buildView(surface.input());
}
