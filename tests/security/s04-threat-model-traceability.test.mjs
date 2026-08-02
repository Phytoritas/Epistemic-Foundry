import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const traceabilityPath = path.join(
  repositoryRoot,
  "artifacts/work_packages/S04/threat_model_traceability.json",
);

const readText = (relativePath) =>
  fs.readFileSync(path.join(repositoryRoot, relativePath), "utf8");

const readJson = (relativePath) => JSON.parse(readText(relativePath));

const sha256 = (relativePath) =>
  createHash("sha256").update(fs.readFileSync(path.join(repositoryRoot, relativePath))).digest("hex");

const canonicalJson = (value) => {
  if (value === null) return "null";
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") {
    assert.equal(Number.isFinite(value), true, "canonical JSON rejects non-finite numbers");
    return JSON.stringify(value);
  }
  assert.equal(typeof value, "object", "canonical JSON only accepts JSON values");
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
    .join(",")}}`;
};

const canonicalHashExcluding = (document, excludedField) => {
  const preimage = Object.fromEntries(
    Object.entries(document).filter(([key]) => key !== excludedField),
  );
  return `sha256:${createHash("sha256").update(canonicalJson(preimage), "utf8").digest("hex")}`;
};

const canonicalHash = (value) =>
  `sha256:${createHash("sha256").update(canonicalJson(value), "utf8").digest("hex")}`;

const withCanonicalHash = (document, hashField) => ({
  ...document,
  [hashField]: canonicalHashExcluding(document, hashField),
});

const requirementSection = (source, requirementId) => {
  const marker = `- requirement_id: ${requirementId}`;
  const start = source.indexOf(marker);
  assert.notEqual(start, -1, `${requirementId} is missing`);
  const next = source.indexOf("\n- requirement_id:", start + marker.length);
  return source.slice(start, next === -1 ? source.length : next);
};

const ACTIVE_BINDING_PATH = "manifests/source_bindings/development-manifest.binding.json";

const parseManifestStringList = (source, packageId, field) => {
  const lines = source.split(/\r?\n/u);
  const packageStart = lines.findIndex((line) => line === `- id: ${packageId}`);
  assert.notEqual(packageStart, -1, `manifest package is missing: ${packageId}`);
  const nextPackageOffset = lines
    .slice(packageStart + 1)
    .findIndex((line) => /^- id: [A-Z][0-9]{2}$/u.test(line));
  const packageEnd = nextPackageOffset === -1
    ? lines.length
    : packageStart + 1 + nextPackageOffset;
  const fieldOffset = lines
    .slice(packageStart, packageEnd)
    .findIndex((line) => line === `  ${field}:`);
  assert.notEqual(fieldOffset, -1, `manifest field is missing: ${packageId}:${field}`);
  const fieldStart = packageStart + fieldOffset;
  const values = [];
  for (let index = fieldStart + 1; index < packageEnd; index += 1) {
    const line = lines[index];
    if (/^  [a-z][a-z0-9_]*:/u.test(line)) break;
    if (line.length === 0) continue;
    const item = /^  - (.+)$/u.exec(line);
    assert.notEqual(item, null, `unsupported manifest list syntax: ${packageId}:${field}`);
    let value = item[1];
    if (value.startsWith('"')) value = JSON.parse(value);
    else if (value.startsWith("'") && value.endsWith("'")) {
      value = value.slice(1, -1).replaceAll("''", "'");
    }
    values.push(value);
  }
  assert.ok(values.length > 0, `manifest list is empty: ${packageId}:${field}`);
  return values;
};

const validateActiveManifestBinding = (options = {}) => {
  const binding = options.binding ?? readJson(ACTIVE_BINDING_PATH);
  assertReference(ACTIVE_BINDING_PATH);
  assert.match(binding.binding_id, /^DMB-EF4-[0-9]{8}-[0-9]{3}$/u);
  assert.equal(binding.binding_type, "active_source_binding");
  assert.equal(binding.active_source_binding, true);
  assert.equal(binding.source_path, "manifests/development_manifest.yaml");
  assert.match(binding.patch_plan_id, /^MP-EF4-[A-Z][0-9]{2}-[A-Z0-9-]+-[0-9]{8}-[0-9]{3}$/u);
  assertReference(binding.patch_plan_path);
  assert.match(binding.supersedes_binding_id, /^DMB-EF4-[0-9]{8}-[0-9]{3}$/u);
  assert.match(binding.supersedes_binding_hash, /^sha256:[0-9a-f]{64}$/u);
  assertReference(binding.superseded_binding_evidence_path);
  assert.match(binding.reconciliation_binding_id, /^DMBR-EF4-[A-Z0-9-]+-[0-9]{8}-[0-9]{3}$/u);
  assertReference(binding.reconciliation_binding_path);
  assert.match(binding.parent_sha256, /^[0-9a-f]{64}$/u);
  assert.match(binding.successor_sha256, /^[0-9a-f]{64}$/u);
  assert.match(binding.patch_plan_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.match(binding.binding_hash, /^sha256:[0-9a-f]{64}$/u);
  assert.equal(
    binding.binding_hash,
    canonicalHashExcluding(binding, "binding_hash"),
    "active binding self-hash mismatch",
  );
  assert.equal(
    sha256(binding.source_path),
    binding.successor_sha256,
    "active manifest does not match the bound successor",
  );

  const patchPlan = options.patchPlan ?? readJson(binding.patch_plan_path);
  assert.equal(patchPlan.patch_plan_id, binding.patch_plan_id);
  assert.equal(patchPlan.source_path, binding.source_path);
  assert.equal(patchPlan.parent_sha256, binding.parent_sha256);
  assert.equal(patchPlan.successor_sha256, binding.successor_sha256);
  assert.equal(patchPlan.patch_plan_hash, binding.patch_plan_hash);
  assert.equal(
    patchPlan.patch_plan_hash,
    canonicalHashExcluding(patchPlan, "patch_plan_hash"),
    "patch plan self-hash mismatch",
  );
  assert.equal(patchPlan.parent_hash_verification.status, "PASS");
  assert.equal(
    patchPlan.parent_hash_verification.observed_sha256,
    binding.parent_sha256,
  );
  assert.equal(
    typeof patchPlan.parent_hash_verification.observed_before_patch,
    "boolean",
  );
  if (patchPlan.parent_hash_verification.observed_before_patch === false) {
    assert.equal(
      patchPlan.parent_hash_verification.verification_source,
      "superseded_active_binding_successor",
    );
  }
  assert.deepEqual(patchPlan.static_dependency_changes, []);
  assert.deepEqual(binding.static_dependency_changes, []);
  assert.equal(patchPlan.operation_count, patchPlan.operations.length);
  assert.deepEqual(patchPlan.changed_package_ids, binding.changed_package_ids);
  assert.deepEqual(patchPlan.changed_fields, binding.changed_fields);
  assert.deepEqual(patchPlan.attempt_level_reconciliation, binding.attempt_level_reconciliation);

  const manifestSource = readText(binding.source_path);
  const operationFields = {};
  const operationKeys = new Set();
  for (const operation of patchPlan.operations) {
    assert.equal(operation.op, "replace");
    assert.match(operation.replacement_value_hash, /^sha256:[0-9a-f]{64}$/u);
    const operationKey = `${operation.package_id}:${operation.field}`;
    assert.equal(operationKeys.has(operationKey), false, `duplicate patch operation ${operationKey}`);
    operationKeys.add(operationKey);
    operationFields[operation.package_id] ??= [];
    operationFields[operation.package_id].push(operation.field);
    const liveValue = parseManifestStringList(
      manifestSource,
      operation.package_id,
      operation.field,
    );
    assert.equal(
      operation.replacement_value_hash,
      canonicalHash(liveValue),
      `live manifest replacement hash mismatch: ${operationKey}`,
    );
  }
  assert.deepEqual(operationFields, binding.changed_fields);
  assert.deepEqual(Object.keys(operationFields), binding.changed_package_ids);

  assert.ok(binding.authorizing_decision_ids.length > 0);
  assert.equal(
    new Set(binding.authorizing_decision_ids).size,
    binding.authorizing_decision_ids.length,
    "duplicate authorizing decision",
  );
  assert.deepEqual(patchPlan.authorizing_decision_ids, binding.authorizing_decision_ids);
  const decisions = [];
  for (const decisionId of binding.authorizing_decision_ids) {
    const decisionPath = `artifacts/authority_decisions/${decisionId}.human-decision.json`;
    assertReference(decisionPath);
    const decision = options.decisionOverrides?.[decisionId] ?? readJson(decisionPath);
    assert.equal(decision.decision_id, decisionId);
    assert.equal(decision.decision_type, "correct");
    assert.equal(decision.authority_role, "product_owner");
    assert.equal(decision.non_mutation_acknowledgement, true);
    assert.match(decision.decision_hash, /^sha256:[0-9a-f]{64}$/u);
    assert.equal(
      decision.decision_hash,
      canonicalHashExcluding(decision, "decision_hash"),
      `HumanDecision self-hash mismatch: ${decisionId}`,
    );
    decisions.push(decision);
  }
  assert.ok(
    decisions.some(({ affected_artifact_ids: affected }) =>
      affected.includes(binding.patch_plan_path)
      && affected.includes(ACTIVE_BINDING_PATH)),
    "no HumanDecision authorizes the active binding and patch plan",
  );

  assert.equal(
    binding.superseded_binding_evidence_sha256,
    `sha256:${sha256(binding.superseded_binding_evidence_path)}`,
    "superseded binding evidence byte hash mismatch",
  );
  const supersededBindingEvidence = options.supersededBindingEvidence
    ?? readJson(binding.superseded_binding_evidence_path);
  assert.match(supersededBindingEvidence.attempt_id, /^S04-[0-9]{4}$/u);
  assert.equal(
    supersededBindingEvidence.active_binding.binding_id,
    binding.supersedes_binding_id,
    "superseded binding evidence binding_id mismatch",
  );
  assert.equal(
    supersededBindingEvidence.active_binding.binding_hash,
    binding.supersedes_binding_hash,
    "superseded binding evidence binding_hash mismatch",
  );
  assert.equal(
    binding.parent_sha256,
    supersededBindingEvidence.active_binding.successor_sha256.slice("sha256:".length),
    "active binding parent does not continue the superseded binding successor",
  );

  const reconciliationBinding = options.reconciliationBinding
    ?? readJson(binding.reconciliation_binding_path);
  assert.equal(reconciliationBinding.binding_id, binding.reconciliation_binding_id);
  assert.equal(reconciliationBinding.binding_type, "attempt_level_reconciliation_evidence");
  assert.equal(reconciliationBinding.active_source_binding, false);
  assert.equal(
    reconciliationBinding.parent_binding_id,
    supersededBindingEvidence.lineage.superseded_binding_id,
  );
  assert.equal(
    reconciliationBinding.parent_sha256,
    supersededBindingEvidence.lineage.superseded_successor_sha256.slice("sha256:".length),
    "reconciliation parent does not continue its historical predecessor",
  );
  assert.equal(
    reconciliationBinding.successor_sha256,
    supersededBindingEvidence.active_binding.parent_sha256.slice("sha256:".length),
    "reconciliation successor does not match the superseded binding parent",
  );
  assert.equal(reconciliationBinding.reconciliation_binding_path, undefined);
  assert.equal(
    binding.reconciliation_binding_file_sha256,
    `sha256:${sha256(binding.reconciliation_binding_path)}`,
    "reconciliation binding byte hash mismatch",
  );
  assert.equal(reconciliationBinding.binding_hash, binding.reconciliation_binding_hash);
  assert.equal(
    binding.reconciliation_binding_hash,
    supersededBindingEvidence.lineage.reconciliation_binding_hash,
  );
  assert.equal(
    reconciliationBinding.binding_hash,
    canonicalHashExcluding(reconciliationBinding, "binding_hash"),
    "reconciliation binding self-hash mismatch",
  );
  assertReference(reconciliationBinding.patch_plan_path);
  const reconciliationPatchPlan = options.reconciliationPatchPlan
    ?? readJson(reconciliationBinding.patch_plan_path);
  assert.equal(reconciliationPatchPlan.patch_plan_id, reconciliationBinding.patch_plan_id);
  assert.equal(reconciliationPatchPlan.source_path, binding.source_path);
  assert.equal(reconciliationPatchPlan.parent_sha256, reconciliationBinding.parent_sha256);
  assert.equal(reconciliationPatchPlan.successor_sha256, reconciliationBinding.successor_sha256);
  assert.equal(reconciliationPatchPlan.patch_plan_hash, reconciliationBinding.patch_plan_hash);
  assert.equal(
    reconciliationPatchPlan.patch_plan_hash,
    canonicalHashExcluding(reconciliationPatchPlan, "patch_plan_hash"),
    "reconciliation patch plan self-hash mismatch",
  );
  assert.deepEqual(reconciliationPatchPlan.static_dependency_changes, []);

  const migrationRequirement = requirementSection(
    readText("manifests/requirements_traceability.yaml"),
    "EF4-I31",
  );
  assert.match(
    migrationRequirement,
    /^  - manifests\/source_bindings\/development-manifest\.binding\.json$/mu,
    "EF4-I31 does not trace the active development-manifest binding",
  );

  return Object.freeze({
    binding_id: binding.binding_id,
    binding_hash: binding.binding_hash,
    patch_plan_id: patchPlan.patch_plan_id,
    patch_plan_hash: patchPlan.patch_plan_hash,
    successor_sha256: binding.successor_sha256,
  });
};

const parseS04Lenses = (source) => {
  const result = new Map();
  let current = null;
  for (const line of source.split(/\r?\n/u)) {
    const idMatch = /^  - id: ([A-Z][0-9]{2})$/u.exec(line);
    if (idMatch !== null) {
      current = { lens_id: idMatch[1] };
      continue;
    }
    if (current === null) continue;
    const questionMatch = /^    question: (.+)$/u.exec(line);
    if (questionMatch !== null) current.question = questionMatch[1];
    const statusMatch = /^    expected_status: (.+)$/u.exec(line);
    if (statusMatch !== null) current.expected_status = statusMatch[1];
    const ownerMatch = /^    owner_work_package: (.+)$/u.exec(line);
    if (ownerMatch !== null) {
      if (ownerMatch[1] === "S04") result.set(current.lens_id, Object.freeze({ ...current }));
      current = null;
    }
  }
  return result;
};

const parseThreatCatalog = (source) => {
  const section = source.split("## 2. Threat catalog and mandatory controls", 2)[1]
    ?.split("## 3. Hook fail-open/fail-closed matrix", 1)[0];
  assert.equal(typeof section, "string", "threat catalog section is missing");
  const threats = [];
  for (const line of section.split(/\r?\n/u)) {
    if (!line.startsWith("| ") || line.startsWith("| Threat ") || line.startsWith("|---")) continue;
    const cells = line.slice(1, -1).split("|").map((cell) => cell.trim());
    if (cells.length === 3) threats.push(cells[0]);
  }
  return threats;
};

const parseWorkPackageIds = (source) => new Set(
  [...source.matchAll(/^- id: ([A-Z][0-9]{2})$/gmu)].map((match) => match[1]),
);

const assertReference = (reference) => {
  assert.equal(typeof reference, "string");
  const separator = reference.indexOf("#");
  const relativePath = separator === -1 ? reference : reference.slice(0, separator);
  const anchor = separator === -1 ? null : reference.slice(separator + 1);
  assert.equal(path.isAbsolute(relativePath), false, reference);
  assert.equal(relativePath.split(/[\\/]/u).includes(".."), false, reference);
  const absolutePath = path.join(repositoryRoot, relativePath);
  assert.equal(fs.existsSync(absolutePath), true, reference);
  if (anchor !== null) {
    assert.notEqual(anchor.length, 0, reference);
    assert.equal(fs.readFileSync(absolutePath, "utf8").includes(anchor), true, reference);
  }
};

const traceability = readJson("artifacts/work_packages/S04/threat_model_traceability.json");

// S04-TM001
test("S04-TM001 traceability matrix covers every S04-owned audit lens without inflating deferred controls", () => {
  const canonical = parseS04Lenses(readText("manifests/216_lens_plugin_audit_matrix.yaml"));
  assert.equal(canonical.size, 24);
  assert.deepEqual([...canonical.keys()].sort(), [
    ...Array.from({ length: 12 }, (_, index) => `J${String(index + 1).padStart(2, "0")}`),
    ...Array.from({ length: 12 }, (_, index) => `M${String(index + 1).padStart(2, "0")}`),
  ]);

  const rows = new Map(traceability.lens_traceability.map((row) => [row.lens_id, row]));
  assert.equal(rows.size, traceability.lens_traceability.length, "duplicate lens traceability row");
  assert.deepEqual([...rows.keys()].sort(), [...canonical.keys()].sort());

  const allowedStatuses = new Set([
    "VERIFIED_CURRENT_BOUNDARY",
    "VERIFIED_WITH_DECLARED_LIMIT",
    "CONTRACT_ONLY_FUTURE_GATE",
    "CONDITIONAL_EXTERNAL_EVIDENCE",
  ]);
  const workPackageIds = parseWorkPackageIds(readText("manifests/development_manifest.yaml"));
  for (const [lensId, expected] of canonical) {
    const row = rows.get(lensId);
    assert.equal(row.question, expected.question, lensId);
    assert.equal(allowedStatuses.has(row.status), true, lensId);
    assert.equal(typeof row.current_claim, "string", lensId);
    assert.notEqual(row.current_claim.length, 0, lensId);
    assert.equal(typeof row.residual_limit, "string", lensId);
    assert.notEqual(row.residual_limit.length, 0, lensId);
    assert.ok(row.control_refs.length > 0, lensId);
    assert.ok(row.verification_refs.length > 0, lensId);
    for (const reference of [...row.control_refs, ...row.verification_refs]) {
      assertReference(reference);
    }
    for (const owner of row.follow_up_work_packages) {
      assert.equal(workPackageIds.has(owner), true, `${lensId}:${owner}`);
    }
    if (expected.expected_status === "CONDITIONAL") {
      assert.equal(row.status, "CONDITIONAL_EXTERNAL_EVIDENCE", lensId);
      assert.equal(row.release_claim_blocked, true, lensId);
    }
    if (["CONTRACT_ONLY_FUTURE_GATE", "CONDITIONAL_EXTERNAL_EVIDENCE"].includes(row.status)) {
      assert.equal(row.release_claim_blocked, true, lensId);
      assert.ok(row.follow_up_work_packages.length > 0, lensId);
    }
  }
});

// S04-TM002
test("S04-TM002 every plugin threat has a control, a verification path, and an honest residual limit", () => {
  const canonicalThreats = parseThreatCatalog(readText("docs/plugin_security_threat_model.md"));
  const rows = new Map(traceability.threat_traceability.map((row) => [row.threat, row]));
  assert.equal(rows.size, traceability.threat_traceability.length, "duplicate threat row");
  assert.deepEqual([...rows.keys()].sort(), [...canonicalThreats].sort());

  const allowedStatuses = new Set([
    "VERIFIED_CURRENT_BOUNDARY",
    "VERIFIED_WITH_DECLARED_LIMIT",
    "CONTRACT_ONLY_FUTURE_GATE",
  ]);
  const workPackageIds = parseWorkPackageIds(readText("manifests/development_manifest.yaml"));
  for (const threat of canonicalThreats) {
    const row = rows.get(threat);
    assert.equal(allowedStatuses.has(row.status), true, threat);
    assert.ok(row.control_refs.length > 0, threat);
    assert.ok(row.verification_refs.length > 0, threat);
    assert.equal(typeof row.residual_limit, "string", threat);
    assert.notEqual(row.residual_limit.length, 0, threat);
    for (const reference of [...row.control_refs, ...row.verification_refs]) {
      assertReference(reference);
    }
    for (const owner of row.follow_up_work_packages) {
      assert.equal(workPackageIds.has(owner), true, `${threat}:${owner}`);
    }
  }
  assert.equal(traceability.current_scope_critical_findings.length, 0);
  assert.equal(traceability.current_scope_noncritical_findings.length, 1);
  const openFinding = traceability.current_scope_noncritical_findings[0];
  assert.equal(openFinding.finding_id, "S04-NF001");
  assert.equal(openFinding.severity, "HIGH");
  assert.equal(openFinding.disposition, "DECLARED_LIMIT_FOLLOW_UP");
  assert.equal(openFinding.release_claim_blocked, true);
  assert.deepEqual(openFinding.follow_up_work_packages, ["T04", "Z01", "Z04"]);
  for (const owner of openFinding.follow_up_work_packages) {
    assert.equal(workPackageIds.has(owner), true, `${openFinding.finding_id}:${owner}`);
  }
});

// S04-TM003
test("S04-TM003 hook bypass and primitive enforcement limitations are explicit and release-safe", () => {
  const limitations = new Map(
    traceability.hook_bypass_limitations.map((entry) => [entry.limitation_id, entry]),
  );
  assert.deepEqual([...limitations.keys()].sort(), [
    "effect_time_adapters_are_future_scope",
    "hooks_are_guardrails_not_enforcement",
    "hosted_paths_may_be_unobserved",
    "primitives_are_not_an_os_sandbox",
    "receipts_dns_and_quotas_are_not_implemented_here",
  ]);
  for (const entry of limitations.values()) {
    assert.equal(typeof entry.statement, "string");
    assert.ok(entry.statement.length > 40);
    assert.equal(typeof entry.consequence, "string");
    assert.ok(entry.consequence.length > 20);
    assert.ok(entry.follow_up_work_packages.length > 0);
  }

  assert.deepEqual(traceability.assurance_claims, {
    production_security_qualified: false,
    external_penetration_test_completed: false,
    all_hosted_tool_paths_observed: false,
    os_or_container_sandbox_implemented: false,
    effect_time_receipts_complete: false,
    s01_s03_boundary_red_team_passed: true,
  });
  assert.ok(traceability.release_blockers.some(({ lens_id: lensId }) => lensId === "J12"));
  assert.ok(traceability.release_blockers.some(({ lens_id: lensId }) => lensId === "M12"));
});

// S04-TM004
test("S04-TM004 traceability source bindings fail on undocumented contract drift", () => {
  assert.equal(traceability.schema_version, 1);
  assert.equal(traceability.work_package_id, "S04");
  assert.equal(traceability.dependencies.S02, "PASS");
  assert.equal(traceability.dependencies.S03, "PASS");
  const historicalManifestBindings = traceability.source_bindings.filter(
    ({ path: sourcePath }) => sourcePath === "manifests/development_manifest.yaml",
  );
  assert.equal(historicalManifestBindings.length, 1);
  assert.match(historicalManifestBindings[0].sha256, /^[0-9a-f]{64}$/u);
  for (const binding of traceability.source_bindings.filter(
    ({ path: sourcePath }) => sourcePath !== "manifests/development_manifest.yaml",
  )) {
    assertReference(binding.path);
    assert.match(binding.sha256, /^[0-9a-f]{64}$/u);
    assert.equal(sha256(binding.path), binding.sha256, binding.path);
  }

  const activeBinding = readJson(ACTIVE_BINDING_PATH);
  const patchPlan = readJson(activeBinding.patch_plan_path);
  assert.deepEqual(validateActiveManifestBinding({ binding: activeBinding, patchPlan }), {
    binding_id: activeBinding.binding_id,
    binding_hash: activeBinding.binding_hash,
    patch_plan_id: activeBinding.patch_plan_id,
    patch_plan_hash: patchPlan.patch_plan_hash,
    successor_sha256: activeBinding.successor_sha256,
  });

  const tamperedSuccessor = withCanonicalHash(
    { ...activeBinding, successor_sha256: "0".repeat(64) },
    "binding_hash",
  );
  assert.throws(
    () => validateActiveManifestBinding({ binding: tamperedSuccessor, patchPlan }),
    /bound successor/u,
  );

  assert.throws(
    () => validateActiveManifestBinding({
      binding: { ...activeBinding, binding_hash: `sha256:${"0".repeat(64)}` },
      patchPlan,
    }),
    /active binding self-hash mismatch/u,
  );

  assert.throws(
    () => validateActiveManifestBinding({
      binding: activeBinding,
      patchPlan: { ...patchPlan, operation_count: patchPlan.operation_count + 1 },
    }),
    /patch plan self-hash mismatch/u,
  );

  const tamperedOperations = patchPlan.operations.map((operation, index) => (
    index === 0
      ? { ...operation, replacement_value_hash: `sha256:${"0".repeat(64)}` }
      : operation
  ));
  const tamperedReplacementHashPlan = withCanonicalHash(
    { ...patchPlan, operations: tamperedOperations },
    "patch_plan_hash",
  );
  const tamperedReplacementHashBinding = withCanonicalHash(
    {
      ...activeBinding,
      patch_plan_hash: tamperedReplacementHashPlan.patch_plan_hash,
    },
    "binding_hash",
  );
  assert.throws(
    () => validateActiveManifestBinding({
      binding: tamperedReplacementHashBinding,
      patchPlan: tamperedReplacementHashPlan,
    }),
    /live manifest replacement hash mismatch/u,
  );

  const decisionId = activeBinding.authorizing_decision_ids[0];
  const decision = readJson(
    `artifacts/authority_decisions/${decisionId}.human-decision.json`,
  );
  assert.throws(
    () => validateActiveManifestBinding({
      binding: activeBinding,
      patchPlan,
      decisionOverrides: {
        [decisionId]: { ...decision, rationale: `${decision.rationale} tampered` },
      },
    }),
    /HumanDecision self-hash mismatch/u,
  );

  const reconciliationBinding = readJson(activeBinding.reconciliation_binding_path);
  assert.throws(
    () => validateActiveManifestBinding({
      binding: activeBinding,
      patchPlan,
      reconciliationBinding: {
        ...reconciliationBinding,
        successor_sha256: "0".repeat(64),
      },
    }),
    /reconciliation successor|self-hash mismatch/u,
  );

  const supersededBindingEvidence = readJson(activeBinding.superseded_binding_evidence_path);
  assert.throws(
    () => validateActiveManifestBinding({
      binding: activeBinding,
      patchPlan,
      supersededBindingEvidence: {
        ...supersededBindingEvidence,
        active_binding: {
          ...supersededBindingEvidence.active_binding,
          binding_hash: `sha256:${"0".repeat(64)}`,
        },
      },
    }),
    /binding_hash|supersedes_binding_hash/u,
  );
});
