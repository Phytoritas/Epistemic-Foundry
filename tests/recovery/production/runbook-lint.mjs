// Runbook lint contract for Epistemic Foundry Y03 operational runbooks.
//
// `runbook_lint` is fail-closed: a runbook is only lint-clean when every
// structural requirement below holds. The rules exist so that each runbook
// step is actionable and complete (imperative + verifiable), recovery
// objectives are quantified (RPO/RTO measured, not vague), and no placeholder
// text can silently ship as an "operational" procedure.

import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

// Sections every runbook must declare, in this exact order, exactly once.
export const REQUIRED_SECTIONS = Object.freeze([
  "Metadata",
  "Preconditions",
  "Procedure",
  "Verification",
  "Rollback",
  "Escalation",
]);

// Metadata keys every runbook must declare with a non-empty value.
export const REQUIRED_METADATA_KEYS = Object.freeze([
  "id",
  "title",
  "owner",
  "severity",
  "last_reviewed",
  "rpo",
  "rto",
]);

// Tokens that mark an unfinished or non-actionable runbook. Fail-closed.
const PLACEHOLDER_PATTERN =
  /\b(TODO|TBD|FIXME|XXX|PLACEHOLDER|WIP|LOREM)\b|<[^>\n]+>/iu;

// A quantified duration: a number followed by a time unit. Enforces that RPO
// and RTO are measured, not narrative ("as soon as possible" is rejected).
const DURATION_PATTERN =
  /(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days)\b/iu;

const ID_PATTERN = /^RB-[A-Z0-9][A-Z0-9-]*$/u;
const SEVERITY_PATTERN = /^sev[123]$/u;
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/u;
// A step is actionable only if it opens with a capitalized imperative verb.
const IMPERATIVE_PATTERN = /^[A-Z][a-z]+\b/u;

const fail = (sourceName, message) => {
  throw new Error(`runbook_lint(${sourceName}): ${message}`);
};

