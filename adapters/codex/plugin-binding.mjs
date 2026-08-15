// Read-and-verify: does the shipped payload actually bind to the Codex host?
//
// Nothing here rewrites the payload.  `plugins/epistemic-foundry` is read as it
// ships — its manifest, its hook registrations, its dispatcher — and every claim
// it makes is checked against a source that is entitled to make it: the hook
// gateway declares the event types, the hosts and the coverage classes; the
// payload declares its own files; `adapters/codex/codex-binding.json` declares
// which of those the adapter binds.
//
// Two kinds of outcome are kept apart on purpose.  A declaration that contradicts
// a declaring source is a refusal: the binding is wrong and must not be reported
// as anything else.  A declared runtime target that is not built at this
// revision is a finding, and the binding is DEGRADED — the payload is what it
// says it is, and the part of it that cannot run is named rather than implied.

import { readFileSync, realpathSync } from "node:fs";
import { isAbsolute, join, posix, relative, sep, win32 } from "node:path";

import {
  HOOK_COVERAGE,
  HOOK_EVENT_TYPES,
  HOOK_HOSTS,
  sha256HookJson,
} from "../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";
import {
  BINDING_DECLARATION_PATH,
  BINDING_STATUS,
  CodexAdapterError,
  deepFreeze,
  fail,
  isPlainObject,
  PAYLOAD_ROOT,
  pathExists,
  PLUGIN_MANIFEST_PATH,
  readBytes,
  readJson,
  readText,
  REPOSITORY_ROOT,
  requireCanonicalStrings,
  requireFields,
  ROLE_MAPPING_PATH,
  ROLE_REGISTRY_PATH,
  selectDeclared,
  sha256,
} from "./codex-declarations.mjs";
import { buildRoleDescriptorTable, roleTableHash } from "./role-adapter.mjs";

/** The fields `adapters/codex/codex-binding.json` must declare, exactly. */
export const DECLARATION_FIELDS = Object.freeze([
  "adapter_id",
  "adapter_version",
  "coverage_restricted",
  "coverage_unregistered",
  "coverage_unrestricted",
  "declared_host",
  "descriptor_name_prefix",
  "dispatcher",
  "entrypoints",
  "hook_files",
  "manifest_asset_fields",
  "plugin_name",
  "unrestricted_matchers",
]);

const REGISTRATION_FIELDS = Object.freeze(["command", "statusMessage", "timeout", "type"]);
const COMMAND_PATTERN = /^node "\$\{PLUGIN_ROOT\}\/([^"]+)" ([a-z][a-z0-9-]*)$/u;

const requirePayloadRelativePath = (candidate, label, code) => {
  if (
    typeof candidate !== "string" ||
    candidate.length === 0 ||
    candidate.includes("\\") ||
    candidate.includes("\0") ||
    posix.isAbsolute(candidate) ||
    win32.isAbsolute(candidate) ||
    /^[A-Za-z]:/u.test(candidate)
  ) {
    fail(code, `${label} must be a payload-relative POSIX path`, { path: candidate });
  }
  const normalized = posix.normalize(candidate);
  if (
    normalized !== candidate ||
    normalized === "." ||
    normalized === ".." ||
    normalized.startsWith("../")
  ) {
    fail(code, `${label} escapes or is not canonical within the payload`, {
      normalized,
      path: candidate,
    });
  }
  return normalized;
};

const resolvePayloadFile = (root, relativePath, label, code) => {
  const canonical = requirePayloadRelativePath(relativePath, label, code);
  const logicalPath = posix.join(PAYLOAD_ROOT, canonical);
  if (!pathExists(root, logicalPath)) return null;
  try {
    const payloadRoot = realpathSync(join(root, PAYLOAD_ROOT));
    const actualPath = realpathSync(join(root, logicalPath));
    const fromPayload = relative(payloadRoot, actualPath);
    if (
      fromPayload === "" ||
      fromPayload === ".." ||
      fromPayload.startsWith(`..${sep}`) ||
      isAbsolute(fromPayload)
    ) {
      fail(code, `${label} resolves outside the payload`, {
        path: relativePath,
      });
    }
    return actualPath;
  } catch (error) {
    if (error instanceof CodexAdapterError) throw error;
    fail(code, `${label} cannot be resolved inside the payload: ${error.message}`, {
      path: relativePath,
    });
  }
};

