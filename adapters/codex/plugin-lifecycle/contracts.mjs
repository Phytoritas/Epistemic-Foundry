import path from "node:path";
import {
  FAILURE,
  LIMITS,
  STATUS,
  LifecycleError,
  boundedJson,
  exactFields,
  fail,
  hashJson,
  isPlainObject,
  makeResult,
} from "./core.mjs";

function stableCapabilityId(value, label) {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value !== value.normalize("NFC") ||
    value.trim() !== value ||
    /[\u0000-\u001f\u007f]/u.test(value) ||
    Buffer.byteLength(value, "utf8") > 512
  ) fail(FAILURE.HOST_UNSUPPORTED, `${label} capability identity is invalid`, STATUS.UNSUPPORTED);
  return value;
}

function optionalCapabilityId(port, label) {
  if (port === null) return null;
  if ((typeof port !== "object" && typeof port !== "function") || port === null) {
    fail(FAILURE.HOST_UNSUPPORTED, `${label} port is invalid`, STATUS.UNSUPPORTED);
  }
  return stableCapabilityId(port.capability_id, label);
}

export function callCapabilityPort(port, method, payload, label) {
  if (!isPlainObject(port) || typeof port[method] !== "function") {
    fail(FAILURE.HOST_UNSUPPORTED, `${label} capability is unavailable`, STATUS.UNSUPPORTED);
  }
  let value;
  try {
    value = port[method](boundedJson(payload, `${label} input`));
  } catch {
    fail(FAILURE.HOST_UNSUPPORTED, `${label} capability failed`, STATUS.UNSUPPORTED);
  }
  if (value?.then !== undefined) fail(FAILURE.HOST_UNSUPPORTED, `${label} capability is asynchronous`, STATUS.UNSUPPORTED);
  return boundedJson(value, `${label} output`);
}

