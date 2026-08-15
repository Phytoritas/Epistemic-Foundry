/**
 * M01 typed workspace inventory and dependency extraction.
 *
 * This module consumes an already frozen logical workspace snapshot. It never
 * reads or writes the filesystem, guesses a missing target, computes ranking,
 * or emits the canonical WorkspaceMapSnapshot owned by later M packages.
 */

import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

const ARRAY_IS_ARRAY = Array.isArray;
const IS_PROXY = utilTypes.isProxy;
const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;

const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const ERROR_CODE_PATTERN = /^[A-Z][A-Z0-9_]{2,63}$/u;
const URI_SCHEME_PATTERN = /^[A-Za-z][A-Za-z0-9+.-]*:/u;
const WINDOWS_RESERVED_BASENAME =
  /^(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$/iu;

export const WORKSPACE_INVENTORY_VERSION = "4.0.0-m01.1";
export const WORKSPACE_EDGE_EXTRACTION_VERSION = "4.0.0-m01.1";

export const ENTITY_LAYERS = OBJECT_FREEZE(["CODE", "RESEARCH", "ARTIFACT"]);
export const SOURCE_CLASSES = OBJECT_FREEZE([
  "SOURCE",
  "DIST",
  "GENERATED",
  "VENDOR",
  "TEST",
  "RESEARCH",
  "ARTIFACT",
]);
export const ENTITY_KINDS = OBJECT_FREEZE([
  "PACKAGE",
  "SOURCE_FILE",
  "DIST_FILE",
  "GENERATED_FILE",
  "VENDOR_FILE",
  "CODE_SYMBOL",
  "SCHEMA",
  "WORKFLOW",
  "WORK_PACKAGE",
  "TEST",
  "API_CONTRACT",
  "SKILL",
  "HOOK",
  "MCP_TOOL",
  "PAPER",
  "DATASET",
  "SOURCE_SPAN",
  "CLAIM",
  "EVIDENCE",
  "ARTIFACT",
  "DECISION",
  "RECEIPT",
]);
export const IDENTITY_NAMESPACES = OBJECT_FREEZE([
  "ENTITY_ID",
  "PATH",
  "LOCATOR",
  "PACKAGE_NAME",
  "SCHEMA_ID",
  "WORKFLOW_ID",
  "WORK_PACKAGE_ID",
  "SYMBOL_ID",
  "DOCUMENT_ID",
  "DATASET_ID",
  "CLAIM_ID",
  "EVIDENCE_ID",
  "ARTIFACT_ID",
  "TEST_ID",
  "SKILL_ID",
  "HOOK_ID",
  "MCP_TOOL_ID",
  "DECISION_ID",
  "RECEIPT_ID",
]);
export const EDGE_KINDS = OBJECT_FREEZE([
  "IMPORTS",
  "SCHEMA_REF",
  "API_CONTRACT_REF",
  "TESTS",
  "WORKFLOW_DEPENDS_ON",
  "PACKAGE_DEPENDS_ON",
  "WORK_PACKAGE_DEPENDS_ON",
  "OWNS_CONTRACT",
  "CITES",
  "PUBLICATION_VERSION_OF",
  "USES_DATASET",
  "SOURCE_SPAN_OF",
  "EVIDENCE_SUPPORTS_CLAIM",
  "EVIDENCE_COUNTERS_CLAIM",
  "DERIVED_FROM",
  "PRODUCED_BY",
  "SUPERSEDES",
  "SKILL_USES",
  "HOOK_DISPATCHES",
]);

const LAYER_SET = new Set(ENTITY_LAYERS);
const SOURCE_CLASS_SET = new Set(SOURCE_CLASSES);
const ENTITY_KIND_SET = new Set(ENTITY_KINDS);
const IDENTITY_NAMESPACE_SET = new Set(IDENTITY_NAMESPACES);
const EDGE_KIND_SET = new Set(EDGE_KINDS);
const RESERVED_ALIAS_NAMESPACES = new Set(["ENTITY_ID", "PATH", "LOCATOR"]);

const KIND_LAYER = OBJECT_FREEZE({
  PACKAGE: "CODE",
  SOURCE_FILE: "CODE",
  DIST_FILE: "CODE",
  GENERATED_FILE: "CODE",
  VENDOR_FILE: "CODE",
  CODE_SYMBOL: "CODE",
  SCHEMA: "CODE",
  WORKFLOW: "CODE",
  WORK_PACKAGE: "CODE",
  TEST: "CODE",
  API_CONTRACT: "CODE",
  SKILL: "CODE",
  HOOK: "CODE",
  MCP_TOOL: "CODE",
  PAPER: "RESEARCH",
  DATASET: "RESEARCH",
  SOURCE_SPAN: "RESEARCH",
  CLAIM: "RESEARCH",
  EVIDENCE: "RESEARCH",
  ARTIFACT: "ARTIFACT",
  DECISION: "ARTIFACT",
  RECEIPT: "ARTIFACT",
});

const IDENTITY_NAMESPACE_KIND = OBJECT_FREEZE({
  PACKAGE_NAME: "PACKAGE",
  SCHEMA_ID: "SCHEMA",
  WORKFLOW_ID: "WORKFLOW",
  WORK_PACKAGE_ID: "WORK_PACKAGE",
  SYMBOL_ID: "CODE_SYMBOL",
  DOCUMENT_ID: "PAPER",
  DATASET_ID: "DATASET",
  CLAIM_ID: "CLAIM",
  EVIDENCE_ID: "EVIDENCE",
  ARTIFACT_ID: "ARTIFACT",
  TEST_ID: "TEST",
  SKILL_ID: "SKILL",
  HOOK_ID: "HOOK",
  MCP_TOOL_ID: "MCP_TOOL",
  DECISION_ID: "DECISION",
  RECEIPT_ID: "RECEIPT",
});

const EDGE_TARGET_KINDS = OBJECT_FREEZE({
  SCHEMA_REF: OBJECT_FREEZE(["SCHEMA"]),
  API_CONTRACT_REF: OBJECT_FREEZE(["API_CONTRACT", "SCHEMA"]),
  WORKFLOW_DEPENDS_ON: OBJECT_FREEZE(["WORKFLOW"]),
  PACKAGE_DEPENDS_ON: OBJECT_FREEZE(["PACKAGE"]),
  WORK_PACKAGE_DEPENDS_ON: OBJECT_FREEZE(["WORK_PACKAGE"]),
  OWNS_CONTRACT: OBJECT_FREEZE(["SCHEMA", "API_CONTRACT", "WORKFLOW"]),
  CITES: OBJECT_FREEZE(["PAPER"]),
  PUBLICATION_VERSION_OF: OBJECT_FREEZE(["PAPER"]),
  USES_DATASET: OBJECT_FREEZE(["DATASET"]),
  SOURCE_SPAN_OF: OBJECT_FREEZE(["PAPER", "DATASET"]),
  EVIDENCE_SUPPORTS_CLAIM: OBJECT_FREEZE(["CLAIM"]),
  EVIDENCE_COUNTERS_CLAIM: OBJECT_FREEZE(["CLAIM"]),
  SKILL_USES: OBJECT_FREEZE(["MCP_TOOL", "SCHEMA", "WORKFLOW", "CODE_SYMBOL"]),
  HOOK_DISPATCHES: OBJECT_FREEZE(["CODE_SYMBOL", "WORKFLOW"]),
});

const FIXED_FILE_SOURCE_CLASS = OBJECT_FREEZE({
  SOURCE_FILE: "SOURCE",
  DIST_FILE: "DIST",
  GENERATED_FILE: "GENERATED",
  VENDOR_FILE: "VENDOR",
  TEST: "TEST",
});

const ENTITY_INPUT_FIELDS = OBJECT_FREEZE([
  "entity_id",
  "kind",
  "label",
  "path",
  "locator",
  "content_hash",
  "owner",
  "source_class",
  "aliases",
]);
const ENTITY_OUTPUT_FIELDS = OBJECT_FREEZE([
  "entity_id",
  "layer",
  "kind",
  "label",
  "path",
  "locator",
  "content_hash",
  "owner",
  "source_class",
  "aliases",
]);
const ALIAS_FIELDS = OBJECT_FREEZE(["namespace", "value"]);
const UNREADABLE_PATH_FIELDS = OBJECT_FREEZE(["path", "error_code"]);
const INVENTORY_INPUT_FIELDS = OBJECT_FREEZE([
  "workspace_id",
  "root_hash",
  "entities",
  "unreadable_paths",
]);
const INVENTORY_OUTPUT_FIELDS = OBJECT_FREEZE([
  "inventory_id",
  "inventory_version",
  "workspace_id",
  "root_hash",
  "entity_count",
  "entities",
  "unreadable_paths",
  "layer_counts",
  "source_class_counts",
  "inventory_hash",
]);
const REFERENCE_FIELDS = OBJECT_FREEZE([
  "source_entity_id",
  "kind",
  "target_identity",
  "target_hint",
  "source_locator",
  "owner",
]);
const EDGE_INPUT_FIELDS = OBJECT_FREEZE(["inventory", "references"]);
const EDGE_OUTPUT_FIELDS = OBJECT_FREEZE([
  "edge_id",
  "kind",
  "source_entity_id",
  "target_entity_id",
  "target_identity",
  "target_hint",
  "source_locator",
  "owner",
  "resolution",
  "unresolved_reason",
]);
const EXTRACTION_OUTPUT_FIELDS = OBJECT_FREEZE([
  "extraction_id",
  "extraction_version",
  "inventory_id",
  "inventory_hash",
  "resolved_edges",
  "unresolved_edges",
  "edge_counts",
  "extraction_hash",
]);

const MISSING_TARGET_ALLOWED_KINDS = new Set([
  "CITES",
  "PUBLICATION_VERSION_OF",
  "USES_DATASET",
  "SOURCE_SPAN_OF",
  "EVIDENCE_SUPPORTS_CLAIM",
  "EVIDENCE_COUNTERS_CLAIM",
  "DERIVED_FROM",
  "PRODUCED_BY",
  "SUPERSEDES",
]);

export class WorkspaceInventoryError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "WorkspaceInventoryError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(canonicalClone(details));
  }
}

