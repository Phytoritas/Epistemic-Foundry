/**
 * U04 accessibility_test.
 *
 * The U-phase accessibility gate asserts, deterministically and over the sealed
 * U02/U03 view projections, that every console surface meets the declared
 * accessibility contract with zero WCAG-critical structural failures:
 *
 *   * one `<main>` landmark, one `<header>`, one `<h1>`, and an unbroken
 *     h1 -> h2 heading hierarchy per rendered panel;
 *   * every content section carries a unique `data-section` landmark id and an
 *     `<h2>` accessible name, and the rendered focus order is exactly the
 *     order of the accessible projection the view record carries;
 *   * status is never conveyed by colour alone: every `data-state` token and
 *     every projected section state is non-empty text, and empty results are
 *     rendered as text rather than an empty list;
 *   * the record-only surfaces (health, navigation) expose titled, textual,
 *     visible sections and a textual read-model-state vocabulary.
 *
 * There is no browser here.  The gate makes no claim of a running site; it
 * proves a property of the deterministic HTML and frozen records the sealed
 * views produce, and refuses on any violation.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  canonicalJson,
  navigationAccessibilityViolations,
  panelAccessibilityViolations,
  projectRecord,
  projectRendered,
  recordSurfaces,
  renderedSurfaces,
  sectionRecordViolations,
} from "./ui-surface.mjs";

test("accessibility_test: every rendered U03 panel meets the contract with zero critical failures", () => {
  const failures = [];
  for (const surface of renderedSurfaces) {
    const { record, html } = projectRendered(surface, "packaged");
    const violations = panelAccessibilityViolations(html, record.sections);
    if (violations.length > 0) failures.push({ surface: surface.id, violations });
  }
  assert.deepEqual(failures, [], "rendered panels carry no WCAG-critical failure");
});

for (const surface of renderedSurfaces) {
  test(`accessibility_test: ${surface.id} panel has a single main/header/h1 and titled unique sections`, () => {
    const { record, html } = projectRendered(surface, "packaged");
    const violations = panelAccessibilityViolations(html, record.sections);
    assert.deepEqual(violations, []);

    // The focus order (data-section order) is exactly the projection order.
    const domIds = [...html.matchAll(/data-section="([^"]+)"/g)].map((match) => match[1]);
    assert.deepEqual(
      domIds,
      record.sections.map((section) => section.id),
    );
    assert.equal(new Set(domIds).size, domIds.length);
  });

  test(`accessibility_test: ${surface.id} rendered focus order is deterministic`, () => {
    const first = projectRendered(surface, "packaged").html;
    const second = projectRendered(surface, "packaged").html;
    assert.equal(first, second);
  });
}

test("accessibility_test: the health record exposes titled, textual, visible sections", () => {
  const health = recordSurfaces.find((surface) => surface.id === "health");
  const record = projectRecord(health, "packaged");
  assert.deepEqual(sectionRecordViolations(record.sections), []);
  // State is text, never colour: each section state is a non-empty token.
  for (const section of record.sections) {
    assert.equal(typeof section.state, "string");
    assert.ok(section.state.length > 0);
  }
});

test("accessibility_test: the console navigation exposes a textual read-model-state vocabulary", () => {
  const nav = recordSurfaces.find((surface) => surface.id === "shell-navigation");
  const record = projectRecord(nav, "packaged");
  assert.deepEqual(navigationAccessibilityViolations(record), []);
});

test("accessibility_test: the whole U-phase surface has zero critical accessibility failures", () => {
  const findings = [];
  for (const surface of renderedSurfaces) {
    const { record, html } = projectRendered(surface, "packaged");
    findings.push(...panelAccessibilityViolations(html, record.sections));
  }
  const health = recordSurfaces.find((surface) => surface.id === "health");
  findings.push(...sectionRecordViolations(projectRecord(health, "packaged").sections));
  const nav = recordSurfaces.find((surface) => surface.id === "shell-navigation");
  findings.push(...navigationAccessibilityViolations(projectRecord(nav, "packaged")));
  assert.deepEqual(findings, []);
});

test("accessibility_test: the projection accessibility check is deterministic", () => {
  const health = recordSurfaces.find((surface) => surface.id === "health");
  const first = projectRecord(health, "packaged");
  const second = projectRecord(health, "packaged");
  assert.equal(canonicalJson(first), canonicalJson(second));
});

// ---------------------------------------------------------------------------
// The gate must actually refuse: each rule flags a deliberately broken surface.
// ---------------------------------------------------------------------------

test("accessibility_test: two <main> landmarks are refused", () => {
  const html = "<main><header><h1>A</h1></header><section data-section=\"x\"><h2>X</h2></section></main><main></main>";
  assert.ok(panelAccessibilityViolations(html).some((v) => v.includes("<main> landmark")));
});

test("accessibility_test: a missing <h1> is refused", () => {
  const html = "<main><header></header><section data-section=\"x\"><h2>X</h2></section></main>";
  assert.ok(panelAccessibilityViolations(html).some((v) => v.includes("<h1>")));
});

test("accessibility_test: a section with no <h2> accessible name is refused", () => {
  const html = "<main><header><h1>A</h1></header><section data-section=\"x\"><p>no heading</p></section></main>";
  assert.ok(panelAccessibilityViolations(html).some((v) => v.includes("accessible name")));
});

test("accessibility_test: a skipped heading level is refused", () => {
  const html = "<main><header><h1>A</h1></header><section data-section=\"x\"><h2>X</h2><h4>deep</h4></section></main>";
  assert.ok(panelAccessibilityViolations(html).some((v) => v.includes("hierarchy")));
});

test("accessibility_test: an empty data-state token is refused as colour-only status", () => {
  const html = "<main><header><h1>A</h1></header><section data-section=\"x\" data-state=\"\"><h2>X</h2></section></main>";
  assert.ok(panelAccessibilityViolations(html).some((v) => v.includes("no text token")));
});

test("accessibility_test: an empty <ol></ol> with no textual alternative is refused", () => {
  const html = "<main><header><h1>A</h1></header><section data-section=\"x\"><h2>X</h2><ol></ol></section></main>";
  assert.ok(panelAccessibilityViolations(html).some((v) => v.includes("empty <ol>")));
});

test("accessibility_test: a focus order that disagrees with the projection is refused", () => {
  const html =
    "<main><header><h1>A</h1></header>" +
    "<section data-section=\"b\"><h2>B</h2></section>" +
    "<section data-section=\"a\"><h2>A</h2></section></main>";
  const projection = [
    { id: "a", title: "A", state: "READY", visible: true },
    { id: "b", title: "B", state: "READY", visible: true },
  ];
  assert.ok(panelAccessibilityViolations(html, projection).some((v) => v.includes("focus order")));
});

test("accessibility_test: a section record missing a title, state or visibility is refused", () => {
  assert.ok(
    sectionRecordViolations([{ id: "x", title: "", state: "READY", visible: true }]).some((v) =>
      v.includes("accessible name"),
    ),
  );
  assert.ok(
    sectionRecordViolations([{ id: "x", title: "X", state: "", visible: true }]).some((v) =>
      v.includes("text token"),
    ),
  );
  assert.ok(
    sectionRecordViolations([{ id: "x", title: "X", state: "READY", visible: false }]).some((v) =>
      v.includes("visible"),
    ),
  );
});