export function qualifyComposition(config) {
  if (
    !isPlainObject(config.privateRootPort) ||
    typeof config.privateRootPort.qualify !== "function" ||
    typeof config.privateRootPort.revalidate !== "function"
  ) fail(FAILURE.HOST_UNSUPPORTED, "private root capability is unavailable", STATUS.UNSUPPORTED);
  const privateRootCapabilityId = optionalCapabilityId(config.privateRootPort, "private root");
  const dataSnapshotCapabilityId = optionalCapabilityId(config.dataSnapshotPort, "data snapshot");
  const quiescenceCapabilityId = optionalCapabilityId(config.quiescencePort, "quiescence");
  const commandCapabilityId = config.commandPortInjected
    ? optionalCapabilityId(config.commandPort, "command")
    : null;
  const conditionalMutationCapabilityId = config.commandPort.conditional_mutation_capability_id == null
    ? null
    : stableCapabilityId(config.commandPort.conditional_mutation_capability_id, "conditional mutation");
  const migrationCapabilityId = optionalCapabilityId(config.migrationPort, "migration");
  const trustCapabilityId = optionalCapabilityId(config.trustPort, "trust");
  const verificationCapabilityId = optionalCapabilityId(config.verificationPort, "verification");
  const hostEnvironmentRoots = Object.fromEntries(
    Object.entries(config.envRoots)
      .filter(([key]) => key !== "PLUGIN_DATA")
      .map(([key, value]) => [key, { path: value.path, filesystem_id: value.filesystem_id }]),
  );
  const hostEnvironmentHash = hashJson("PLUGIN_LIFECYCLE_V3_HOST_ENVIRONMENT", config.env);
  const rootsHash = hashJson("PLUGIN_LIFECYCLE_V3_ROOT_SET", {
    codex_executable: config.executable.path,
    codex_executable_hash: config.executable.content_hash,
    lifecycle_root: config.lifecycleRoot,
    plugin_data_root: config.pluginDataRoot,
    codex_home: config.codexHome,
    codex_home_filesystem_id: config.codexHomeIdentity,
    cwd: config.cwd,
    cwd_filesystem_id: config.cwdIdentity,
    host_environment_hash: hostEnvironmentHash,
    host_environment_roots: hostEnvironmentRoots,
  });
  const privateRaw = callCapabilityPort(
    config.privateRootPort,
    "qualify",
    {
      lifecycle_root: config.lifecycleRoot,
      roots_hash: rootsHash,
      required_guarantee: "OWNER_ONLY_LOCAL_PRIVATE_STORAGE",
    },
    "private root",
  );
  exactFields(privateRaw, ["status", "lifecycle_root", "roots_hash", "capability_id", "receipt_hash"], "private root qualification");
  if (
    privateRaw.status !== "PROTECTED_LOCAL" ||
    privateRaw.lifecycle_root !== config.lifecycleRoot ||
    privateRaw.roots_hash !== rootsHash ||
    privateRaw.capability_id !== privateRootCapabilityId ||
    privateRaw.receipt_hash !== hashJson("PLUGIN_LIFECYCLE_V3_PRIVATE_ROOT_RECEIPT", {
      status: privateRaw.status,
      lifecycle_root: privateRaw.lifecycle_root,
      roots_hash: privateRaw.roots_hash,
      capability_id: privateRaw.capability_id,
    })
  ) fail(FAILURE.HOST_UNSUPPORTED, "private root protection cannot be established", STATUS.UNSUPPORTED);

  const dataRaw = callCapabilityPort(
    config.dataSnapshotPort,
    "qualify",
    {
      plugin_data_root: config.pluginDataRoot,
      required_guarantee: "FULL_FILESYSTEM_BYTE_METADATA_SNAPSHOT",
      max_entries: LIMITS.maxEntries,
      max_total_bytes: LIMITS.maxTreeBytes,
      max_file_bytes: LIMITS.maxFileBytes,
    },
    "data snapshot",
  );
  exactFields(
    dataRaw,
    [
      "status",
      "plugin_data_root",
      "capability_id",
      "max_entries",
      "max_total_bytes",
      "max_file_bytes",
      "receipt_hash",
    ],
    "data snapshot qualification",
  );
  if (
    dataRaw.status !== "FULL_FILESYSTEM_SNAPSHOT" ||
    dataRaw.plugin_data_root !== config.pluginDataRoot ||
    dataRaw.capability_id !== dataSnapshotCapabilityId ||
    dataRaw.max_entries !== LIMITS.maxEntries ||
    dataRaw.max_total_bytes !== LIMITS.maxTreeBytes ||
    dataRaw.max_file_bytes !== LIMITS.maxFileBytes ||
    dataRaw.receipt_hash !== hashJson("PLUGIN_LIFECYCLE_V3_DATA_CAPABILITY_RECEIPT", {
      status: dataRaw.status,
      plugin_data_root: dataRaw.plugin_data_root,
      capability_id: dataRaw.capability_id,
      max_entries: dataRaw.max_entries,
      max_total_bytes: dataRaw.max_total_bytes,
      max_file_bytes: dataRaw.max_file_bytes,
    })
  ) fail(FAILURE.HOST_UNSUPPORTED, "full-filesystem data snapshots cannot be established", STATUS.UNSUPPORTED);
  if (!quiescencePortReady(config.quiescencePort)) {
    fail(FAILURE.HOST_UNSUPPORTED, "qualified quiescence capability identity is unavailable", STATUS.UNSUPPORTED);
  }
  const binding = boundedJson(
    {
      lifecycle_root: {
        path: config.lifecycleRoot,
        capability_id: privateRaw.capability_id,
        roots_hash: privateRaw.roots_hash,
      },
      codex_home: {
        path: config.codexHome,
        filesystem_id: config.codexHomeIdentity,
      },
      plugin_data: {
        path: config.pluginDataRoot,
        capability_id: dataRaw.capability_id,
      },
      codex_executable: {
        path: config.executable.path,
        content_hash: config.executable.content_hash,
        signature: config.executable.signature,
      },
      cwd: {
        path: config.cwd,
        filesystem_id: config.cwdIdentity,
      },
      host_environment_hash: hostEnvironmentHash,
      host_environment_roots: hostEnvironmentRoots,
      command_capability_id: commandCapabilityId,
      conditional_mutation_capability_id: conditionalMutationCapabilityId,
      migration_capability_id: migrationCapabilityId,
      trust_capability_id: trustCapabilityId,
      verification_capability_id: verificationCapabilityId,
      quiescence_capability_id: quiescenceCapabilityId,
    },
    "runtime composition binding",
  );
  return Object.freeze({
    privateRoot: privateRaw,
    dataSnapshot: dataRaw,
    capabilityIds: Object.freeze({
      privateRoot: privateRootCapabilityId,
      dataSnapshot: dataSnapshotCapabilityId,
      quiescence: quiescenceCapabilityId,
      command: commandCapabilityId,
      conditionalMutation: conditionalMutationCapabilityId,
      migration: migrationCapabilityId,
      trust: trustCapabilityId,
      verification: verificationCapabilityId,
    }),
    binding: Object.freeze(binding),
    bindingHash: hashJson("PLUGIN_LIFECYCLE_V3_COMPOSITION_BINDING", binding),
  });
}