const fail = (code, message, details = undefined) => {
  throw new WorkspaceInventoryError(code, message, details);
};

const compareUtf8 = (left, right) =>
  Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));

const hasOnlyUnicodeScalars = (value) => {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      return false;
    }
  }
  return true;
};

const requireText = (
  value,
  label,
  { minLength = 1, maxLength = 4096, code = "INVALID_INPUT", allowControl = false } = {},
) => {
  const length = typeof value === "string" ? [...value].length : -1;
  if (
    typeof value !== "string" ||
    !hasOnlyUnicodeScalars(value) ||
    value.normalize("NFC") !== value ||
    (!allowControl && /\p{Cc}/u.test(value)) ||
    length < minLength ||
    length > maxLength
  ) {
    fail(code, `${label} must be a bounded NFC Unicode scalar string`);
  }
  return value;
};

const requireIdentifier = (value, label, code = "INVALID_INPUT") =>
  requireText(value, label, { minLength: 3, maxLength: 128, code });

const requireHash = (value, label, code = "INVALID_HASH") => {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) {
    fail(code, `${label} must be sha256:<64 lowercase hex>`);
  }
  return value;
};

const requirePlainDataObject = (value, label, fields, code = "INVALID_INPUT") => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    (OBJECT_GET_PROTOTYPE_OF(value) !== PLAIN_OBJECT_PROTOTYPE &&
      OBJECT_GET_PROTOTYPE_OF(value) !== null)
  ) {
    fail(code, `${label} must be a non-proxy plain data object`);
  }
  const allowed = new Set(fields);
  const keys = REFLECT_OWN_KEYS(value);
  for (const key of keys) {
    if (typeof key !== "string" || !allowed.has(key)) {
      fail(code, `${label} contains an unsupported field`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label}.${String(key)} must be an enumerable data property`);
    }
  }
  for (const field of fields) {
    if (!OBJECT_HAS_OWN(value, field)) fail(code, `${label}.${field} is required`);
  }
  return value;
};

const readDataProperty = (object, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(object, key).value;

const readDenseArray = (value, label, code = "INVALID_INPUT") => {
  if (
    !ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== Array.prototype
  ) {
    fail(code, `${label} must be a non-proxy plain dense array`);
  }
  for (const key of REFLECT_OWN_KEYS(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail(code, `${label} contains a non-element property`);
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index >= value.length || String(index) !== key) {
      fail(code, `${label} contains an invalid element index`);
    }
  }
  const result = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail(code, `${label} contains a sparse or accessor-backed element`);
    }
    result.push(descriptor.value);
  }
  return result;
};

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of REFLECT_OWN_KEYS(value)) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const canonicalizeWorkspaceMapJsonValue = (value, ancestors) => {
  if (value === null) return "null";
  if (typeof value === "string") {
    requireText(value, "canonical JSON string", { minLength: 0, maxLength: 1_000_000 });
    return JSON.stringify(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || Object.is(value, -0)) {
      fail("NON_CANONICAL_JSON", "canonical JSON accepts finite safe integers only");
    }
    return String(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    if (ancestors.has(value)) {
      fail("NON_CANONICAL_JSON", "canonical JSON cannot contain a cycle");
    }
    const entries = readDenseArray(value, "canonical JSON array", "NON_CANONICAL_JSON");
    ancestors.add(value);
    try {
      return `[${entries
        .map((entry) => canonicalizeWorkspaceMapJsonValue(entry, ancestors))
        .join(",")}]`;
    } finally {
      ancestors.delete(value);
    }
  }
  if (value === undefined || typeof value !== "object" || IS_PROXY(value)) {
    fail("NON_CANONICAL_JSON", "canonical JSON contains an unsupported value");
  }
  const prototype = OBJECT_GET_PROTOTYPE_OF(value);
  if (prototype !== PLAIN_OBJECT_PROTOTYPE && prototype !== null) {
    fail("NON_CANONICAL_JSON", "canonical JSON object has a custom prototype");
  }
  const keys = REFLECT_OWN_KEYS(value);
  if (keys.some((key) => typeof key !== "string")) {
    fail("NON_CANONICAL_JSON", "canonical JSON object contains a symbol key");
  }
  keys.sort(compareUtf8);
  if (ancestors.has(value)) {
    fail("NON_CANONICAL_JSON", "canonical JSON cannot contain a cycle");
  }
  ancestors.add(value);
  try {
    return `{${keys
      .map((key) => {
        const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
        if (
          descriptor === undefined ||
          !descriptor.enumerable ||
          !OBJECT_HAS_OWN(descriptor, "value")
        ) {
          fail("NON_CANONICAL_JSON", "canonical JSON object contains an accessor field");
        }
        return `${JSON.stringify(key)}:${canonicalizeWorkspaceMapJsonValue(
          descriptor.value,
          ancestors,
        )}`;
      })
      .join(",")}}`;
  } finally {
    ancestors.delete(value);
  }
};

export const canonicalizeWorkspaceMapJson = (value) =>
  canonicalizeWorkspaceMapJsonValue(value, new Set());

const canonicalClone = (value) =>
  deepFreeze(JSON.parse(canonicalizeWorkspaceMapJson(value)));

const sha256CanonicalJson = (value) =>
  `sha256:${createHash("sha256")
    .update(canonicalizeWorkspaceMapJson(value), "utf8")
    .digest("hex")}`;

const requirePortablePath = (value, label, code = "INVALID_PORTABLE_PATH") => {
  const candidate = requireText(value, label, { maxLength: 4096, code });
  if (
    candidate.includes("\\") ||
    candidate.includes(":") ||
    candidate.startsWith("/") ||
    candidate.endsWith("/") ||
    candidate.includes("//")
  ) {
    fail(code, `${label} must be a normalized portable relative path`);
  }
  const segments = candidate.split("/");
  for (const segment of segments) {
    const windowsBaseName = segment.split(".", 1)[0].trimEnd();
    if (
      segment.length === 0 ||
      segment === "." ||
      segment === ".." ||
      /[<>"|?*]/u.test(segment) ||
      segment.endsWith(".") ||
      segment.endsWith(" ") ||
      WINDOWS_RESERVED_BASENAME.test(windowsBaseName)
    ) {
      fail(code, `${label} contains an unsafe path component`);
    }
  }
  return candidate;
};

const requireLocator = (value, label, code = "INVALID_LOCATOR") => {
  const locator = requireText(value, label, { maxLength: 4096, code });
  if (!URI_SCHEME_PATTERN.test(locator) || /\s/u.test(locator)) {
    fail(code, `${label} must be an explicit URI-like locator`);
  }
  return locator;
};

const requireEnum = (value, label, set, code) => {
  if (typeof value !== "string" || !set.has(value)) {
    fail(
      code,
      `${label} is outside the canonical vocabulary`,
      typeof value === "string" ? { value } : undefined,
    );
  }
  return value;
};

const normalizeAliasValue = (namespace, value, label) => {
  if (namespace === "PATH") return requirePortablePath(value, label);
  if (namespace === "LOCATOR") return requireLocator(value, label);
  if (namespace === "ENTITY_ID") return requireIdentifier(value, label);
  return requireText(value, label, { maxLength: 4096 });
};

const normalizeAlias = (candidate, label) => {
  const alias = requirePlainDataObject(candidate, label, ALIAS_FIELDS, "INVALID_ALIAS");
  const namespace = requireEnum(
    readDataProperty(alias, "namespace"),
    `${label}.namespace`,
    IDENTITY_NAMESPACE_SET,
    "UNKNOWN_IDENTITY_NAMESPACE",
  );
  if (RESERVED_ALIAS_NAMESPACES.has(namespace)) {
    fail("RESERVED_ALIAS_NAMESPACE", `${namespace} identity is derived from the entity envelope`);
  }
  return {
    namespace,
    value: normalizeAliasValue(namespace, readDataProperty(alias, "value"), `${label}.value`),
  };
};

const normalizeEntity = (candidate, label) => {
  const entity = requirePlainDataObject(candidate, label, ENTITY_INPUT_FIELDS, "INVALID_ENTITY");
  const kind = requireEnum(
    readDataProperty(entity, "kind"),
    `${label}.kind`,
    ENTITY_KIND_SET,
    "UNKNOWN_ENTITY_KIND",
  );
  const layer = KIND_LAYER[kind];
  if (!LAYER_SET.has(layer)) fail("UNKNOWN_ENTITY_KIND", `${label}.kind has no layer mapping`);
  const sourceClass = requireEnum(
    readDataProperty(entity, "source_class"),
    `${label}.source_class`,
    SOURCE_CLASS_SET,
    "UNKNOWN_SOURCE_CLASS",
  );
  if (
    (layer === "CODE" && !["SOURCE", "DIST", "GENERATED", "VENDOR", "TEST"].includes(sourceClass)) ||
    (layer === "RESEARCH" && sourceClass !== "RESEARCH") ||
    (layer === "ARTIFACT" && sourceClass !== "ARTIFACT")
  ) {
    fail("SOURCE_CLASS_LAYER_MISMATCH", `${label}.source_class conflicts with ${layer}`);
  }
  if (FIXED_FILE_SOURCE_CLASS[kind] !== undefined && FIXED_FILE_SOURCE_CLASS[kind] !== sourceClass) {
    fail("SOURCE_CLASS_KIND_MISMATCH", `${label}.${kind} requires ${FIXED_FILE_SOURCE_CLASS[kind]}`);
  }
  const pathValue = readDataProperty(entity, "path");
  const locatorValue = readDataProperty(entity, "locator");
  const entityPath = pathValue === null ? null : requirePortablePath(pathValue, `${label}.path`);
  const locator = locatorValue === null ? null : requireLocator(locatorValue, `${label}.locator`);
  if (entityPath === null && locator === null) {
    fail("ENTITY_LOCATION_MISSING", `${label} requires a path or locator`);
  }
  const aliases = readDenseArray(readDataProperty(entity, "aliases"), `${label}.aliases`, "INVALID_ALIAS")
    .map((alias, index) => normalizeAlias(alias, `${label}.aliases[${index}]`))
    .sort((left, right) =>
      compareUtf8(left.namespace, right.namespace) || compareUtf8(left.value, right.value),
    );
  const aliasKeys = aliases.map((alias) => `${alias.namespace}\u0000${alias.value}`);
  if (new Set(aliasKeys).size !== aliasKeys.length) {
    fail("DUPLICATE_ENTITY_ALIAS", `${label}.aliases contains a duplicate identity`);
  }
  return canonicalClone({
    entity_id: requireIdentifier(readDataProperty(entity, "entity_id"), `${label}.entity_id`),
    layer,
    kind,
    label: requireText(readDataProperty(entity, "label"), `${label}.label`, { maxLength: 512 }),
    path: entityPath,
    locator,
    content_hash: requireHash(readDataProperty(entity, "content_hash"), `${label}.content_hash`),
    owner: requireText(readDataProperty(entity, "owner"), `${label}.owner`, { maxLength: 256 }),
    source_class: sourceClass,
    aliases,
  });
};

const entityInputFromOutput = (candidate, label) => {
  const entity = requirePlainDataObject(candidate, label, ENTITY_OUTPUT_FIELDS, "INVALID_ENTITY");
  const input = {};
  for (const field of ENTITY_INPUT_FIELDS) input[field] = readDataProperty(entity, field);
  const normalized = normalizeEntity(input, label);
  const suppliedLayer = requireEnum(
    readDataProperty(entity, "layer"),
    `${label}.layer`,
    LAYER_SET,
    "UNKNOWN_ENTITY_LAYER",
  );
  if (suppliedLayer !== normalized.layer) {
    fail("ENTITY_LAYER_MISMATCH", `${label}.layer conflicts with its kind`);
  }
  return input;
};

const normalizeUnreadablePath = (candidate, label) => {
  const record = requirePlainDataObject(
    candidate,
    label,
    UNREADABLE_PATH_FIELDS,
    "INVALID_UNREADABLE_PATH",
  );
  const errorCode = readDataProperty(record, "error_code");
  if (typeof errorCode !== "string" || !ERROR_CODE_PATTERN.test(errorCode)) {
    fail("INVALID_UNREADABLE_PATH", `${label}.error_code must be a stable uppercase code`);
  }
  return canonicalClone({
    path: requirePortablePath(readDataProperty(record, "path"), `${label}.path`),
    error_code: errorCode,
  });
};

const automaticIdentities = (entity) => {
  const identities = [{ namespace: "ENTITY_ID", value: entity.entity_id }];
  if (entity.path !== null) identities.push({ namespace: "PATH", value: entity.path });
  if (entity.locator !== null) identities.push({ namespace: "LOCATOR", value: entity.locator });
  identities.push(...entity.aliases);
  return identities;
};

const identityKey = (namespace, value) => `${namespace}\u0000${value}`;

const assertUniqueInventoryIdentities = (entities, unreadablePaths) => {
  const entityIds = new Set();
  const portablePaths = new Map();
  const identityOwners = new Map();
  for (const entity of entities) {
    if (entityIds.has(entity.entity_id)) {
      fail("DUPLICATE_ENTITY_ID", "entity_id must be globally unique", {
        entity_id: entity.entity_id,
      });
    }
    entityIds.add(entity.entity_id);
    if (entity.path !== null) {
      const folded = entity.path.toLowerCase();
      if (portablePaths.has(folded)) {
        fail("DUPLICATE_ENTITY_PATH", "entity paths must be portable and case-unambiguous", {
          path: entity.path,
          conflicts_with: portablePaths.get(folded),
        });
      }
      portablePaths.set(folded, entity.path);
    }
    for (const identity of automaticIdentities(entity)) {
      const key = identityKey(identity.namespace, identity.value);
      if (identityOwners.has(key)) {
        fail("DUPLICATE_ENTITY_IDENTITY", "an entity identity resolves to multiple entities", {
          namespace: identity.namespace,
          value: identity.value,
          first_entity_id: identityOwners.get(key),
          second_entity_id: entity.entity_id,
        });
      }
      identityOwners.set(key, entity.entity_id);
    }
  }
  const unreadableSeen = new Set();
  for (const entry of unreadablePaths) {
    const folded = entry.path.toLowerCase();
    if (unreadableSeen.has(folded)) {
      fail("DUPLICATE_UNREADABLE_PATH", "unreadable paths must be unique", { path: entry.path });
    }
    if (portablePaths.has(folded)) {
      fail("READABILITY_CONFLICT", "a path cannot be both indexed and unreadable", {
        path: entry.path,
      });
    }
    unreadableSeen.add(folded);
  }
};

const fixedCountRecord = (keys, rows, field) => {
  const result = {};
  for (const key of keys) result[key] = rows.filter((row) => row[field] === key).length;
  return result;
};

const inventoryPreimage = ({ workspaceId, rootHash, entities, unreadablePaths }) => ({
  inventory_version: WORKSPACE_INVENTORY_VERSION,
  workspace_id: workspaceId,
  root_hash: rootHash,
  entity_count: entities.length,
  entities,
  unreadable_paths: unreadablePaths,
  layer_counts: fixedCountRecord(ENTITY_LAYERS, entities, "layer"),
  source_class_counts: fixedCountRecord(SOURCE_CLASSES, entities, "source_class"),
});

export const buildWorkspaceInventory = (candidate) => {
  const input = requirePlainDataObject(
    candidate,
    "WorkspaceInventoryInput",
    INVENTORY_INPUT_FIELDS,
    "INVALID_INVENTORY_INPUT",
  );
  const entities = readDenseArray(
    readDataProperty(input, "entities"),
    "entities",
    "INVALID_INVENTORY_INPUT",
  )
    .map((entity, index) => normalizeEntity(entity, `entities[${index}]`))
    .sort((left, right) => compareUtf8(left.entity_id, right.entity_id));
  const unreadablePaths = readDenseArray(
    readDataProperty(input, "unreadable_paths"),
    "unreadable_paths",
    "INVALID_INVENTORY_INPUT",
  )
    .map((entry, index) => normalizeUnreadablePath(entry, `unreadable_paths[${index}]`))
    .sort((left, right) => compareUtf8(left.path, right.path));
  assertUniqueInventoryIdentities(entities, unreadablePaths);
  const preimage = inventoryPreimage({
    workspaceId: requireIdentifier(readDataProperty(input, "workspace_id"), "workspace_id"),
    rootHash: requireHash(readDataProperty(input, "root_hash"), "root_hash"),
    entities,
    unreadablePaths,
  });
  const inventoryHash = sha256CanonicalJson(preimage);
  return canonicalClone({
    inventory_id: `WINV-${inventoryHash.slice("sha256:".length)}`,
    ...preimage,
    inventory_hash: inventoryHash,
  });
};

export const validateWorkspaceInventory = (candidate) => {
  const inventory = requirePlainDataObject(
    candidate,
    "WorkspaceInventory",
    INVENTORY_OUTPUT_FIELDS,
    "INVALID_INVENTORY",
  );
  if (readDataProperty(inventory, "inventory_version") !== WORKSPACE_INVENTORY_VERSION) {
    fail("INVENTORY_VERSION_UNSUPPORTED", "workspace inventory version is unsupported");
  }
  const entityInputs = readDenseArray(
    readDataProperty(inventory, "entities"),
    "entities",
    "INVALID_INVENTORY",
  ).map((entity, index) => entityInputFromOutput(entity, `entities[${index}]`));
  const unreadablePaths = readDenseArray(
    readDataProperty(inventory, "unreadable_paths"),
    "unreadable_paths",
    "INVALID_INVENTORY",
  );
  const rebuilt = buildWorkspaceInventory({
    workspace_id: readDataProperty(inventory, "workspace_id"),
    root_hash: readDataProperty(inventory, "root_hash"),
    entities: entityInputs,
    unreadable_paths: unreadablePaths,
  });
  const observedHash = requireHash(
    readDataProperty(inventory, "inventory_hash"),
    "inventory_hash",
    "INVALID_INVENTORY_HASH",
  );
  if (observedHash !== rebuilt.inventory_hash) {
    fail("INVENTORY_HASH_MISMATCH", "inventory_hash does not bind the canonical inventory", {
      expected: rebuilt.inventory_hash,
      observed: observedHash,
    });
  }
  const inventoryId = requireIdentifier(
    readDataProperty(inventory, "inventory_id"),
    "inventory_id",
    "INVALID_INVENTORY",
  );
  if (inventoryId !== rebuilt.inventory_id) {
    fail("INVENTORY_ID_MISMATCH", "inventory_id does not bind inventory_hash");
  }
  if (canonicalizeWorkspaceMapJson(inventory) !== canonicalizeWorkspaceMapJson(rebuilt)) {
    fail("INVENTORY_REBUILD_MISMATCH", "inventory differs from its canonical rebuild");
  }
  return rebuilt;
};

const normalizeTargetIdentity = (candidate, label) => {
  const identity = requirePlainDataObject(candidate, label, ALIAS_FIELDS, "INVALID_TARGET_IDENTITY");
  const namespace = requireEnum(
    readDataProperty(identity, "namespace"),
    `${label}.namespace`,
    IDENTITY_NAMESPACE_SET,
    "UNKNOWN_IDENTITY_NAMESPACE",
  );
  return canonicalClone({
    namespace,
    value: normalizeAliasValue(namespace, readDataProperty(identity, "value"), `${label}.value`),
  });
};

const normalizeReference = (candidate, label) => {
  const reference = requirePlainDataObject(candidate, label, REFERENCE_FIELDS, "INVALID_EDGE_REFERENCE");
  const kind = requireEnum(
    readDataProperty(reference, "kind"),
    `${label}.kind`,
    EDGE_KIND_SET,
    "UNKNOWN_EDGE_KIND",
  );
  const targetValue = readDataProperty(reference, "target_identity");
  const targetIdentity =
    targetValue === null ? null : normalizeTargetIdentity(targetValue, `${label}.target_identity`);
  const hintValue = readDataProperty(reference, "target_hint");
  const targetHint =
    hintValue === null
      ? null
      : requireText(hintValue, `${label}.target_hint`, { maxLength: 1024 });
  if (targetIdentity === null && targetHint === null) {
    fail("MISSING_TARGET_HINT", `${label} without target_identity requires a target_hint`);
  }
  if (targetIdentity === null && !MISSING_TARGET_ALLOWED_KINDS.has(kind)) {
    fail("MISSING_TARGET_IDENTITY_DENIED", `${kind} requires a typed target identity`);
  }
  return canonicalClone({
    source_entity_id: requireIdentifier(
      readDataProperty(reference, "source_entity_id"),
      `${label}.source_entity_id`,
    ),
    kind,
    target_identity: targetIdentity,
    target_hint: targetHint,
    source_locator: requireText(
      readDataProperty(reference, "source_locator"),
      `${label}.source_locator`,
      { maxLength: 2048 },
    ),
    owner: requireText(readDataProperty(reference, "owner"), `${label}.owner`, {
      maxLength: 256,
    }),
  });
};

const assertSourceKind = (kind, source, allowed) => {
  if (!allowed.includes(source.kind)) {
    fail("EDGE_SOURCE_KIND_MISMATCH", `${kind} cannot originate from ${source.kind}`, {
      edge_kind: kind,
      source_entity_id: source.entity_id,
      source_kind: source.kind,
    });
  }
};

const assertSourceLayer = (kind, source, allowed) => {
  if (!allowed.includes(source.layer)) {
    fail("EDGE_SOURCE_LAYER_MISMATCH", `${kind} cannot originate from ${source.layer}`, {
      edge_kind: kind,
      source_entity_id: source.entity_id,
      source_layer: source.layer,
    });
  }
};

const assertTargetKind = (kind, target, allowed) => {
  if (!allowed.includes(target.kind)) {
    fail("EDGE_TARGET_KIND_MISMATCH", `${kind} cannot target ${target.kind}`, {
      edge_kind: kind,
      target_entity_id: target.entity_id,
      target_kind: target.kind,
    });
  }
};

const assertTargetLayer = (kind, target, allowed) => {
  if (!allowed.includes(target.layer)) {
    fail("EDGE_TARGET_LAYER_MISMATCH", `${kind} cannot target ${target.layer}`, {
      edge_kind: kind,
      target_entity_id: target.entity_id,
      target_layer: target.layer,
    });
  }
};

const validateEdgeDirection = (kind, source, target = null) => {
  switch (kind) {
    case "IMPORTS":
      assertSourceLayer(kind, source, ["CODE"]);
      if (target !== null) assertTargetLayer(kind, target, ["CODE"]);
      break;
    case "SCHEMA_REF":
      assertSourceLayer(kind, source, ["CODE", "ARTIFACT"]);
      if (target !== null) assertTargetKind(kind, target, ["SCHEMA"]);
      break;
    case "API_CONTRACT_REF":
      assertSourceLayer(kind, source, ["CODE"]);
      if (target !== null) assertTargetKind(kind, target, ["API_CONTRACT", "SCHEMA"]);
      break;
    case "TESTS":
      assertSourceKind(kind, source, ["TEST"]);
      break;
    case "WORKFLOW_DEPENDS_ON":
      assertSourceKind(kind, source, ["WORKFLOW"]);
      if (target !== null) assertTargetKind(kind, target, ["WORKFLOW"]);
      break;
    case "PACKAGE_DEPENDS_ON":
      assertSourceKind(kind, source, ["PACKAGE"]);
      if (target !== null) assertTargetKind(kind, target, ["PACKAGE"]);
      break;
    case "WORK_PACKAGE_DEPENDS_ON":
      assertSourceKind(kind, source, ["WORK_PACKAGE"]);
      if (target !== null) assertTargetKind(kind, target, ["WORK_PACKAGE"]);
      break;
    case "OWNS_CONTRACT":
      assertSourceKind(kind, source, ["PACKAGE", "WORK_PACKAGE"]);
      if (target !== null) assertTargetKind(kind, target, ["SCHEMA", "API_CONTRACT", "WORKFLOW"]);
      break;
    case "CITES":
    case "PUBLICATION_VERSION_OF":
      assertSourceKind(kind, source, ["PAPER"]);
      if (target !== null) assertTargetKind(kind, target, ["PAPER"]);
      break;
    case "USES_DATASET":
      assertSourceKind(kind, source, ["PAPER", "CLAIM", "EVIDENCE"]);
      if (target !== null) assertTargetKind(kind, target, ["DATASET"]);
      break;
    case "SOURCE_SPAN_OF":
      assertSourceKind(kind, source, ["SOURCE_SPAN"]);
      if (target !== null) assertTargetKind(kind, target, ["PAPER", "DATASET"]);
      break;
    case "EVIDENCE_SUPPORTS_CLAIM":
    case "EVIDENCE_COUNTERS_CLAIM":
      assertSourceKind(kind, source, ["EVIDENCE"]);
      if (target !== null) assertTargetKind(kind, target, ["CLAIM"]);
      break;
    case "DERIVED_FROM":
      assertSourceKind(kind, source, ["ARTIFACT", "DECISION", "RECEIPT"]);
      if (target !== null) assertTargetLayer(kind, target, ["RESEARCH", "ARTIFACT"]);
      break;
    case "PRODUCED_BY":
      assertSourceKind(kind, source, ["ARTIFACT", "RECEIPT"]);
      if (target !== null) assertTargetLayer(kind, target, ["CODE", "ARTIFACT"]);
      break;
    case "SUPERSEDES":
      assertSourceKind(kind, source, ["ARTIFACT", "DECISION"]);
      if (target !== null && target.kind !== source.kind) {
        fail("EDGE_TARGET_KIND_MISMATCH", "SUPERSEDES must retain entity kind", {
          source_kind: source.kind,
          target_kind: target.kind,
        });
      }
      break;
    case "SKILL_USES":
      assertSourceKind(kind, source, ["SKILL"]);
      if (target !== null) assertTargetKind(kind, target, ["MCP_TOOL", "SCHEMA", "WORKFLOW", "CODE_SYMBOL"]);
      break;
    case "HOOK_DISPATCHES":
      assertSourceKind(kind, source, ["HOOK"]);
      if (target !== null) assertTargetKind(kind, target, ["CODE_SYMBOL", "WORKFLOW"]);
      break;
    default:
      fail("UNKNOWN_EDGE_KIND", `unhandled edge kind ${kind}`);
  }
};

const validateTargetIdentityKind = (kind, source, identity) => {
  const targetKind = IDENTITY_NAMESPACE_KIND[identity.namespace];
  if (targetKind === undefined) return;
  if (kind === "SUPERSEDES") {
    if (targetKind !== source.kind) {
      fail("EDGE_TARGET_KIND_MISMATCH", "SUPERSEDES must retain entity kind", {
        source_kind: source.kind,
        target_kind: targetKind,
      });
    }
    return;
  }
  const allowed = EDGE_TARGET_KINDS[kind];
  if (allowed === undefined) return;
  assertTargetKind(kind, { entity_id: null, kind: targetKind }, allowed);
};

const inventoryIndexes = (inventory) => {
  const byEntityId = new Map();
  const byIdentity = new Map();
  for (const entity of inventory.entities) {
    byEntityId.set(entity.entity_id, entity);
    for (const identity of automaticIdentities(entity)) {
      byIdentity.set(identityKey(identity.namespace, identity.value), entity);
    }
  }
  return { byEntityId, byIdentity };
};

const resolveReference = (reference, indexes) => {
  const source = indexes.byEntityId.get(reference.source_entity_id);
  if (source === undefined) {
    fail("EDGE_SOURCE_NOT_FOUND", "edge source is absent from the bound inventory", {
      source_entity_id: reference.source_entity_id,
    });
  }
  if (reference.owner !== source.owner) {
    fail("EDGE_OWNER_MISMATCH", "edge owner must equal the indexed source owner", {
      source_entity_id: source.entity_id,
      expected_owner: source.owner,
      observed_owner: reference.owner,
    });
  }
  let target = null;
  let resolution = "UNRESOLVED";
  let unresolvedReason = "MISSING_TARGET_LOCATOR";
  if (reference.target_identity !== null) {
    validateTargetIdentityKind(reference.kind, source, reference.target_identity);
    target = indexes.byIdentity.get(
      identityKey(reference.target_identity.namespace, reference.target_identity.value),
    ) ?? null;
    unresolvedReason = target === null ? "TARGET_NOT_FOUND" : null;
    resolution = target === null ? "UNRESOLVED" : "RESOLVED";
  }
  validateEdgeDirection(reference.kind, source, target);
  if (target !== null && target.entity_id === source.entity_id) {
    fail("SELF_EDGE_DENIED", "a dependency or provenance edge cannot target itself", {
      entity_id: source.entity_id,
      edge_kind: reference.kind,
    });
  }
  const semantic = canonicalClone({
    kind: reference.kind,
    source_entity_id: source.entity_id,
    target_entity_id: target?.entity_id ?? null,
    target_identity: reference.target_identity,
    target_hint: reference.target_hint,
    source_locator: reference.source_locator,
    owner: reference.owner,
    resolution,
    unresolved_reason: unresolvedReason,
  });
  const edgeHash = sha256CanonicalJson(semantic);
  return canonicalClone({ edge_id: `WEDGE-${edgeHash.slice("sha256:".length)}`, ...semantic });
};

const extractionPreimage = ({ inventory, resolvedEdges, unresolvedEdges }) => {
  const byKind = {};
  for (const kind of EDGE_KINDS) {
    byKind[kind] = [...resolvedEdges, ...unresolvedEdges].filter((edge) => edge.kind === kind).length;
  }
  return {
    extraction_version: WORKSPACE_EDGE_EXTRACTION_VERSION,
    inventory_id: inventory.inventory_id,
    inventory_hash: inventory.inventory_hash,
    resolved_edges: resolvedEdges,
    unresolved_edges: unresolvedEdges,
    edge_counts: {
      total: resolvedEdges.length + unresolvedEdges.length,
      resolved: resolvedEdges.length,
      unresolved: unresolvedEdges.length,
      by_kind: byKind,
    },
  };
};

export const extractWorkspaceEdges = (candidate) => {
  const input = requirePlainDataObject(
    candidate,
    "WorkspaceEdgeExtractionInput",
    EDGE_INPUT_FIELDS,
    "INVALID_EDGE_EXTRACTION_INPUT",
  );
  const inventory = validateWorkspaceInventory(readDataProperty(input, "inventory"));
  const references = readDenseArray(
    readDataProperty(input, "references"),
    "references",
    "INVALID_EDGE_EXTRACTION_INPUT",
  )
    .map((reference, index) => normalizeReference(reference, `references[${index}]`))
    .sort((left, right) =>
      compareUtf8(canonicalizeWorkspaceMapJson(left), canonicalizeWorkspaceMapJson(right)),
    );
  const referenceKeys = references.map((reference) => canonicalizeWorkspaceMapJson(reference));
  if (new Set(referenceKeys).size !== referenceKeys.length) {
    fail("DUPLICATE_EDGE_REFERENCE", "references contains an exact duplicate");
  }
  const indexes = inventoryIndexes(inventory);
  const edges = references.map((reference) => resolveReference(reference, indexes));
  if (new Set(edges.map((edge) => edge.edge_id)).size !== edges.length) {
    fail("DUPLICATE_EDGE_ID", "edge identity collision detected");
  }
  const resolvedEdges = edges
    .filter((edge) => edge.resolution === "RESOLVED")
    .sort((left, right) => compareUtf8(left.edge_id, right.edge_id));
  const unresolvedEdges = edges
    .filter((edge) => edge.resolution === "UNRESOLVED")
    .sort((left, right) => compareUtf8(left.edge_id, right.edge_id));
  const preimage = extractionPreimage({ inventory, resolvedEdges, unresolvedEdges });
  const extractionHash = sha256CanonicalJson(preimage);
  return canonicalClone({
    extraction_id: `WEDGESET-${extractionHash.slice("sha256:".length)}`,
    ...preimage,
    extraction_hash: extractionHash,
  });
};

const referenceFromEmittedEdge = (candidate, label) => {
  const edge = requirePlainDataObject(candidate, label, EDGE_OUTPUT_FIELDS, "INVALID_EDGE");
  return {
    source_entity_id: readDataProperty(edge, "source_entity_id"),
    kind: readDataProperty(edge, "kind"),
    target_identity: readDataProperty(edge, "target_identity"),
    target_hint: readDataProperty(edge, "target_hint"),
    source_locator: readDataProperty(edge, "source_locator"),
    owner: readDataProperty(edge, "owner"),
  };
};

export const validateWorkspaceEdgeExtraction = (candidate, inventoryCandidate) => {
  const extraction = requirePlainDataObject(
    candidate,
    "WorkspaceEdgeExtraction",
    EXTRACTION_OUTPUT_FIELDS,
    "INVALID_EDGE_EXTRACTION",
  );
  if (readDataProperty(extraction, "extraction_version") !== WORKSPACE_EDGE_EXTRACTION_VERSION) {
    fail("EDGE_EXTRACTION_VERSION_UNSUPPORTED", "edge extraction version is unsupported");
  }
  const inventory = validateWorkspaceInventory(inventoryCandidate);
  if (
    readDataProperty(extraction, "inventory_id") !== inventory.inventory_id ||
    readDataProperty(extraction, "inventory_hash") !== inventory.inventory_hash
  ) {
    fail("EDGE_INVENTORY_BINDING_MISMATCH", "edge extraction is bound to another inventory");
  }
  const resolved = readDenseArray(
    readDataProperty(extraction, "resolved_edges"),
    "resolved_edges",
    "INVALID_EDGE_EXTRACTION",
  );
  const unresolved = readDenseArray(
    readDataProperty(extraction, "unresolved_edges"),
    "unresolved_edges",
    "INVALID_EDGE_EXTRACTION",
  );
  const references = [
    ...resolved.map((edge, index) => referenceFromEmittedEdge(edge, `resolved_edges[${index}]`)),
    ...unresolved.map((edge, index) =>
      referenceFromEmittedEdge(edge, `unresolved_edges[${index}]`),
    ),
  ];
  const rebuilt = extractWorkspaceEdges({ inventory, references });
  const observedHash = requireHash(
    readDataProperty(extraction, "extraction_hash"),
    "extraction_hash",
    "INVALID_EDGE_EXTRACTION_HASH",
  );
  if (observedHash !== rebuilt.extraction_hash) {
    fail("EDGE_EXTRACTION_HASH_MISMATCH", "extraction_hash does not bind the canonical edge set", {
      expected: rebuilt.extraction_hash,
      observed: observedHash,
    });
  }
  const extractionId = requireIdentifier(
    readDataProperty(extraction, "extraction_id"),
    "extraction_id",
    "INVALID_EDGE_EXTRACTION",
  );
  if (extractionId !== rebuilt.extraction_id) {
    fail("EDGE_EXTRACTION_ID_MISMATCH", "extraction_id does not bind extraction_hash");
  }
  if (canonicalizeWorkspaceMapJson(extraction) !== canonicalizeWorkspaceMapJson(rebuilt)) {
    fail("EDGE_EXTRACTION_REBUILD_MISMATCH", "edge extraction differs from its canonical rebuild");
  }
  return rebuilt;
};

export const computeWorkspaceInventoryHash = (candidate) =>
  validateWorkspaceInventory(candidate).inventory_hash;

export const computeWorkspaceEdgeExtractionHash = (candidate, inventory) =>
  validateWorkspaceEdgeExtraction(candidate, inventory).extraction_hash;