const parseSections = (lines, sourceName) => {
  // Locate the single H1 title.
  let titleIndex = -1;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.trim() === "") continue;
    if (/^# (?!#)/u.test(line)) {
      titleIndex = index;
      break;
    }
    fail(sourceName, "first content line must be a single H1 title");
  }
  if (titleIndex === -1) fail(sourceName, "missing H1 title");
  const h1Count = lines.filter((line) => /^# (?!#)/u.test(line)).length;
  if (h1Count !== 1) fail(sourceName, `expected exactly one H1 title, found ${h1Count}`);
  const title = lines[titleIndex].replace(/^#\s+/u, "").trim();
  if (title === "") fail(sourceName, "H1 title is empty");

  // Collect H2 sections in document order.
  const sections = [];
  for (let index = titleIndex + 1; index < lines.length; index += 1) {
    const match = /^##\s+(.+?)\s*$/u.exec(lines[index]);
    if (!match) continue;
    if (/^#{1,1}\s/u.test(lines[index])) continue;
    sections.push({ name: match[1].trim(), start: index });
  }
  for (let index = 0; index < sections.length; index += 1) {
    sections[index].end = index + 1 < sections.length ? sections[index + 1].start : lines.length;
    sections[index].body = lines.slice(sections[index].start + 1, sections[index].end);
  }

  const observed = sections.map((section) => section.name);
  if (observed.length !== REQUIRED_SECTIONS.length ||
      observed.some((name, index) => name !== REQUIRED_SECTIONS[index])) {
    fail(
      sourceName,
      `sections must be exactly [${REQUIRED_SECTIONS.join(", ")}] in order, ` +
        `found [${observed.join(", ")}]`,
    );
  }
  return { title, sections };
};

const bulletValues = (body) =>
  body
    .map((line) => /^-\s+(.+?)\s*$/u.exec(line))
    .filter((match) => match !== null)
    .map((match) => match[1].trim());

const parseMetadata = (body, sourceName) => {
  const metadata = {};
  for (const entry of bulletValues(body)) {
    const match = /^([a-z_]+):\s*(.+?)\s*$/u.exec(entry);
    if (!match) fail(sourceName, `metadata bullet is not "key: value": "${entry}"`);
    const key = match[1];
    if (key in metadata) fail(sourceName, `duplicate metadata key "${key}"`);
    metadata[key] = match[2].trim();
  }
  for (const key of REQUIRED_METADATA_KEYS) {
    if (!(key in metadata) || metadata[key] === "") {
      fail(sourceName, `missing or empty required metadata key "${key}"`);
    }
  }
  if (!ID_PATTERN.test(metadata.id)) fail(sourceName, `metadata id "${metadata.id}" is malformed`);
  if (!SEVERITY_PATTERN.test(metadata.severity)) {
    fail(sourceName, `metadata severity "${metadata.severity}" must be sev1|sev2|sev3`);
  }
  if (!ISO_DATE_PATTERN.test(metadata.last_reviewed)) {
    fail(sourceName, `metadata last_reviewed "${metadata.last_reviewed}" must be YYYY-MM-DD`);
  }
  for (const key of ["rpo", "rto"]) {
    if (!DURATION_PATTERN.test(metadata[key])) {
      fail(sourceName, `metadata ${key} "${metadata[key]}" must be a measured duration`);
    }
  }
  return metadata;
};

const parseProcedure = (body, sourceName) => {
  // Group lines into numbered steps: "1. ...", continuation lines are indented.
  const steps = [];
  let current = null;
  for (const line of body) {
    if (line.trim() === "") continue;
    const stepMatch = /^(\d+)\.\s+(.+?)\s*$/u.exec(line);
    if (stepMatch) {
      current = { number: Number(stepMatch[1]), head: stepMatch[2].trim(), lines: [] };
      steps.push(current);
      continue;
    }
    if (/^\s+\S/u.test(line)) {
      if (current === null) fail(sourceName, "procedure continuation before first step");
      current.lines.push(line.trim());
      continue;
    }
    fail(sourceName, `procedure line is neither a numbered step nor a step detail: "${line}"`);
  }
  if (steps.length < 2) fail(sourceName, `procedure must have at least 2 steps, found ${steps.length}`);
  for (let index = 0; index < steps.length; index += 1) {
    const step = steps[index];
    if (step.number !== index + 1) {
      fail(sourceName, `procedure steps must be 1..N in order; step ${index + 1} is numbered ${step.number}`);
    }
    if (!IMPERATIVE_PATTERN.test(step.head)) {
      fail(sourceName, `procedure step ${step.number} must start with an imperative verb: "${step.head}"`);
    }
    const hasVerify = step.lines.some((line) => /^Verify:\s*\S/u.test(line));
    if (!hasVerify) {
      fail(sourceName, `procedure step ${step.number} is missing a "Verify:" detail line`);
    }
  }
  return steps;
};

const requireNonEmptyBullets = (section, sourceName) => {
  if (bulletValues(section.body).length === 0) {
    fail(sourceName, `section "${section.name}" must contain at least one "- " bullet`);
  }
};

/**
 * Lint one runbook. Returns parsed metadata + steps on success; throws a
 * precise Error on the first violation (fail-closed).
 */
export const lintRunbookText = (text, sourceName = "runbook") => {
  if (typeof text !== "string" || text.trim() === "") {
    fail(sourceName, "runbook is empty");
  }
  if (PLACEHOLDER_PATTERN.test(text)) {
    fail(sourceName, "runbook contains a placeholder token (TODO/TBD/FIXME/<...>)");
  }
  const lines = text.replace(/\r\n/gu, "\n").split("\n");
  const { title, sections } = parseSections(lines, sourceName);
  const byName = new Map(sections.map((section) => [section.name, section]));
  const metadata = parseMetadata(byName.get("Metadata").body, sourceName);
  if (metadata.title !== title) {
    fail(sourceName, `metadata title "${metadata.title}" must match H1 "${title}"`);
  }
  const steps = parseProcedure(byName.get("Procedure").body, sourceName);
  for (const name of ["Preconditions", "Verification", "Rollback", "Escalation"]) {
    requireNonEmptyBullets(byName.get(name), sourceName);
  }
  return { title, metadata, steps };
};

/**
 * Lint every `*.md` runbook under `directory`. Fail-closed: an empty or
 * missing directory is a lint failure, not an empty pass.
 */
export const lintRunbookDirectory = (directory) => {
  let entries;
  try {
    entries = readdirSync(directory);
  } catch {
    throw new Error(`runbook_lint: runbook directory is missing: ${directory}`);
  }
  const runbooks = entries.filter((name) => name.endsWith(".md")).sort();
  if (runbooks.length === 0) {
    throw new Error(`runbook_lint: no runbooks found in ${directory}`);
  }
  const results = new Map();
  const ids = new Set();
  for (const name of runbooks) {
    const filePath = path.join(directory, name);
    if (!statSync(filePath).isFile()) {
      throw new Error(`runbook_lint: ${name} is not a regular file`);
    }
    const parsed = lintRunbookText(readFileSync(filePath, "utf8"), name);
    if (ids.has(parsed.metadata.id)) {
      throw new Error(`runbook_lint: duplicate runbook id "${parsed.metadata.id}" in ${name}`);
    }
    ids.add(parsed.metadata.id);
    results.set(name, parsed);
  }
  return results;
};

/**
 * Parse a measured duration string ("at most 30 minutes") to milliseconds.
 * Used by the disaster recovery drill to enforce documented RPO/RTO budgets.
 */
export const parseDurationToMs = (value) => {
  const match = DURATION_PATTERN.exec(value);
  if (!match) throw new Error(`not a measured duration: "${value}"`);
  const quantity = Number(match[1]);
  const unit = match[2].toLowerCase();
  const unitMs = unit.startsWith("second")
    ? 1000
    : unit.startsWith("minute")
      ? 60_000
      : unit.startsWith("hour")
        ? 3_600_000
        : 86_400_000;
  return quantity * unitMs;
};