export function unsupportedCompositionPort(cause) {
  const known = cause instanceof LifecycleError;
  const failure = known ? cause.code : FAILURE.HOST_UNSUPPORTED;
  const requiredCapabilities = [
    "privateRootPort.capability_id/qualify/revalidate",
    "dataSnapshotPort.capability_id/qualify/capture/compare/restore/reconcile/dispose",
    "quiescencePort.capability_id/acquire/revalidate/renew/recover/release/reconcile",
    "capability_id on each injected command/migration/trust/verification port",
    "commandPort.conditional_mutation_capability_id for destructive lifecycle calls",
    "verificationPort.health/replay/integrity",
  ];
  const method = (operation) => makeResult(operation, {
    ok: false,
    status: known ? cause.status : STATUS.UNSUPPORTED,
    code: failure,
    rolled_back: false,
    data: failure !== FAILURE.HOST_UNSUPPORTED
      ? null
      : operation === "probeHost"
        ? {
            host: "codex_cli",
            host_version: null,
            version_pinned_activation: false,
            mode: "UNSUPPORTED",
            capabilities: {
              exact_selector_lifecycle: { state: "UNASSESSED" },
              version_pinned_activation: { state: "UNSUPPORTED" },
              atomic_upgrade: { state: "UNSUPPORTED" },
              crash_idempotent_migration: { state: "UNASSESSED" },
              quiescent_data_ownership: { state: "UNASSESSED" },
              full_filesystem_data_snapshot: { state: "UNSUPPORTED" },
              protected_private_state: { state: "UNSUPPORTED" },
              installed_verification: { state: "UNASSESSED" },
            },
            required_capabilities: requiredCapabilities,
          }
        : { required_capabilities: requiredCapabilities },
  }, null);
  const close = () => makeResult(
    "close",
    { ok: true, status: STATUS.IDLE, code: null, message: "Lifecycle port was closed." },
    null,
  );
  return Object.freeze({
    probeHost: () => method("probeHost"),
    capture: () => method("capture"),
    prepare: () => method("prepare"),
    activate: () => method("activate"),
    verify: () => method("verify"),
    rollback: () => method("rollback"),
    uninstall: () => method("uninstall"),
    cancel: () => method("cancel"),
    finalize: () => method("finalize"),
    cleanup: () => method("cleanup"),
    close,
    dispose: close,
  });
}

export function sameAbsolutePath(left, right) {
  const a = path.resolve(left).normalize("NFC");
  const b = path.resolve(right).normalize("NFC");
  return process.platform === "win32" || process.platform === "darwin"
    ? a.toLowerCase() === b.toLowerCase()
    : a === b;
}

export function publicPackage(record) {
  if (record === null) return null;
  return {
    package_hash: record.package_hash,
    plugin_name: record.plugin_name,
    plugin_version: record.plugin_version,
    manifest_hash: record.manifest_hash,
    has_hooks: record.has_hooks === 1 || record.has_hooks === true,
    hook_subject_hash: record.hook_subject_hash,
    file_count: record.file_count,
    byte_size: record.byte_size,
  };
}