const payloadFileExists = (root, relativePath, label, code) =>
  resolvePayloadFile(root, relativePath, label, code) !== null;

const readPayloadBytes = (root, relativePath, label, code) => {
  const actualPath = resolvePayloadFile(root, relativePath, label, code);
  if (actualPath === null) {
    fail(code, `${label} is missing from the payload`, { path: relativePath });
  }
  try {
    return readFileSync(actualPath);
  } catch (error) {
    fail(code, `${label} cannot be read from the payload: ${error.message}`, {
      path: relativePath,
    });
  }
};

const readDeclaration = (root) => {
  const declaration = requireFields(
    readJson(root, BINDING_DECLARATION_PATH, "DECLARATION_NONCANONICAL"),
    DECLARATION_FIELDS,
    "binding declaration",
    "DECLARATION_NONCANONICAL",
  );
  for (const key of ["entrypoints", "hook_files", "manifest_asset_fields", "unrestricted_matchers"]) {
    requireCanonicalStrings(declaration[key], `declaration.${key}`, "DECLARATION_NONCANONICAL");
  }
  for (const key of [
    "adapter_id",
    "adapter_version",
    "declared_host",
    "descriptor_name_prefix",
    "dispatcher",
    "plugin_name",
  ]) {
    if (typeof declaration[key] !== "string" || declaration[key].length === 0) {
      fail("DECLARATION_NONCANONICAL", `declaration.${key} must be a non-empty string`, { key });
    }
  }
  for (const key of ["entrypoints", "hook_files"]) {
    for (const relativePath of declaration[key]) {
      requirePayloadRelativePath(
        relativePath,
        `declaration.${key}`,
        "DECLARATION_NONCANONICAL",
      );
    }
  }
  requirePayloadRelativePath(
    declaration.dispatcher,
    "declaration.dispatcher",
    "DECLARATION_NONCANONICAL",
  );
  if (!declaration.entrypoints.includes(declaration.dispatcher)) {
    fail("DECLARATION_NONCANONICAL", "the declared dispatcher is not a declared entrypoint", {
      dispatcher: declaration.dispatcher,
      entrypoints: [...declaration.entrypoints],
    });
  }
  return deepFreeze(declaration);
};

const readManifest = (root, declaration) => {
  const manifest = readJson(root, PLUGIN_MANIFEST_PATH, "MANIFEST_UNREADABLE");
  if (!isPlainObject(manifest)) {
    fail("MANIFEST_UNREADABLE", `${PLUGIN_MANIFEST_PATH} is not a JSON object`);
  }
  if (typeof manifest.version !== "string" || manifest.version.length === 0) {
    fail("MANIFEST_UNREADABLE", `${PLUGIN_MANIFEST_PATH} declares no version`);
  }
  if (manifest.name !== declaration.plugin_name) {
    fail("PLUGIN_NAME_DRIFT", `${PLUGIN_MANIFEST_PATH} names a different package`, {
      declared: declaration.plugin_name,
      manifest: manifest.name,
    });
  }
  return manifest;
};

/**
 * The manifest-declared asset paths, resolved against the payload root.
 *
 * The manifest writes them as `./assets/logo.svg`; a field the manifest does not
 * declare, or declares as something other than a payload-relative path, is a
 * missing entrypoint rather than an absent one.
 */
