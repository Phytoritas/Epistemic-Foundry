import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..", "..", "..");
const skillPath = path.join(
  root,
  "plugins",
  "epistemic-foundry",
  "skills",
  "foundry",
  "SKILL.md",
);
const agentPath = path.join(
  root,
  "plugins",
  "epistemic-foundry",
  "skills",
  "foundry",
  "agents",
  "openai.yaml",
);

const readCanonicalText = (target) => {
  const bytes = fs.readFileSync(target);
  assert.notEqual(bytes[0], 0xef, `${target} must not start with a UTF-8 BOM`);
  const text = bytes.toString("utf8");
  assert.equal(text.includes("\uFFFD"), false, `${target} must be valid UTF-8`);
  assert.equal(/\r/u.test(text), false, `${target} must use LF line endings`);
  assert.equal(/[ \t]+$/gmu.test(text), false, `${target} must not contain trailing whitespace`);
  assert.equal(text.endsWith("\n"), true, `${target} must end with one newline`);
  return text;
};

test("skill_metadata_lint: parent frontmatter has bounded implicit invocation metadata", () => {
  const skill = readCanonicalText(skillPath);
  const frontmatterMatch = /^---\n([\s\S]*?)\n---\n/u.exec(skill);
  assert.notEqual(frontmatterMatch, null);
  const frontmatter = frontmatterMatch[1];

  assert.match(frontmatter, /^name: foundry$/mu);
  assert.match(frontmatter, /^description: .*Route research and evidence-synthesis requests/mu);
  assert.match(frontmatter, /Use for claim validation/mu);
  assert.match(frontmatter, /do not use for ordinary editing or casual questions/mu);
  assert.match(frontmatter, /^  allow_implicit_invocation: true$/mu);
  assert.match(frontmatter, /^  sensitive: false$/mu);
  assert.match(frontmatter, /^  side_effecting: false$/mu);
});

test("skill_metadata_lint: parent instructions preserve routing-only authority boundary", () => {
  const skill = readCanonicalText(skillPath);

  assert.match(skill, /does not own state, approval, promotion, or execution authority/u);
  assert.match(skill, /Load a selected child skill only after/u);
  assert.match(skill, /Sensitive, side-effecting, administrative, and remote skills are explicit-only/u);
  assert.match(skill, /Do not invoke for ordinary editing, rewriting, proofreading, translation, or casual questions/u);
  assert.match(skill, /Never treat a routing decision as permission to mutate FORGE state/u);
});

test("skill_metadata_lint: always-visible agent metadata has exact trigger and exclusion boundaries", () => {
  const metadata = readCanonicalText(agentPath);

  assert.match(metadata, /^  allow_implicit_invocation: true$/mu);
  assert.match(metadata, /^  sensitive: false$/mu);
  assert.match(metadata, /^  side_effecting: false$/mu);
  assert.match(metadata, /^  load_full_instructions: on_demand$/mu);
  for (const phrase of [
    "claim validation",
    "literature synthesis",
    "evidence synthesis",
    "evidence coverage",
    "contradiction analysis",
    "hypothesis passport",
  ]) {
    assert.match(metadata, new RegExp(`^    - "${phrase}"$`, "mu"));
  }
  for (const phrase of ["ordinary editing", "proofread", "rewrite", "translate", "casual question"]) {
    assert.match(metadata, new RegExp(`^    - "${phrase}"$`, "mu"));
  }
});

test("skill_metadata_lint: initial metadata does not embed full instructions or references", () => {
  const metadata = readCanonicalText(agentPath);

  assert.doesNotMatch(metadata, /^instructions:/mu);
  assert.doesNotMatch(metadata, /^references:/mu);
  assert.doesNotMatch(metadata, /^body:/mu);
  assert.doesNotMatch(metadata, /\.\.\/references\//u);
});