export function parseMigrationPlan(value, candidateHash, previousHash) {
  if (value === undefined || value === null) return null;
  exactFields(
    value,
    ["plan_id", "from_package_hash", "to_package_hash", "rollback_operation", "steps", "plan_hash"],
    "migration_plan",
  );
  const closed = boundedJson(
    {
      plan_id: value.plan_id,
      from_package_hash: value.from_package_hash,
      to_package_hash: value.to_package_hash,
      rollback_operation: value.rollback_operation,
      steps: value.steps,
    },
    "migration plan",
  );
  if (
    typeof closed.plan_id !== "string" ||
    closed.plan_id.length === 0 ||
    typeof closed.rollback_operation !== "string" ||
    closed.rollback_operation.length === 0 ||
    closed.from_package_hash !== previousHash ||
    closed.to_package_hash !== candidateHash ||
    !Array.isArray(closed.steps)
  ) fail(FAILURE.INVALID_INPUT, "migration plan package binding is invalid");
  const expected = hashJson("PLUGIN_LIFECYCLE_V3_MIGRATION_PLAN", closed);
  if (value.plan_hash !== expected) fail(FAILURE.INVALID_INPUT, "migration plan hash does not match its closed plan");
  return { ...closed, plan_hash: expected };
}

export function migrationPortReady(port) {
  return isPlainObject(port) &&
    typeof port.capability_id === "string" &&
    port.capability_id.length > 0 &&
    ["apply", "rollback", "reconcile", "verifyCompatible"].every(
    (name) => typeof port[name] === "function",
  );
}

export function quiescencePortReady(port) {
  return isPlainObject(port) &&
    typeof port.capability_id === "string" &&
    port.capability_id.length > 0 &&
    ["acquire", "revalidate", "renew", "recover", "release", "reconcile"].every(
      (name) => typeof port[name] === "function",
    );
}

export function dataSnapshotPortReady(port) {
  return isPlainObject(port) &&
    typeof port.capability_id === "string" &&
    port.capability_id.length > 0 &&
    ["qualify", "capture", "compare", "restore", "reconcile", "dispose"].every(
    (name) => typeof port[name] === "function",
  );
}

export function validateMigrationReceipt(value, { operationId, ownerEpoch, effectId, planHash, phase }) {
  const receipt = boundedJson(value, "migration receipt");
  exactFields(
    receipt,
    ["operation_id", "owner_epoch", "effect_id", "plan_hash", "phase", "status", "receipt_hash"],
    "migration receipt",
  );
  const preimage = {
    operation_id: receipt.operation_id,
    owner_epoch: receipt.owner_epoch,
    effect_id: receipt.effect_id,
    plan_hash: receipt.plan_hash,
    phase: receipt.phase,
    status: receipt.status,
  };
  if (
    receipt.operation_id !== operationId ||
    receipt.owner_epoch !== ownerEpoch ||
    receipt.effect_id !== effectId ||
    receipt.plan_hash !== planHash ||
    receipt.phase !== phase ||
    !["APPLIED", "ROLLED_BACK", "COMPATIBLE", "NOT_APPLIED"].includes(receipt.status) ||
    receipt.receipt_hash !== hashJson("PLUGIN_LIFECYCLE_V3_MIGRATION_RECEIPT", preimage)
  ) fail(FAILURE.MIGRATION_RECEIPT_INVALID, "migration receipt is not resolving or operation-bound");
  return receipt;
}

export function marketplaceDocument(name, pluginName) {
  return {
    name,
    interface: { displayName: "Epistemic Foundry lifecycle marketplace" },
    plugins: [
      {
        name: pluginName,
        source: { source: "local", path: `./plugins/${pluginName}` },
        policy: { installation: "AVAILABLE", authentication: "ON_INSTALL" },
        category: "Research",
      },
    ],
  };
}