const resolveDeclaredEntrypoints = (root, declaration, manifest) => {
  const resolved = [];
  for (const relative of declaration.entrypoints) {
    if (!payloadFileExists(root, relative, "declared entrypoint", "ENTRYPOINT_MISSING")) {
      fail("ENTRYPOINT_MISSING", `the payload does not ship declared entrypoint ${relative}`, {
        path: relative,
      });
    }
    resolved.push({ field: null, path: relative });
  }
  const interface_ = isPlainObject(manifest.interface) ? manifest.interface : {};
  for (const field of declaration.manifest_asset_fields) {
    const declared = interface_[field];
    if (typeof declared !== "string" || !declared.startsWith("./")) {
      fail("ENTRYPOINT_MISSING", `the manifest declares no payload-relative "${field}"`, {
        declared,
        field,
      });
    }
    const relative = requirePayloadRelativePath(
      declared.slice(2),
      `manifest.interface.${field}`,
      "ENTRYPOINT_MISSING",
    );
    if (!payloadFileExists(root, relative, `manifest asset ${field}`, "ENTRYPOINT_MISSING")) {
      fail("ENTRYPOINT_MISSING", `the payload does not ship declared asset ${relative}`, {
        field,
        path: relative,
      });
    }
    resolved.push({ field, path: relative });
  }
  resolved.sort((left, right) => (left.path < right.path ? -1 : 1));
  return resolved;
};

/**
 * The payload target the dispatcher spawns.
 *
 * `bin/efoundry.mjs` resolves its payload CLI through exactly one
 * `new URL(..., import.meta.url)`; a dispatcher that names none or several is
 * unreadable rather than assumed, because the adapter would then be reporting on
 * a binding it cannot see.
 */
export const parseDispatcherTarget = (source, dispatcherPath) => {
  const targets = [...source.matchAll(/new URL\("([^"]+)", import\.meta\.url\)/gu)].map(
    (match) => match[1],
  );
  if (targets.length !== 1) {
    fail("DISPATCHER_UNREADABLE", `${dispatcherPath} names ${targets.length} payload targets`, {
      dispatcher: dispatcherPath,
      targets,
    });
  }
  const target = targets[0];
  if (target.includes("\\") || posix.isAbsolute(target) || win32.isAbsolute(target)) {
    fail("DISPATCHER_UNREADABLE", `${dispatcherPath} names a non-relative payload target`, {
      dispatcher: dispatcherPath,
      target,
    });
  }
  return requirePayloadRelativePath(
    posix.normalize(posix.join(posix.dirname(dispatcherPath), target)),
    `${dispatcherPath} target`,
    "DISPATCHER_UNREADABLE",
  );
};

const readRegistrations = (root, declaration, eventTypes) => {
  const registrations = [];
  for (const relative of declaration.hook_files) {
    const path = posix.join(PAYLOAD_ROOT, relative);
    if (!payloadFileExists(root, relative, "declared hook file", "HOOK_FILE_MISSING")) {
      fail("HOOK_FILE_MISSING", `the payload does not ship hook registration ${relative}`, {
        path: relative,
      });
    }
    const document = requireFields(
      readJson(root, path, "HOOK_REGISTRATION_UNREADABLE"),
      ["hooks"],
      relative,
      "HOOK_REGISTRATION_UNREADABLE",
    );
    if (!isPlainObject(document.hooks) || Object.keys(document.hooks).length === 0) {
      fail("HOOK_REGISTRATION_UNREADABLE", `${relative} registers no event`, { path: relative });
    }
    for (const [eventType, groups] of Object.entries(document.hooks)) {
      selectDeclared(eventTypes, eventType, `${relative} event type`, "HOOK_EVENT_UNDECLARED");
      if (!Array.isArray(groups) || groups.length === 0) {
        fail("HOOK_REGISTRATION_UNREADABLE", `${relative}.${eventType} is not a registration list`, {
          event_type: eventType,
          path: relative,
        });
      }
      for (const group of groups) {
        if (!isPlainObject(group) || !Array.isArray(group.hooks) || group.hooks.length === 0) {
          fail("HOOK_REGISTRATION_UNREADABLE", `${relative}.${eventType} holds no hook`, {
            event_type: eventType,
            path: relative,
          });
        }
        const extra = Object.keys(group).filter((key) => key !== "hooks" && key !== "matcher");
        if (extra.length > 0) {
          fail("HOOK_REGISTRATION_UNREADABLE", `${relative}.${eventType} holds unsupported fields`, {
            event_type: eventType,
            fields: extra.sort(),
            path: relative,
          });
        }
        const matcher = Object.hasOwn(group, "matcher") ? group.matcher : null;
        if (matcher !== null && typeof matcher !== "string") {
          fail("HOOK_REGISTRATION_UNREADABLE", `${relative}.${eventType} matcher is not a string`, {
            event_type: eventType,
            path: relative,
          });
        }
        for (const hook of group.hooks) {
          requireFields(
            hook,
            REGISTRATION_FIELDS,
            `${relative}.${eventType} hook`,
            "HOOK_REGISTRATION_UNREADABLE",
          );
          const parsed = COMMAND_PATTERN.exec(String(hook.command));
          if (parsed === null || hook.type !== "command") {
            fail("HOOK_COMMAND_UNPARSEABLE", `${relative}.${eventType} holds an opaque command`, {
              command: hook.command,
              event_type: eventType,
              path: relative,
            });
          }
          const target = requirePayloadRelativePath(
            parsed[1],
            `${relative}.${eventType} hook target`,
            "HOOK_COMMAND_UNPARSEABLE",
          );
          registrations.push({
            event_type: eventType,
            hook_file: relative,
            matcher,
            target,
            verb: parsed[2],
          });
        }
      }
    }
  }
  registrations.sort((left, right) =>
    `${left.event_type} ${left.hook_file} ${left.verb}` <
    `${right.event_type} ${right.hook_file} ${right.verb}`
      ? -1
      : 1,
  );
  return registrations;
};

/**
 * verb -> event type, derived from the commands the payload actually registers.
 *
 * The hook process is invoked as `hook-runner.mjs <verb>`, so the verb is the
 * only thing a raw host event has to carry for the adapter to know which
 * canonical event type it is.  The map is read from the registrations; the
 * adapter never restates it.
 */
export const deriveVerbIndex = (registrations) => {
  const index = new Map();
  for (const row of registrations) {
    const known = index.get(row.verb);
    if (known !== undefined && known !== row.event_type) {
      fail("HOOK_VERB_AMBIGUOUS", `verb "${row.verb}" is claimed by two event types`, {
        event_types: [known, row.event_type].sort(),
        verb: row.verb,
      });
    }
    index.set(row.verb, row.event_type);
  }
  return index;
};

/**
 * How much of each canonical event type this payload can actually observe.
 *
 * A registration with no matcher, or with a matcher the declaration names as
 * unrestricted, routes every instance of its event; a restricting matcher routes
 * only some.  An event type no registration claims is not observed at all, and
 * saying so is the point: the gap is published, not assumed away.
 */
export const deriveCoverage = (declaration, registrations, eventTypes, coverageClasses) => {
  const unrestricted = selectDeclared(
    coverageClasses,
    declaration.coverage_unrestricted,
    "declaration.coverage_unrestricted",
    "COVERAGE_UNDECLARED",
  );
  const restricted = selectDeclared(
    coverageClasses,
    declaration.coverage_restricted,
    "declaration.coverage_restricted",
    "COVERAGE_UNDECLARED",
  );
  const unregistered = selectDeclared(
    coverageClasses,
    declaration.coverage_unregistered,
    "declaration.coverage_unregistered",
    "COVERAGE_UNDECLARED",
  );
  const coverage = new Map();
  for (const eventType of eventTypes) coverage.set(eventType, unregistered);
  for (const row of registrations) {
    const routesEverything =
      row.matcher === null || declaration.unrestricted_matchers.includes(row.matcher);
    const current = coverage.get(row.event_type);
    if (routesEverything) coverage.set(row.event_type, unrestricted);
    else if (current === unregistered) coverage.set(row.event_type, restricted);
  }
  return coverage;
};

/** Read, cross-check and freeze the whole Codex host binding. */
export const loadCodexBinding = ({ root = REPOSITORY_ROOT } = {}) => {
  const declaration = readDeclaration(root);
  const adapterHost = selectDeclared(
    HOOK_HOSTS,
    declaration.declared_host,
    "declaration.declared_host",
    "HOOK_HOST_UNDECLARED",
  );
  const manifest = readManifest(root, declaration);
  const entrypoints = resolveDeclaredEntrypoints(root, declaration, manifest);
  const registrations = readRegistrations(root, declaration, HOOK_EVENT_TYPES);
  const verbIndex = deriveVerbIndex(registrations);
  const coverage = deriveCoverage(declaration, registrations, HOOK_EVENT_TYPES, HOOK_COVERAGE);

  const dispatcherTarget = parseDispatcherTarget(
    readText(root, posix.join(PAYLOAD_ROOT, declaration.dispatcher), "DISPATCHER_UNREADABLE"),
    declaration.dispatcher,
  );

  const findings = [];
  if (!payloadFileExists(root, dispatcherTarget, "dispatcher target", "DISPATCHER_UNREADABLE")) {
    findings.push({
      code: "DISPATCHER_PAYLOAD_MISSING",
      event_types: [],
      path: dispatcherTarget,
    });
  }
  for (const target of [...new Set(registrations.map((row) => row.target))].sort()) {
    if (payloadFileExists(root, target, "hook command target", "HOOK_COMMAND_UNPARSEABLE")) {
      continue;
    }
    findings.push({
      code: "HOOK_COMMAND_TARGET_MISSING",
      event_types: [
        ...new Set(registrations.filter((row) => row.target === target).map((row) => row.event_type)),
      ].sort(),
      path: target,
    });
  }
  findings.sort((left, right) => (`${left.code} ${left.path}` < `${right.code} ${right.path}` ? -1 : 1));

  const registeredEventTypes = [...new Set(registrations.map((row) => row.event_type))].sort();
  const roleTable = buildRoleDescriptorTable({
    prefix: declaration.descriptor_name_prefix,
    root,
  });

  return deepFreeze({
    adapterHost,
    coverageByEventType: coverage,
    declaration,
    dispatcherTarget,
    entrypoints,
    eventTypeByVerb: verbIndex,
    findings,
    manifest,
    registeredEventTypes,
    registrations,
    roleTable,
    root,
    status: findings.length === 0 ? BINDING_STATUS.BOUND : BINDING_STATUS.DEGRADED,
    unregisteredEventTypes: HOOK_EVENT_TYPES.filter(
      (eventType) => !registeredEventTypes.includes(eventType),
    ).slice().sort(),
  });
};

/** The files whose bytes decide the binding, each named with its digest. */
export const BINDING_SOURCE_PATHS = Object.freeze(
  [BINDING_DECLARATION_PATH, PLUGIN_MANIFEST_PATH, ROLE_MAPPING_PATH, ROLE_REGISTRY_PATH].sort(),
);

/**
 * An immutable receipt for the binding: what was read, what bound, what did not,
 * and the hash of exactly those fields.  No clock and no randomness, so the same
 * payload always produces the same receipt and a changed input always produces a
 * different one.
 */
export const codexBindingReceipt = (binding) => {
  const dispatcherTargetPath = posix.join(PAYLOAD_ROOT, binding.dispatcherTarget);
  let dispatcherTargetBytes = null;
  const resolvedDispatcherTarget = resolvePayloadFile(
    binding.root,
    binding.dispatcherTarget,
    "dispatcher target",
    "DISPATCHER_UNREADABLE",
  );
  if (resolvedDispatcherTarget !== null) {
    try {
      dispatcherTargetBytes = readFileSync(resolvedDispatcherTarget);
    } catch (error) {
      fail("DISPATCHER_UNREADABLE", `dispatcher target cannot be read: ${error.message}`, {
        path: binding.dispatcherTarget,
      });
    }
  }
  const findings = binding.findings.filter(
    (finding) =>
      finding.code !== "DISPATCHER_PAYLOAD_MISSING" ||
      finding.path !== binding.dispatcherTarget,
  );
  if (dispatcherTargetBytes === null) {
    findings.push({
      code: "DISPATCHER_PAYLOAD_MISSING",
      event_types: [],
      path: binding.dispatcherTarget,
    });
  }
  findings.sort((left, right) =>
    left.code === right.code
      ? left.path < right.path
        ? -1
        : left.path > right.path
          ? 1
          : 0
      : left.code < right.code
        ? -1
        : 1,
  );
  const sources = [
    ...BINDING_SOURCE_PATHS.map((path) => ({
      path,
      sha256: sha256(
        path.startsWith(`${PAYLOAD_ROOT}/`)
          ? readPayloadBytes(
              binding.root,
              path.slice(PAYLOAD_ROOT.length + 1),
              "plugin manifest",
              "MANIFEST_UNREADABLE",
            )
          : readBytes(binding.root, path, "MANIFEST_UNREADABLE"),
      ),
    })),
    ...binding.declaration.hook_files.map((relative) => ({
      path: posix.join(PAYLOAD_ROOT, relative),
      sha256: sha256(
        readPayloadBytes(binding.root, relative, "declared hook file", "HOOK_FILE_MISSING"),
      ),
    })),
    {
      path: posix.join(PAYLOAD_ROOT, binding.declaration.dispatcher),
      sha256: sha256(
        readPayloadBytes(
          binding.root,
          binding.declaration.dispatcher,
          "plugin dispatcher",
          "DISPATCHER_UNREADABLE",
        ),
      ),
    },
    ...(dispatcherTargetBytes === null
      ? []
      : [
          {
            path: dispatcherTargetPath,
            sha256: sha256(dispatcherTargetBytes),
          },
        ]),
  ].sort((left, right) => (left.path < right.path ? -1 : 1));

  const preimage = {
    adapter_id: binding.declaration.adapter_id,
    adapter_version: binding.declaration.adapter_version,
    adapter_host: binding.adapterHost,
    binding_status: findings.length === 0 ? BINDING_STATUS.BOUND : BINDING_STATUS.DEGRADED,
    coverage_by_event_type: [...binding.coverageByEventType.entries()]
      .map(([event_type, coverage]) => ({ coverage, event_type }))
      .sort((left, right) => (left.event_type < right.event_type ? -1 : 1)),
    dispatcher_target: binding.dispatcherTarget,
    entrypoints: binding.entrypoints.map((row) => ({ field: row.field, path: row.path })),
    findings: findings.map((row) => ({
      code: row.code,
      event_types: [...row.event_types],
      path: row.path,
    })),
    hook_verbs: [...binding.eventTypeByVerb.entries()]
      .map(([verb, event_type]) => ({ event_type, verb }))
      .sort((left, right) => (left.verb < right.verb ? -1 : 1)),
    plugin_name: binding.manifest.name,
    plugin_version: binding.manifest.version,
    registered_event_types: [...binding.registeredEventTypes],
    registration_count: binding.registrations.length,
    role_count: binding.roleTable.length,
    role_table_hash: roleTableHash(binding.roleTable),
    sources,
    unregistered_event_types: [...binding.unregisteredEventTypes],
  };
  const receiptHash = sha256HookJson(preimage);
  return deepFreeze({
    receipt_id: `EFX01-CODEX-${receiptHash.slice("sha256:".length, "sha256:".length + 16)}`,
    ...preimage,
    receipt_hash: receiptHash,
  });
};
