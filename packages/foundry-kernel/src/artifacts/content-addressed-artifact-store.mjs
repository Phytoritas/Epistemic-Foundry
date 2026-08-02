import { createHash, randomUUID } from "node:crypto";
import {
  closeSync,
  constants as fsConstants,
  existsSync,
  fstatSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  rmdirSync,
  unlinkSync,
  writeSync,
} from "node:fs";
import path from "node:path";
import { types as utilTypes } from "node:util";

const OBJECT_FREEZE = Object.freeze;
const OBJECT_GET_PROTOTYPE_OF = Object.getPrototypeOf;
const OBJECT_GET_OWN_PROPERTY_DESCRIPTOR = Object.getOwnPropertyDescriptor;
const OBJECT_HAS_OWN = Object.hasOwn;
const REFLECT_OWN_KEYS = Reflect.ownKeys;
const ARRAY_IS_ARRAY = Array.isArray;
const ARRAY_SORT = Function.prototype.call.bind(Array.prototype.sort);
const NUMBER_IS_FINITE = Number.isFinite;
const NUMBER_IS_SAFE_INTEGER = Number.isSafeInteger;
const STRING_CHAR_CODE_AT = Function.prototype.call.bind(String.prototype.charCodeAt);
const STRING_STARTS_WITH = Function.prototype.call.bind(String.prototype.startsWith);
const STRING_TO_LOWER_CASE = Function.prototype.call.bind(String.prototype.toLowerCase);
const IS_PROXY = utilTypes.isProxy;
const BUFFER_IS_BUFFER = Buffer.isBuffer;
const PLAIN_OBJECT_PROTOTYPE = Object.prototype;
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const LOCATOR_PATTERN = /^artifact:\/\/sha256\/([0-9a-f]{64})$/u;
const PREFIX_PATTERN = /^[0-9a-f]{2}$/u;
const SUFFIX_PATTERN = /^[0-9a-f]{62}$/u;
const ID_KEY_PATTERN = /^[0-9a-f]{64}$/u;
const RECEIPT_FILE_PATTERN = /^([0-9a-f]{64})\.json$/u;
const STAGE_PATTERN = /^\.stage-[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const RFC3339_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/u;
const HEX_DIRECTORY = "sha256";
const STAGING_DIRECTORY = ".staging";
const MUTATION_LOCK = ".mutation-lock";
const CONTENT_FILE = "content.bin";
const ARTIFACTS_DIRECTORY = "artifacts";
const MANIFEST_FILE = "artifact-manifest.json";
const RECEIPTS_DIRECTORY = "receipts";
const OBJECT_ENTRIES = OBJECT_FREEZE([ARTIFACTS_DIRECTORY, CONTENT_FILE]);
const REGISTRATION_ENTRIES = OBJECT_FREEZE([MANIFEST_FILE, RECEIPTS_DIRECTORY]);
const ROOT_ENTRIES = OBJECT_FREEZE([STAGING_DIRECTORY, HEX_DIRECTORY]);
const MAX_METADATA_BYTES = 1024 * 1024;
const MUTATION_LOCK_TIMEOUT_MS = 5000;
const MUTATION_LOCK_WAIT_MS = 5;
const STAGING_HANDOFF_RETRY_LIMIT = 8;
const MUTATION_WAIT_ARRAY = new Int32Array(new SharedArrayBuffer(4));
const ACTOR_TYPES = OBJECT_FREEZE(new Set(["human", "agent", "service", "tool"]));
const RETENTION_CLASSES = OBJECT_FREEZE(
  new Set(["ephemeral", "project", "regulated", "permanent"]),
);
const CONFIDENTIALITY_CLASSES = OBJECT_FREEZE(
  new Set(["public", "internal", "restricted", "secret"]),
);
const VALIDATION_STATUSES = OBJECT_FREEZE(new Set(["PASS", "FAIL", "NOT_RUN"]));
const RESERVED_VALIDATION_CHECKS = OBJECT_FREEZE(
  new Set(["content_sha256", "artifact_manifest_sha256"]),
);
const METADATA_KEYS = OBJECT_FREEZE(["artifact", "receipt"]);
const ARTIFACT_METADATA_KEYS = OBJECT_FREEZE([
  "artifactId",
  "artifactType",
  "confidentiality",
  "createdAt",
  "createdBy",
  "encryption",
  "inputArtifactIds",
  "license",
  "lineageEventIds",
  "mediaType",
  "provenanceManifestId",
  "retentionClass",
]);
const RECEIPT_METADATA_KEYS = OBJECT_FREEZE([
  "actionIntentId",
  "createdAt",
  "createdBy",
  "receiptId",
  "schemaRef",
  "validationResults",
]);

export const ARTIFACT_STORE_MODE = OBJECT_FREEZE({
  ACTIVE: "ACTIVE",
  SAFE_MODE: "SAFE_MODE",
});

export class ArtifactStoreError extends Error {
  constructor(code, message, details = undefined) {
    super(message);
    this.name = "ArtifactStoreError";
    this.code = code;
    if (details !== undefined) this.details = deepFreeze(details);
  }
}

const fail = (code, message, details) => {
  throw new ArtifactStoreError(code, message, details);
};

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object" || BUFFER_IS_BUFFER(value)) return value;
  if (IS_PROXY(value)) return value;
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < keys.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, keys[index]);
    if (descriptor !== undefined && OBJECT_HAS_OWN(descriptor, "value")) {
      deepFreeze(descriptor.value);
    }
  }
  return OBJECT_FREEZE(value);
};

const hasOnlyCanonicalUnicode = (value) => {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = STRING_CHAR_CODE_AT(value, index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const next = STRING_CHAR_CODE_AT(value, index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      return false;
    }
  }
  return true;
};

const requireString = (value, label, { allowEmpty = false } = {}) => {
  if (
    typeof value !== "string" ||
    (!allowEmpty && value.length === 0) ||
    !hasOnlyCanonicalUnicode(value)
  ) {
    fail("INVALID_INPUT", `${label} must be a canonical${allowEmpty ? "" : " non-empty"} string`);
  }
  return value;
};

const requireBoundedId = (value, label) => {
  const candidate = requireString(value, label);
  if (candidate.length < 3 || candidate.length > 128) {
    fail("INVALID_INPUT", `${label} must contain 3 to 128 characters`);
  }
  return candidate;
};

const requireNullableString = (value, label) =>
  value === null ? null : requireString(value, label);

const requirePlainObject = (value, label, expectedKeys) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    IS_PROXY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== PLAIN_OBJECT_PROTOTYPE
  ) {
    fail("INVALID_INPUT", `${label} must be a plain object`);
  }
  const keys = REFLECT_OWN_KEYS(value);
  if (keys.length !== expectedKeys.length) {
    fail("INVALID_INPUT", `${label} must contain exactly the canonical fields`);
  }
  const expected = new Set(expectedKeys);
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (typeof key !== "string" || !expected.has(key)) {
      fail("INVALID_INPUT", `${label} contains an unsupported field`);
    }
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, key);
    if (
      descriptor === undefined ||
      !descriptor.enumerable ||
      !OBJECT_HAS_OWN(descriptor, "value")
    ) {
      fail("INVALID_INPUT", `${label}.${key} must be an enumerable data property`);
    }
  }
  return value;
};

const readDataProperty = (object, key) =>
  OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(object, key).value;

const cloneStringArray = (value, label) => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) {
    fail("INVALID_INPUT", `${label} must be an array`);
  }
  const keys = REFLECT_OWN_KEYS(value);
  for (let index = 0; index < keys.length; index += 1) {
    const key = keys[index];
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(0|[1-9][0-9]*)$/u.test(key)) {
      fail("INVALID_INPUT", `${label} contains a non-element property`);
    }
  }
  const result = new Array(value.length);
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail("INVALID_INPUT", `${label} must not be sparse or accessor-backed`);
    }
    result[index] = requireString(descriptor.value, `${label}[${index}]`, { allowEmpty: true });
  }
  return result;
};

const isValidRfc3339 = (candidate) => {
  if (typeof candidate !== "string" || !hasOnlyCanonicalUnicode(candidate)) return false;
  const match = RFC3339_PATTERN.exec(candidate);
  if (match === null) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offsetHour = match[8] === undefined ? 0 : Number(match[8]);
  const offsetMinute = match[9] === undefined ? 0 : Number(match[9]);
  const calendar = new Date(Date.UTC(year, month - 1, day));
  return (
    month >= 1 &&
    month <= 12 &&
    day >= 1 &&
    calendar.getUTCFullYear() === year &&
    calendar.getUTCMonth() === month - 1 &&
    calendar.getUTCDate() === day &&
    hour <= 23 &&
    minute <= 59 &&
    second <= 59 &&
    offsetHour <= 23 &&
    offsetMinute <= 59 &&
    NUMBER_IS_FINITE(Date.parse(candidate))
  );
};

const validateRfc3339 = (value, label) => {
  const candidate = requireString(value, label);
  if (!isValidRfc3339(candidate)) {
    fail("INVALID_INPUT", `${label} is not a real RFC 3339 date-time`);
  }
  return candidate;
};

const cloneCreatedBy = (value, label = "createdBy") => {
  const object = requirePlainObject(value, label, ["actorId", "actorType"]);
  const actorId = requireBoundedId(readDataProperty(object, "actorId"), `${label}.actorId`);
  const actorType = requireString(readDataProperty(object, "actorType"), `${label}.actorType`);
  if (!ACTOR_TYPES.has(actorType)) {
    fail("INVALID_INPUT", `${label}.actorType is not canonical`);
  }
  return { actorId, actorType };
};

const cloneEncryption = (value) => {
  const object = requirePlainObject(value, "artifact.encryption", [
    "atRest",
    "inTransit",
    "keyRef",
  ]);
  const atRest = readDataProperty(object, "atRest");
  const inTransit = readDataProperty(object, "inTransit");
  if (typeof atRest !== "boolean" || typeof inTransit !== "boolean") {
    fail("INVALID_INPUT", "artifact.encryption flags must be booleans");
  }
  return {
    atRest,
    inTransit,
    keyRef: requireNullableString(
      readDataProperty(object, "keyRef"),
      "artifact.encryption.keyRef",
    ),
  };
};

const cloneValidationResults = (value) => {
  if (!ARRAY_IS_ARRAY(value) || IS_PROXY(value)) {
    fail("INVALID_INPUT", "receipt.validationResults must be an array");
  }
  const result = new Array(value.length);
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = OBJECT_GET_OWN_PROPERTY_DESCRIPTOR(value, String(index));
    if (descriptor === undefined || !OBJECT_HAS_OWN(descriptor, "value")) {
      fail("INVALID_INPUT", "receipt.validationResults must not be sparse or accessor-backed");
    }
    const row = requirePlainObject(
      descriptor.value,
      `receipt.validationResults[${index}]`,
      ["check", "details", "status"],
    );
    const check = requireString(
      readDataProperty(row, "check"),
      `receipt.validationResults[${index}].check`,
    );
    const status = requireString(
      readDataProperty(row, "status"),
      `receipt.validationResults[${index}].status`,
    );
    const details = requireString(
      readDataProperty(row, "details"),
      `receipt.validationResults[${index}].details`,
      { allowEmpty: true },
    );
    if (!VALIDATION_STATUSES.has(status)) {
      fail("INVALID_INPUT", `receipt.validationResults[${index}].status is not canonical`);
    }
    if (RESERVED_VALIDATION_CHECKS.has(check)) {
      fail("INVALID_INPUT", `${check} is reserved for store integrity evidence`);
    }
    result[index] = { check, status, details };
  }
  return result;
};

const normalizeMetadata = (value) => {
  const metadata = requirePlainObject(value, "metadata", METADATA_KEYS);
  const artifact = requirePlainObject(
    readDataProperty(metadata, "artifact"),
    "metadata.artifact",
    ARTIFACT_METADATA_KEYS,
  );
  const receipt = requirePlainObject(
    readDataProperty(metadata, "receipt"),
    "metadata.receipt",
    RECEIPT_METADATA_KEYS,
  );
  const retentionClass = requireString(
    readDataProperty(artifact, "retentionClass"),
    "artifact.retentionClass",
  );
  const confidentiality = requireString(
    readDataProperty(artifact, "confidentiality"),
    "artifact.confidentiality",
  );
  if (!RETENTION_CLASSES.has(retentionClass)) {
    fail("INVALID_INPUT", "artifact.retentionClass is not canonical");
  }
  if (!CONFIDENTIALITY_CLASSES.has(confidentiality)) {
    fail("INVALID_INPUT", "artifact.confidentiality is not canonical");
  }
  return deepFreeze({
    artifact: {
      artifactId: requireBoundedId(
        readDataProperty(artifact, "artifactId"),
        "artifact.artifactId",
      ),
      artifactType: requireString(
        readDataProperty(artifact, "artifactType"),
        "artifact.artifactType",
      ),
      confidentiality,
      createdAt: validateRfc3339(
        readDataProperty(artifact, "createdAt"),
        "artifact.createdAt",
      ),
      createdBy: requireString(
        readDataProperty(artifact, "createdBy"),
        "artifact.createdBy",
      ),
      encryption: cloneEncryption(readDataProperty(artifact, "encryption")),
      inputArtifactIds: cloneStringArray(
        readDataProperty(artifact, "inputArtifactIds"),
        "artifact.inputArtifactIds",
      ),
      license: requireNullableString(readDataProperty(artifact, "license"), "artifact.license"),
      lineageEventIds: cloneStringArray(
        readDataProperty(artifact, "lineageEventIds"),
        "artifact.lineageEventIds",
      ),
      mediaType: requireString(readDataProperty(artifact, "mediaType"), "artifact.mediaType"),
      provenanceManifestId: requireString(
        readDataProperty(artifact, "provenanceManifestId"),
        "artifact.provenanceManifestId",
      ),
      retentionClass,
    },
    receipt: {
      actionIntentId: requireNullableString(
        readDataProperty(receipt, "actionIntentId"),
        "receipt.actionIntentId",
      ),
      createdAt: validateRfc3339(
        readDataProperty(receipt, "createdAt"),
        "receipt.createdAt",
      ),
      createdBy: cloneCreatedBy(readDataProperty(receipt, "createdBy"), "receipt.createdBy"),
      receiptId: requireBoundedId(
        readDataProperty(receipt, "receiptId"),
        "receipt.receiptId",
      ),
      schemaRef: requireNullableString(
        readDataProperty(receipt, "schemaRef"),
        "receipt.schemaRef",
      ),
      validationResults: cloneValidationResults(
        readDataProperty(receipt, "validationResults"),
      ),
    },
  });
};

const copyBytes = (value) => {
  if (IS_PROXY(value)) fail("INVALID_INPUT", "bytes must not be a Proxy");
  if (BUFFER_IS_BUFFER(value)) return Buffer.from(value);
  if (value instanceof Uint8Array && OBJECT_GET_PROTOTYPE_OF(value) === Uint8Array.prototype) {
    return Buffer.from(value);
  }
  fail("INVALID_INPUT", "bytes must be a Buffer or plain Uint8Array");
};

const canonicalJson = (value) => {
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!NUMBER_IS_FINITE(value) || !NUMBER_IS_SAFE_INTEGER(value) || Object.is(value, -0)) {
      fail("NON_CANONICAL_JSON", "canonical JSON accepts finite safe integers only");
    }
    return String(value);
  }
  if (ARRAY_IS_ARRAY(value)) {
    let output = "[";
    for (let index = 0; index < value.length; index += 1) {
      if (index !== 0) output += ",";
      output += canonicalJson(value[index]);
    }
    return `${output}]`;
  }
  if (value === undefined || typeof value !== "object") {
    fail("NON_CANONICAL_JSON", "canonical JSON contains an unsupported value");
  }
  const keys = Object.keys(value);
  ARRAY_SORT(keys);
  let output = "{";
  for (let index = 0; index < keys.length; index += 1) {
    if (index !== 0) output += ",";
    const key = keys[index];
    output += `${JSON.stringify(key)}:${canonicalJson(value[key])}`;
  }
  return `${output}}`;
};

const sha256Buffer = (bytes) => createHash("sha256").update(bytes).digest("hex");
const sha256Text = (text) => sha256Buffer(Buffer.from(text, "utf8"));
const schemaDigest = (hex) => `sha256:${hex}`;
const artifactLocator = (hex) => `artifact://sha256/${hex}`;
const artifactKeyForId = (artifactId) => sha256Text(`artifact-id\u0000${artifactId}`);
const receiptKeyForId = (receiptId) => sha256Text(`receipt-id\u0000${receiptId}`);
const renderCanonicalDocument = (document) => `${canonicalJson(document)}\n`;

const buildDocuments = (bytes, metadata) => {
  const digestHex = sha256Buffer(bytes);
  const contentHash = schemaDigest(digestHex);
  const locator = artifactLocator(digestHex);
  const manifest = {
    artifact_id: metadata.artifact.artifactId,
    artifact_type: metadata.artifact.artifactType,
    byte_size: bytes.length,
    confidentiality: metadata.artifact.confidentiality,
    content_hash: contentHash,
    created_at: metadata.artifact.createdAt,
    created_by: metadata.artifact.createdBy,
    encryption: {
      at_rest: metadata.artifact.encryption.atRest,
      in_transit: metadata.artifact.encryption.inTransit,
      key_ref: metadata.artifact.encryption.keyRef,
    },
    input_artifact_ids: [...metadata.artifact.inputArtifactIds],
    integrity_status: "verified",
    license: metadata.artifact.license,
    lineage_event_ids: [...metadata.artifact.lineageEventIds],
    media_type: metadata.artifact.mediaType,
    provenance_manifest_id: metadata.artifact.provenanceManifestId,
    retention_class: metadata.artifact.retentionClass,
    storage_uri: locator,
  };
  const manifestText = renderCanonicalDocument(manifest);
  const manifestHash = schemaDigest(sha256Text(manifestText.slice(0, -1)));
  const receiptWithoutHash = {
    action_intent_id: metadata.receipt.actionIntentId,
    artifact_id: manifest.artifact_id,
    byte_size: bytes.length,
    content_hash: contentHash,
    created_at: metadata.receipt.createdAt,
    created_by: {
      actor_id: metadata.receipt.createdBy.actorId,
      actor_type: metadata.receipt.createdBy.actorType,
    },
    locator,
    media_type: metadata.artifact.mediaType,
    receipt_id: metadata.receipt.receiptId,
    schema_ref: metadata.receipt.schemaRef,
    validation_results: [
      { check: "content_sha256", status: "PASS", details: contentHash },
      { check: "artifact_manifest_sha256", status: "PASS", details: manifestHash },
      ...metadata.receipt.validationResults.map((row) => ({ ...row })),
    ],
  };
  const receipt = {
    ...receiptWithoutHash,
    receipt_hash: schemaDigest(sha256Text(canonicalJson(receiptWithoutHash))),
  };
  return deepFreeze({
    artifactKey: artifactKeyForId(manifest.artifact_id),
    digestHex,
    manifest: deepFreeze(manifest),
    manifestText,
    receipt: deepFreeze(receipt),
    receiptKey: receiptKeyForId(receipt.receipt_id),
    receiptText: renderCanonicalDocument(receipt),
  });
};

const normalizeRootPath = (rootPath) => {
  const candidate = requireString(rootPath, "rootPath");
  if (STRING_STARTS_WITH(candidate, "file:")) {
    fail("INVALID_INPUT", "rootPath must be a filesystem path, not a URL");
  }
  return path.resolve(candidate);
};

const pathIdentity = (stats) => ({ dev: stats.dev, ino: stats.ino });
const sameIdentity = (left, right) => left.dev === right.dev && left.ino === right.ino;

const requireDirectory = (candidate, code = "ARTIFACT_STORE_STRUCTURE_INVALID") => {
  let stats;
  try {
    stats = withTransientFsRetry(() => lstatSync(candidate));
  } catch (error) {
    fail(code, "required artifact-store directory is unavailable", {
      path: candidate,
      cause: error instanceof Error ? error.code ?? error.name : "unknown",
    });
  }
  if (stats.isSymbolicLink() || !stats.isDirectory()) {
    fail(code, "artifact-store path must be a real directory", { path: candidate });
  }
  return stats;
};

const ensureDirectory = (candidate) => {
  try {
    mkdirSync(candidate, { recursive: false, mode: 0o700 });
  } catch (error) {
    if (!(error instanceof Error) || error.code !== "EEXIST") throw error;
  }
  return requireDirectory(candidate);
};

const secureReadFile = (candidate, { maximumBytes = undefined } = {}) => {
  let before;
  try {
    before = withTransientFsRetry(() => lstatSync(candidate));
  } catch (error) {
    fail("ARTIFACT_FILE_UNAVAILABLE", "artifact record file is unavailable", {
      path: candidate,
      cause: error instanceof Error ? error.code ?? error.name : "unknown",
    });
  }
  if (before.isSymbolicLink() || !before.isFile() || before.nlink !== 1) {
    fail("ARTIFACT_FILE_IDENTITY_INVALID", "artifact record file is not a single regular file", {
      path: candidate,
    });
  }
  if (maximumBytes !== undefined && before.size > maximumBytes) {
    fail("ARTIFACT_METADATA_TOO_LARGE", "artifact metadata exceeds its bounded size", {
      path: candidate,
      size: before.size,
    });
  }
  let descriptor;
  try {
    descriptor = withTransientFsRetry(() => openSync(candidate, fsConstants.O_RDONLY));
  } catch (error) {
    fail("ARTIFACT_FILE_UNAVAILABLE", "artifact record file could not be opened", {
      path: candidate,
      cause: error instanceof Error ? error.code ?? error.name : "unknown",
    });
  }
  try {
    const opened = fstatSync(descriptor);
    if (!opened.isFile() || opened.nlink !== 1 || !sameIdentity(pathIdentity(before), pathIdentity(opened))) {
      fail("ARTIFACT_FILE_IDENTITY_CHANGED", "artifact record file changed during open", {
        path: candidate,
      });
    }
    const bytes = readFileSync(descriptor);
    const after = fstatSync(descriptor);
    if (
      !sameIdentity(pathIdentity(opened), pathIdentity(after)) ||
      after.size !== opened.size ||
      after.mtimeMs !== opened.mtimeMs
    ) {
      fail("ARTIFACT_FILE_CHANGED_DURING_READ", "artifact record file changed during read", {
        path: candidate,
      });
    }
    let current;
    try {
      current = lstatSync(candidate);
    } catch (error) {
      fail("ARTIFACT_FILE_IDENTITY_CHANGED", "artifact record path changed during read", {
        path: candidate,
        cause: error instanceof Error ? error.code ?? error.name : "unknown",
      });
    }
    if (
      current.isSymbolicLink() ||
      !current.isFile() ||
      current.nlink !== 1 ||
      !sameIdentity(pathIdentity(opened), pathIdentity(current))
    ) {
      fail("ARTIFACT_FILE_IDENTITY_CHANGED", "artifact record path changed during read", {
        path: candidate,
      });
    }
    return bytes;
  } finally {
    closeSync(descriptor);
  }
};

const writeExclusive = (candidate, bytes) => {
  const descriptor = openSync(
    candidate,
    fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL,
    0o600,
  );
  try {
    let offset = 0;
    while (offset < bytes.length) {
      offset += writeSync(descriptor, bytes, offset, bytes.length - offset);
    }
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
};

const fsyncDirectory = (candidate) => {
  let descriptor;
  try {
    descriptor = openSync(candidate, fsConstants.O_RDONLY);
    fsyncSync(descriptor);
    return true;
  } catch (error) {
    if (
      process.platform === "win32" &&
      error instanceof Error &&
      ["EACCES", "EISDIR", "EINVAL", "EPERM"].includes(error.code)
    ) {
      return false;
    }
    throw error;
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
  }
};

const parseCanonicalDocument = (bytes, label) => {
  let text;
  let document;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    document = JSON.parse(text);
  } catch (error) {
    fail(`${label}_INVALID`, `${label} is not canonical UTF-8 JSON`, {
      cause: error instanceof Error ? error.name : "unknown",
    });
  }
  if (text !== renderCanonicalDocument(document)) {
    fail(`${label}_NON_CANONICAL`, `${label} bytes are not canonical JSON`);
  }
  return document;
};

const exactObjectKeys = (value, expected, label) => {
  if (
    value === null ||
    typeof value !== "object" ||
    ARRAY_IS_ARRAY(value) ||
    OBJECT_GET_PROTOTYPE_OF(value) !== PLAIN_OBJECT_PROTOTYPE
  ) {
    fail(`${label}_INVALID`, `${label} must be an object`);
  }
  const actual = Object.keys(value);
  ARRAY_SORT(actual);
  const sortedExpected = [...expected];
  ARRAY_SORT(sortedExpected);
  if (canonicalJson(actual) !== canonicalJson(sortedExpected)) {
    fail(`${label}_INVALID`, `${label} has a non-canonical field set`);
  }
};

const isStringArray = (value) =>
  ARRAY_IS_ARRAY(value) && value.every((entry) => typeof entry === "string");

const validateManifestShape = (manifest) => {
  exactObjectKeys(
    manifest,
    [
      "artifact_id",
      "artifact_type",
      "byte_size",
      "confidentiality",
      "content_hash",
      "created_at",
      "created_by",
      "encryption",
      "input_artifact_ids",
      "integrity_status",
      "license",
      "lineage_event_ids",
      "media_type",
      "provenance_manifest_id",
      "retention_class",
      "storage_uri",
    ],
    "ARTIFACT_MANIFEST",
  );
  if (
    typeof manifest.artifact_id !== "string" ||
    manifest.artifact_id.length < 3 ||
    manifest.artifact_id.length > 128 ||
    !hasOnlyCanonicalUnicode(manifest.artifact_id) ||
    typeof manifest.artifact_type !== "string" ||
    manifest.artifact_type.length === 0 ||
    !NUMBER_IS_SAFE_INTEGER(manifest.byte_size) ||
    manifest.byte_size < 0 ||
    !CONFIDENTIALITY_CLASSES.has(manifest.confidentiality) ||
    !SHA256_PATTERN.test(manifest.content_hash) ||
    !isValidRfc3339(manifest.created_at) ||
    typeof manifest.created_by !== "string" ||
    manifest.created_by.length === 0 ||
    !isStringArray(manifest.input_artifact_ids) ||
    manifest.integrity_status !== "verified" ||
    !(manifest.license === null || typeof manifest.license === "string") ||
    !isStringArray(manifest.lineage_event_ids) ||
    typeof manifest.media_type !== "string" ||
    manifest.media_type.length === 0 ||
    typeof manifest.provenance_manifest_id !== "string" ||
    manifest.provenance_manifest_id.length === 0 ||
    !RETENTION_CLASSES.has(manifest.retention_class) ||
    typeof manifest.storage_uri !== "string" ||
    manifest.storage_uri.length === 0
  ) {
    fail("ARTIFACT_MANIFEST_INVALID", "artifact manifest violates its canonical schema");
  }
  exactObjectKeys(manifest.encryption, ["at_rest", "in_transit", "key_ref"], "ARTIFACT_MANIFEST");
  if (
    typeof manifest.encryption.at_rest !== "boolean" ||
    typeof manifest.encryption.in_transit !== "boolean" ||
    !(manifest.encryption.key_ref === null || typeof manifest.encryption.key_ref === "string")
  ) {
    fail("ARTIFACT_MANIFEST_INVALID", "artifact manifest encryption is invalid");
  }
};

const validateReceiptShape = (receipt) => {
  exactObjectKeys(
    receipt,
    [
      "action_intent_id",
      "artifact_id",
      "byte_size",
      "content_hash",
      "created_at",
      "created_by",
      "locator",
      "media_type",
      "receipt_hash",
      "receipt_id",
      "schema_ref",
      "validation_results",
    ],
    "ARTIFACT_RECEIPT",
  );
  if (
    !(receipt.action_intent_id === null || typeof receipt.action_intent_id === "string") ||
    typeof receipt.artifact_id !== "string" ||
    receipt.artifact_id.length < 3 ||
    receipt.artifact_id.length > 128 ||
    !hasOnlyCanonicalUnicode(receipt.artifact_id) ||
    !NUMBER_IS_SAFE_INTEGER(receipt.byte_size) ||
    receipt.byte_size < 0 ||
    !SHA256_PATTERN.test(receipt.content_hash) ||
    !isValidRfc3339(receipt.created_at) ||
    typeof receipt.locator !== "string" ||
    receipt.locator.length === 0 ||
    typeof receipt.media_type !== "string" ||
    !SHA256_PATTERN.test(receipt.receipt_hash) ||
    typeof receipt.receipt_id !== "string" ||
    receipt.receipt_id.length < 3 ||
    receipt.receipt_id.length > 128 ||
    !hasOnlyCanonicalUnicode(receipt.receipt_id) ||
    !(receipt.schema_ref === null || typeof receipt.schema_ref === "string") ||
    !ARRAY_IS_ARRAY(receipt.validation_results) ||
    receipt.validation_results.length < 1
  ) {
    fail("ARTIFACT_RECEIPT_INVALID", "artifact receipt violates its canonical schema");
  }
  exactObjectKeys(receipt.created_by, ["actor_id", "actor_type"], "ARTIFACT_RECEIPT");
  if (
    typeof receipt.created_by.actor_id !== "string" ||
    receipt.created_by.actor_id.length < 3 ||
    receipt.created_by.actor_id.length > 128 ||
    !ACTOR_TYPES.has(receipt.created_by.actor_type)
  ) {
    fail("ARTIFACT_RECEIPT_INVALID", "artifact receipt creator is invalid");
  }
  for (let index = 0; index < receipt.validation_results.length; index += 1) {
    const row = receipt.validation_results[index];
    exactObjectKeys(row, ["check", "details", "status"], "ARTIFACT_RECEIPT");
    if (
      typeof row.check !== "string" ||
      typeof row.details !== "string" ||
      !VALIDATION_STATUSES.has(row.status)
    ) {
      fail("ARTIFACT_RECEIPT_INVALID", "artifact receipt validation result is invalid");
    }
  }
};

const digestFromContentReference = (reference) => {
  const value = requireString(reference, "content reference");
  if (SHA256_PATTERN.test(value)) return value.slice("sha256:".length);
  const match = LOCATOR_PATTERN.exec(value);
  if (match !== null) return match[1];
  fail("INVALID_CONTENT_REFERENCE", "content reference must be a canonical hash or locator");
};

const recordPathForDigest = (objectsRoot, digestHex) =>
  path.join(objectsRoot, digestHex.slice(0, 2), digestHex.slice(2));

const registrationPathForKey = (recordPath, artifactKey) =>
  path.join(recordPath, ARTIFACTS_DIRECTORY, artifactKey);

const receiptPathForKey = (registrationPath, receiptKey) =>
  path.join(registrationPath, RECEIPTS_DIRECTORY, `${receiptKey}.json`);

const sortedDirectoryEntries = (candidate, code, details = undefined) => {
  try {
    const entries = withTransientFsRetry(() => readdirSync(candidate));
    ARRAY_SORT(entries);
    return entries;
  } catch (error) {
    fail(code, "artifact-store directory is unreadable", {
      ...(details ?? {}),
      cause: error instanceof Error ? error.code ?? error.name : "unknown",
    });
  }
};

const isTransientWindowsStagingError = (error) =>
  process.platform === "win32" &&
  error instanceof Error &&
  (error.code === "EPERM" || error.code === "EACCES");

const waitForStagingHandoff = () => {
  Atomics.wait(MUTATION_WAIT_ARRAY, 0, 0, MUTATION_LOCK_WAIT_MS);
};

// Under concurrent multi-worker access on Windows, an idempotent read/stat/open
// against a committed, write-once record can momentarily fail with a transient
// sharing violation (EPERM/EACCES/EBUSY) while another worker holds a fleeting
// handle on the parent directory during a commit rename. These are safe to
// retry within the same bounded handoff budget already used for staging scans;
// genuine errors (ENOENT, integrity mismatches) are not in this set and still
// surface immediately, so no integrity invariant is weakened.
const isTransientWindowsFsError = (error) =>
  process.platform === "win32" &&
  error instanceof Error &&
  (error.code === "EPERM" || error.code === "EACCES" || error.code === "EBUSY");

const withTransientFsRetry = (operation) => {
  let lastError;
  for (let attempt = 0; attempt <= STAGING_HANDOFF_RETRY_LIMIT; attempt += 1) {
    try {
      return operation();
    } catch (error) {
      lastError = error;
      if (!isTransientWindowsFsError(error) || attempt === STAGING_HANDOFF_RETRY_LIMIT) {
        throw error;
      }
      waitForStagingHandoff();
    }
  }
  throw lastError;
};

const sortedStagingDirectoryEntries = (candidate, code) => {
  let lastError;
  for (let attempt = 0; attempt <= STAGING_HANDOFF_RETRY_LIMIT; attempt += 1) {
    try {
      const entries = readdirSync(candidate);
      ARRAY_SORT(entries);
      return entries;
    } catch (error) {
      lastError = error;
      if (!isTransientWindowsStagingError(error) || attempt === STAGING_HANDOFF_RETRY_LIMIT) {
        break;
      }
      waitForStagingHandoff();
    }
  }
  fail(code, "artifact staging directory is unreadable", {
    path: candidate,
    cause: lastError instanceof Error ? lastError.code ?? lastError.name : "unknown",
  });
};

const inspectStagingEntry = (candidate, entry) => {
  let lastError;
  for (let attempt = 0; attempt <= STAGING_HANDOFF_RETRY_LIMIT; attempt += 1) {
    try {
      return lstatSync(candidate);
    } catch (error) {
      if (error instanceof Error && error.code === "ENOENT") return null;
      lastError = error;
      if (!isTransientWindowsStagingError(error) || attempt === STAGING_HANDOFF_RETRY_LIMIT) {
        break;
      }
      waitForStagingHandoff();
    }
  }
  fail("ARTIFACT_STORE_STRUCTURE_INVALID", "staging entry is unavailable", {
    entry,
    cause: lastError instanceof Error ? lastError.code ?? lastError.name : "unknown",
  });
};

const inspectMutationLock = (candidate, before) => {
  // The mutation lock is an inherently ephemeral directory: concurrent writers
  // legitimately release (rmdir) and re-acquire (mkdir) it, so its filesystem
  // identity can differ from the one observed a moment earlier in the parent
  // staging scan. That is a benign handoff, not a structural violation. The
  // real invariant is only that whenever the lock is present it is an empty,
  // real (non-symlink) directory. We therefore validate those properties on a
  // fresh stat and tolerate identity churn within the bounded handoff budget,
  // while still failing closed on a genuine symlink/non-directory/non-empty
  // lock or a persistent transient error.
  let reference = before;
  let lastError;
  for (let attempt = 0; attempt <= STAGING_HANDOFF_RETRY_LIMIT; attempt += 1) {
    try {
      const entries = readdirSync(candidate);
      if (entries.length !== 0) {
        fail("ARTIFACT_STORE_STRUCTURE_INVALID", "mutation lock must be an empty directory");
      }
      const after = lstatSync(candidate);
      if (after.isSymbolicLink() || !after.isDirectory()) {
        fail("ARTIFACT_STORE_STRUCTURE_INVALID", "mutation lock identity changed during scan");
      }
      if (!sameIdentity(pathIdentity(reference), pathIdentity(after))) {
        // Benign lock handoff between observations; re-observe within the bound
        // rather than failing closed on legitimate churn.
        if (attempt === STAGING_HANDOFF_RETRY_LIMIT) return true;
        reference = after;
        waitForStagingHandoff();
        continue;
      }
      return true;
    } catch (error) {
      if (error instanceof ArtifactStoreError) throw error;
      if (error instanceof Error && error.code === "ENOENT") return false;
      lastError = error;
      if (!isTransientWindowsStagingError(error) || attempt === STAGING_HANDOFF_RETRY_LIMIT) {
        break;
      }
      try {
        const current = lstatSync(candidate);
        if (current.isSymbolicLink() || !current.isDirectory()) {
          fail("ARTIFACT_STORE_STRUCTURE_INVALID", "mutation lock identity changed during scan");
        }
        // A differing identity here is the same benign handoff: adopt the fresh
        // observation and retry instead of failing closed.
        reference = current;
      } catch (probeError) {
        if (probeError instanceof ArtifactStoreError) throw probeError;
        if (probeError instanceof Error && probeError.code === "ENOENT") return false;
        if (!isTransientWindowsStagingError(probeError)) {
          fail("ARTIFACT_STORE_STRUCTURE_INVALID", "mutation lock identity is unavailable", {
            cause: probeError instanceof Error ? probeError.code ?? probeError.name : "unknown",
          });
        }
      }
      waitForStagingHandoff();
    }
  }
  fail("ARTIFACT_STORE_STRUCTURE_INVALID", "mutation lock is unreadable", {
    cause: lastError instanceof Error ? lastError.code ?? lastError.name : "unknown",
  });
};

const sameEntrySet = (actual, expected) => {
  const sortedExpected = [...expected];
  ARRAY_SORT(sortedExpected);
  return canonicalJson(actual) === canonicalJson(sortedExpected);
};

const validateReceiptDocument = ({
  digestHex,
  manifest,
  manifestHash,
  receipt,
  receiptKey,
}) => {
  validateReceiptShape(receipt);
  if (receiptKeyForId(receipt.receipt_id) !== receiptKey) {
    fail("ARTIFACT_RECEIPT_KEY_MISMATCH", "receipt ID does not match its opaque index key", {
      receiptId: receipt.receipt_id,
    });
  }
  const expectedContentHash = schemaDigest(digestHex);
  const expectedLocator = artifactLocator(digestHex);
  if (
    receipt.content_hash !== expectedContentHash ||
    receipt.artifact_id !== manifest.artifact_id ||
    receipt.locator !== expectedLocator ||
    receipt.byte_size !== manifest.byte_size ||
    receipt.media_type !== manifest.media_type
  ) {
    fail("ARTIFACT_RECEIPT_MISMATCH", "artifact receipt does not resolve bytes and manifest", {
      receiptId: receipt.receipt_id,
    });
  }
  const firstCheck = receipt.validation_results[0];
  const secondCheck = receipt.validation_results[1];
  if (
    receipt.validation_results.length < 2 ||
    firstCheck.check !== "content_sha256" ||
    firstCheck.status !== "PASS" ||
    firstCheck.details !== expectedContentHash ||
    secondCheck.check !== "artifact_manifest_sha256" ||
    secondCheck.status !== "PASS" ||
    secondCheck.details !== manifestHash
  ) {
    fail("ARTIFACT_RECEIPT_MISMATCH", "artifact receipt does not seal content and manifest", {
      receiptId: receipt.receipt_id,
    });
  }
  for (let index = 2; index < receipt.validation_results.length; index += 1) {
    if (RESERVED_VALIDATION_CHECKS.has(receipt.validation_results[index].check)) {
      fail("ARTIFACT_RECEIPT_MISMATCH", "reserved integrity evidence is duplicated", {
        receiptId: receipt.receipt_id,
      });
    }
  }
  const receiptWithoutHash = { ...receipt };
  delete receiptWithoutHash.receipt_hash;
  const expectedReceiptHash = schemaDigest(sha256Text(canonicalJson(receiptWithoutHash)));
  if (receipt.receipt_hash !== expectedReceiptHash) {
    fail("ARTIFACT_RECEIPT_HASH_MISMATCH", "artifact receipt self-hash is invalid", {
      expected: expectedReceiptHash,
      actual: receipt.receipt_hash,
      receiptId: receipt.receipt_id,
    });
  }
  return deepFreeze(receipt);
};

const validateRegistrationDirectory = ({
  artifactKey,
  digestHex,
  recordByteSize,
  registrationPath,
}) => {
  const openedRegistration = requireDirectory(
    registrationPath,
    "ARTIFACT_REGISTRATION_STRUCTURE_INVALID",
  );
  const names = sortedDirectoryEntries(
    registrationPath,
    "ARTIFACT_REGISTRATION_STRUCTURE_INVALID",
    { artifactKey },
  );
  if (!sameEntrySet(names, REGISTRATION_ENTRIES)) {
    if (names.includes(RECEIPTS_DIRECTORY) && !names.includes(MANIFEST_FILE)) {
      fail("ARTIFACT_ORPHAN_RECEIPT", "artifact receipts have no resolving manifest", {
        artifactKey,
      });
    }
    fail("ARTIFACT_RECORD_INCOMPLETE", "artifact registration is incomplete", {
      artifactKey,
      entries: names,
    });
  }
  const manifest = parseCanonicalDocument(
    secureReadFile(path.join(registrationPath, MANIFEST_FILE), {
      maximumBytes: MAX_METADATA_BYTES,
    }),
    "ARTIFACT_MANIFEST",
  );
  validateManifestShape(manifest);
  if (artifactKeyForId(manifest.artifact_id) !== artifactKey) {
    fail("ARTIFACT_MANIFEST_KEY_MISMATCH", "artifact ID does not match its opaque index key", {
      artifactId: manifest.artifact_id,
    });
  }
  const expectedContentHash = schemaDigest(digestHex);
  const expectedLocator = artifactLocator(digestHex);
  if (
    manifest.content_hash !== expectedContentHash ||
    manifest.storage_uri !== expectedLocator ||
    manifest.byte_size !== recordByteSize
  ) {
    fail("ARTIFACT_MANIFEST_MISMATCH", "artifact manifest does not resolve its addressed bytes", {
      artifactId: manifest.artifact_id,
    });
  }
  const receiptsPath = path.join(registrationPath, RECEIPTS_DIRECTORY);
  const openedReceipts = requireDirectory(receiptsPath, "ARTIFACT_REGISTRATION_STRUCTURE_INVALID");
  const receiptNames = sortedDirectoryEntries(
    receiptsPath,
    "ARTIFACT_REGISTRATION_STRUCTURE_INVALID",
    { artifactId: manifest.artifact_id },
  );
  if (receiptNames.length === 0) {
    fail("ARTIFACT_RECORD_INCOMPLETE", "artifact registration has no resolving receipt", {
      artifactId: manifest.artifact_id,
    });
  }
  const manifestHash = schemaDigest(sha256Text(canonicalJson(manifest)));
  const receipts = [];
  for (let index = 0; index < receiptNames.length; index += 1) {
    const match = RECEIPT_FILE_PATTERN.exec(receiptNames[index]);
    if (match === null) {
      fail("ARTIFACT_REGISTRATION_STRUCTURE_INVALID", "receipt index contains a non-canonical file", {
        artifactId: manifest.artifact_id,
        entry: receiptNames[index],
      });
    }
    const receipt = parseCanonicalDocument(
      secureReadFile(path.join(receiptsPath, receiptNames[index]), {
        maximumBytes: MAX_METADATA_BYTES,
      }),
      "ARTIFACT_RECEIPT",
    );
    receipts.push(
      validateReceiptDocument({
        digestHex,
        manifest,
        manifestHash,
        receipt,
        receiptKey: match[1],
      }),
    );
  }
  const currentReceipts = requireDirectory(
    receiptsPath,
    "ARTIFACT_REGISTRATION_IDENTITY_CHANGED",
  );
  if (!sameIdentity(pathIdentity(openedReceipts), pathIdentity(currentReceipts))) {
    fail("ARTIFACT_REGISTRATION_IDENTITY_CHANGED", "receipt directory changed during read", {
      artifactId: manifest.artifact_id,
    });
  }
  const currentRegistration = requireDirectory(
    registrationPath,
    "ARTIFACT_REGISTRATION_IDENTITY_CHANGED",
  );
  if (!sameIdentity(pathIdentity(openedRegistration), pathIdentity(currentRegistration))) {
    fail("ARTIFACT_REGISTRATION_IDENTITY_CHANGED", "artifact registration changed during read", {
      artifactId: manifest.artifact_id,
    });
  }
  return deepFreeze({
    artifactKey,
    manifest: deepFreeze(manifest),
    receipts: deepFreeze(receipts),
  });
};

const validateObjectDirectory = (recordPath, digestHex, { includeBytes = false } = {}) => {
  const openedRecord = requireDirectory(recordPath, "ARTIFACT_RECORD_STRUCTURE_INVALID");
  const names = sortedDirectoryEntries(recordPath, "ARTIFACT_RECORD_STRUCTURE_INVALID", {
    digest: digestHex,
  });
  if (!sameEntrySet(names, OBJECT_ENTRIES)) {
    if (names.includes(ARTIFACTS_DIRECTORY) && !names.includes(CONTENT_FILE)) {
      fail("ARTIFACT_ORPHAN_RECEIPT", "artifact registrations have no resolving bytes", {
        digest: digestHex,
      });
    }
    fail("ARTIFACT_RECORD_INCOMPLETE", "content object is incomplete", {
      digest: digestHex,
      entries: names,
    });
  }
  const content = secureReadFile(path.join(recordPath, CONTENT_FILE));
  const actualDigest = sha256Buffer(content);
  if (actualDigest !== digestHex) {
    fail("ARTIFACT_HASH_MISMATCH", "artifact bytes do not match their content address", {
      expected: schemaDigest(digestHex),
      actual: schemaDigest(actualDigest),
    });
  }
  const artifactsPath = path.join(recordPath, ARTIFACTS_DIRECTORY);
  const openedArtifacts = requireDirectory(artifactsPath, "ARTIFACT_RECORD_STRUCTURE_INVALID");
  const artifactKeys = sortedDirectoryEntries(
    artifactsPath,
    "ARTIFACT_RECORD_STRUCTURE_INVALID",
    { digest: digestHex },
  );
  if (artifactKeys.length === 0) {
    fail("ARTIFACT_RECORD_INCOMPLETE", "content object has no artifact registration", {
      digest: digestHex,
    });
  }
  const registrations = [];
  for (let index = 0; index < artifactKeys.length; index += 1) {
    if (!ID_KEY_PATTERN.test(artifactKeys[index])) {
      fail("ARTIFACT_RECORD_STRUCTURE_INVALID", "artifact index contains a non-canonical key", {
        digest: digestHex,
        entry: artifactKeys[index],
      });
    }
    registrations.push(
      validateRegistrationDirectory({
        artifactKey: artifactKeys[index],
        digestHex,
        recordByteSize: content.length,
        registrationPath: path.join(artifactsPath, artifactKeys[index]),
      }),
    );
  }
  const currentArtifacts = requireDirectory(
    artifactsPath,
    "ARTIFACT_RECORD_IDENTITY_CHANGED",
  );
  if (!sameIdentity(pathIdentity(openedArtifacts), pathIdentity(currentArtifacts))) {
    fail("ARTIFACT_RECORD_IDENTITY_CHANGED", "artifact index changed during read", {
      digest: digestHex,
    });
  }
  const currentRecord = requireDirectory(recordPath, "ARTIFACT_RECORD_IDENTITY_CHANGED");
  if (!sameIdentity(pathIdentity(openedRecord), pathIdentity(currentRecord))) {
    fail("ARTIFACT_RECORD_IDENTITY_CHANGED", "content object changed during read", {
      digest: digestHex,
    });
  }
  return deepFreeze({
    bytes: includeBytes ? Buffer.from(content) : null,
    digestHex,
    registrations: deepFreeze(registrations),
  });
};

const createStage = (stagingRoot) => {
  const stagePath = path.join(stagingRoot, `.stage-${randomUUID()}`);
  mkdirSync(stagePath, { recursive: false, mode: 0o700 });
  return stagePath;
};

const safeRemoveTree = (candidate) => {
  const stats = lstatSync(candidate);
  if (stats.isSymbolicLink()) {
    fail("ARTIFACT_STAGE_CLEANUP_FAILED", "staging tree contains a symbolic link");
  }
  if (stats.isFile()) {
    if (stats.nlink !== 1) {
      fail("ARTIFACT_STAGE_CLEANUP_FAILED", "staging tree contains a hard-linked file");
    }
    unlinkSync(candidate);
    return;
  }
  if (!stats.isDirectory()) {
    fail("ARTIFACT_STAGE_CLEANUP_FAILED", "staging tree contains an unsupported entry");
  }
  const entries = readdirSync(candidate);
  for (let index = 0; index < entries.length; index += 1) {
    safeRemoveTree(path.join(candidate, entries[index]));
  }
  rmdirSync(candidate);
};

const safeCleanupStage = (stagingRoot, stagePath) => {
  if (!existsSync(stagePath)) return;
  if (path.dirname(stagePath) !== stagingRoot || !STAGE_PATTERN.test(path.basename(stagePath))) {
    fail("ARTIFACT_STAGE_CLEANUP_FAILED", "staging cleanup target is outside the canonical root");
  }
  safeRemoveTree(stagePath);
};

const isPublishConflict = (error) =>
  error instanceof Error && ["EEXIST", "ENOTEMPTY", "EPERM", "EACCES"].includes(error.code);

// A commit rename of a private stage into its unique, not-yet-existing final
// path is idempotent. On Windows a concurrent lock-free reader that momentarily
// holds a handle on the target's parent can make that rename fail with a
// transient sharing violation (EPERM/EACCES/EBUSY, and occasionally
// EEXIST/ENOTEMPTY when the parent is being enumerated) even though the final
// path is absent. Retry those within the bounded handoff budget. A genuine
// publish conflict — the content address already committed by an earlier write
// (target exists) — is re-thrown immediately so the caller's conflict handling
// (ARTIFACT_PUBLISH_CONFLICT) still fires; a persistent transient error still
// escapes after the bound and fails closed.
const commitRename = (source, target) => {
  let lastError;
  for (let attempt = 0; attempt <= STAGING_HANDOFF_RETRY_LIMIT; attempt += 1) {
    try {
      renameSync(source, target);
      return;
    } catch (error) {
      lastError = error;
      if (isPublishConflict(error) && existsSync(target)) throw error;
      const transient =
        process.platform === "win32" &&
        error instanceof Error &&
        ["EPERM", "EACCES", "EBUSY", "EEXIST", "ENOTEMPTY"].includes(error.code);
      if (!transient || attempt === STAGING_HANDOFF_RETRY_LIMIT) throw error;
      waitForStagingHandoff();
    }
  }
  throw lastError;
};

const sameDocument = (left, right) => canonicalJson(left) === canonicalJson(right);

const waitForMutationLock = () => {
  Atomics.wait(MUTATION_WAIT_ARRAY, 0, 0, MUTATION_LOCK_WAIT_MS);
};

export class ContentAddressedArtifactStore {
  #rootPath;
  #objectsRoot;
  #stagingRoot;
  #mutationLockPath;
  #rootIdentity;
  #objectsIdentity;
  #stagingIdentity;
  #mode;
  #safeModeReason;
  #closed;

  constructor(token, fields) {
    if (token !== CONSTRUCTOR_TOKEN) {
      fail("DIRECT_CONSTRUCTION_DENIED", "use ContentAddressedArtifactStore.open()");
    }
    this.#rootPath = fields.rootPath;
    this.#objectsRoot = fields.objectsRoot;
    this.#stagingRoot = fields.stagingRoot;
    this.#mutationLockPath = path.join(fields.stagingRoot, MUTATION_LOCK);
    this.#rootIdentity = fields.rootIdentity;
    this.#objectsIdentity = fields.objectsIdentity;
    this.#stagingIdentity = fields.stagingIdentity;
    this.#mode = fields.mode;
    this.#safeModeReason = fields.safeModeReason;
    this.#closed = fields.closed ?? false;
  }

  static open(rootPath) {
    const resolvedRoot = normalizeRootPath(rootPath);
    const objectsRoot = path.join(resolvedRoot, HEX_DIRECTORY);
    const stagingRoot = path.join(resolvedRoot, STAGING_DIRECTORY);
    try {
      mkdirSync(resolvedRoot, { recursive: true, mode: 0o700 });
      const rootStats = requireDirectory(resolvedRoot, "ARTIFACT_STORE_ROOT_LINK_DENIED");
      const realRoot = realpathSync.native(resolvedRoot);
      const comparableResolved =
        process.platform === "win32" ? STRING_TO_LOWER_CASE(resolvedRoot) : resolvedRoot;
      const comparableReal =
        process.platform === "win32" ? STRING_TO_LOWER_CASE(realRoot) : realRoot;
      if (comparableResolved !== comparableReal) {
        fail("ARTIFACT_STORE_ROOT_LINK_DENIED", "artifact store root must not resolve through a link");
      }
      const objectsStats = ensureDirectory(objectsRoot);
      const stagingStats = ensureDirectory(stagingRoot);
      const store = new ContentAddressedArtifactStore(CONSTRUCTOR_TOKEN, {
        rootPath: resolvedRoot,
        objectsRoot,
        stagingRoot,
        rootIdentity: pathIdentity(rootStats),
        objectsIdentity: pathIdentity(objectsStats),
        stagingIdentity: pathIdentity(stagingStats),
        mode: ARTIFACT_STORE_MODE.ACTIVE,
        safeModeReason: null,
      });
      const result = store.#validateTree();
      if (!result.ok) return store.#safe(result.code, result.details);
      return store;
    } catch (error) {
      if (error instanceof ArtifactStoreError && error.code === "INVALID_INPUT") throw error;
      const code = error instanceof ArtifactStoreError ? error.code : "ARTIFACT_STORE_OPEN_FAILED";
      const details =
        error instanceof ArtifactStoreError
          ? error.details
          : { cause: error instanceof Error ? error.code ?? error.name : "unknown" };
      return new ContentAddressedArtifactStore(CONSTRUCTOR_TOKEN, {
        rootPath: resolvedRoot,
        objectsRoot,
        stagingRoot,
        rootIdentity: null,
        objectsIdentity: null,
        stagingIdentity: null,
        mode: ARTIFACT_STORE_MODE.SAFE_MODE,
        safeModeReason: deepFreeze({ code, details }),
        closed: true,
      });
    }
  }

  get rootPath() {
    return this.#rootPath;
  }

  get mode() {
    return this.#mode;
  }

  get safeModeReason() {
    return this.#safeModeReason;
  }

  get isClosed() {
    return this.#closed;
  }

  health() {
    return deepFreeze({
      closed: this.#closed,
      mode: this.#mode,
      mutationLocked: existsSync(this.#mutationLockPath),
      rootPath: this.#rootPath,
      safeModeReason: this.#safeModeReason,
    });
  }

  putArtifact(bytes, metadata) {
    this.#assertReadable();
    const content = copyBytes(bytes);
    const normalizedMetadata = normalizeMetadata(metadata);
    const documents = buildDocuments(content, normalizedMetadata);
    return this.#withMutationLock(() => this.#putUnderLock(content, documents));
  }

  readObject(reference) {
    this.#assertReadable();
    const digestHex = digestFromContentReference(reference);
    const record = this.#readValidatedObject(digestHex, { includeBytes: true });
    return Buffer.from(record.bytes);
  }

  readArtifact(artifactId) {
    this.#assertReadable();
    const id = requireBoundedId(artifactId, "artifactId");
    const tree = this.#validatedTreeOrFail();
    const registration = tree.artifacts.find((entry) => entry.manifest.artifact_id === id);
    if (registration === undefined) {
      fail("ARTIFACT_NOT_FOUND", "artifact registration does not exist", { artifactId: id });
    }
    const record = this.#readValidatedObject(registration.digestHex, { includeBytes: true });
    const current = record.registrations.find((entry) => entry.manifest.artifact_id === id);
    if (current === undefined || !sameDocument(current.manifest, registration.manifest)) {
      this.#failSafe(
        "ARTIFACT_BINDING_CHANGED_DURING_READ",
        "artifact registration changed before its bytes were resolved",
        { artifactId: id },
      );
    }
    return Buffer.from(record.bytes);
  }

  readManifest(artifactId) {
    this.#assertReadable();
    const id = requireBoundedId(artifactId, "artifactId");
    const tree = this.#validatedTreeOrFail();
    const registration = tree.artifacts.find((entry) => entry.manifest.artifact_id === id);
    if (registration === undefined) {
      fail("ARTIFACT_NOT_FOUND", "artifact registration does not exist", { artifactId: id });
    }
    return registration.manifest;
  }

  readReceipt(receiptId) {
    this.#assertReadable();
    const id = requireBoundedId(receiptId, "receiptId");
    const tree = this.#validatedTreeOrFail();
    const entry = tree.receipts.find((candidate) => candidate.receipt.receipt_id === id);
    if (entry === undefined) {
      fail("ARTIFACT_RECEIPT_NOT_FOUND", "artifact receipt does not exist", { receiptId: id });
    }
    return entry.receipt;
  }

  resolveReceipt(receiptId) {
    this.#assertReadable();
    const id = requireBoundedId(receiptId, "receiptId");
    const tree = this.#validatedTreeOrFail();
    const entry = tree.receipts.find((candidate) => candidate.receipt.receipt_id === id);
    if (entry === undefined) {
      fail("ARTIFACT_RECEIPT_NOT_FOUND", "artifact receipt does not exist", { receiptId: id });
    }
    const record = this.#readValidatedObject(entry.digestHex, { includeBytes: true });
    const currentRegistration = record.registrations.find(
      (candidate) => candidate.manifest.artifact_id === entry.manifest.artifact_id,
    );
    const currentReceipt = currentRegistration?.receipts.find(
      (candidate) => candidate.receipt_id === id,
    );
    if (
      currentRegistration === undefined ||
      currentReceipt === undefined ||
      !sameDocument(currentRegistration.manifest, entry.manifest) ||
      !sameDocument(currentReceipt, entry.receipt)
    ) {
      this.#failSafe(
        "ARTIFACT_BINDING_CHANGED_DURING_READ",
        "artifact receipt changed before its bytes were resolved",
        { receiptId: id },
      );
    }
    return deepFreeze({
      artifactId: entry.manifest.artifact_id,
      bytes: Buffer.from(record.bytes),
      contentHash: entry.manifest.content_hash,
      createdBy: entry.receipt.created_by,
      manifest: entry.manifest,
      receipt: entry.receipt,
      schemaRef: entry.receipt.schema_ref,
    });
  }

  enumerateArtifacts() {
    this.#assertReadable();
    const tree = this.#validatedTreeOrFail();
    return deepFreeze(tree.artifacts.map((entry) => entry.manifest));
  }

  enumerateReceipts() {
    this.#assertReadable();
    const tree = this.#validatedTreeOrFail();
    return deepFreeze(tree.receipts.map((entry) => entry.receipt));
  }

  checkIntegrity() {
    this.#assertAvailable();
    const result = this.#validateTree();
    if (!result.ok) this.#enterSafeMode(result.code, result.details);
    return deepFreeze({
      artifactCount: result.artifacts?.length ?? 0,
      details: result.details ?? null,
      objectCount: result.objects?.length ?? 0,
      ok: result.ok,
      receiptCount: result.receipts?.length ?? 0,
      mode: this.#mode,
    });
  }

  close() {
    this.#closed = true;
  }

  #putUnderLock(content, documents) {
    const tree = this.#validatedTreeOrFail();
    const artifactEntry = tree.artifacts.find(
      (entry) => entry.manifest.artifact_id === documents.manifest.artifact_id,
    );
    const receiptEntry = tree.receipts.find(
      (entry) => entry.receipt.receipt_id === documents.receipt.receipt_id,
    );
    if (artifactEntry !== undefined && artifactEntry.digestHex !== documents.digestHex) {
      fail("ARTIFACT_ID_CONFLICT", "artifact ID is already bound to different bytes", {
        artifactId: documents.manifest.artifact_id,
        existingContentHash: artifactEntry.manifest.content_hash,
        requestedContentHash: documents.manifest.content_hash,
      });
    }
    if (receiptEntry !== undefined) {
      if (
        receiptEntry.digestHex !== documents.digestHex ||
        !sameDocument(receiptEntry.receipt, documents.receipt) ||
        !sameDocument(receiptEntry.manifest, documents.manifest)
      ) {
        fail("ARTIFACT_RECEIPT_ID_CONFLICT", "receipt ID is already bound to a different receipt", {
          receiptId: documents.receipt.receipt_id,
        });
      }
      return this.#resultForDocuments(documents, {
        artifactStatus: "EXISTING",
        objectStatus: "EXISTING",
        receiptStatus: "EXISTING",
      });
    }
    if (artifactEntry !== undefined && !sameDocument(artifactEntry.manifest, documents.manifest)) {
      fail("ARTIFACT_IMMUTABLE_CONFLICT", "artifact ID already has different immutable metadata", {
        artifactId: documents.manifest.artifact_id,
      });
    }
    const objectEntry = tree.objects.find((entry) => entry.digestHex === documents.digestHex);
    if (objectEntry === undefined) {
      this.#publishObject(content, documents);
      return this.#resultForDocuments(documents, {
        artifactStatus: "CREATED",
        objectStatus: "CREATED",
        receiptStatus: "CREATED",
      });
    }
    if (artifactEntry === undefined) {
      this.#publishRegistration(documents);
      return this.#resultForDocuments(documents, {
        artifactStatus: "CREATED",
        objectStatus: "EXISTING",
        receiptStatus: "CREATED",
      });
    }
    this.#publishReceipt(documents, artifactEntry.manifest);
    return this.#resultForDocuments(documents, {
      artifactStatus: "EXISTING",
      objectStatus: "EXISTING",
      receiptStatus: "CREATED",
    });
  }

  #publishObject(content, documents) {
    const finalPath = recordPathForDigest(this.#objectsRoot, documents.digestHex);
    const prefixPath = path.dirname(finalPath);
    if (!existsSync(prefixPath)) {
      try {
        mkdirSync(prefixPath, { recursive: false, mode: 0o700 });
        fsyncDirectory(this.#objectsRoot);
      } catch (error) {
        if (!(error instanceof Error) || error.code !== "EEXIST") throw error;
      }
    }
    requireDirectory(prefixPath, "ARTIFACT_STORE_STRUCTURE_INVALID");
    const stagePath = createStage(this.#stagingRoot);
    let committed = false;
    try {
      const registrationPath = this.#writeRegistrationTree(stagePath, documents);
      writeExclusive(path.join(stagePath, CONTENT_FILE), content);
      fsyncDirectory(path.join(registrationPath, RECEIPTS_DIRECTORY));
      fsyncDirectory(registrationPath);
      fsyncDirectory(path.join(stagePath, ARTIFACTS_DIRECTORY));
      fsyncDirectory(stagePath);
      validateObjectDirectory(stagePath, documents.digestHex);
      try {
        commitRename(stagePath, finalPath);
      } catch (error) {
        if (isPublishConflict(error) && existsSync(finalPath)) {
          safeCleanupStage(this.#stagingRoot, stagePath);
          fail("ARTIFACT_PUBLISH_CONFLICT", "content address appeared outside the mutation lock", {
            contentHash: documents.manifest.content_hash,
          });
        }
        throw error;
      }
      committed = true;
      fsyncDirectory(this.#stagingRoot);
      fsyncDirectory(prefixPath);
      validateObjectDirectory(finalPath, documents.digestHex);
    } catch (error) {
      this.#cleanupStageAfterFailure(stagePath, error, { committed });
    }
  }

  #publishRegistration(documents) {
    const recordPath = recordPathForDigest(this.#objectsRoot, documents.digestHex);
    const artifactsPath = path.join(recordPath, ARTIFACTS_DIRECTORY);
    const finalPath = registrationPathForKey(recordPath, documents.artifactKey);
    const stagePath = createStage(this.#stagingRoot);
    let committed = false;
    try {
      const stagedRegistration = this.#writeRegistrationTree(stagePath, documents, {
        includeArtifactsDirectory: false,
      });
      const content = secureReadFile(path.join(recordPath, CONTENT_FILE));
      validateRegistrationDirectory({
        artifactKey: documents.artifactKey,
        digestHex: documents.digestHex,
        recordByteSize: content.length,
        registrationPath: stagedRegistration,
      });
      fsyncDirectory(path.join(stagedRegistration, RECEIPTS_DIRECTORY));
      fsyncDirectory(stagedRegistration);
      fsyncDirectory(stagePath);
      try {
        commitRename(stagedRegistration, finalPath);
      } catch (error) {
        if (isPublishConflict(error) && existsSync(finalPath)) {
          fail("ARTIFACT_PUBLISH_CONFLICT", "artifact registration appeared outside the mutation lock", {
            artifactId: documents.manifest.artifact_id,
          });
        }
        throw error;
      }
      committed = true;
      rmdirSync(stagePath);
      fsyncDirectory(this.#stagingRoot);
      fsyncDirectory(artifactsPath);
      validateObjectDirectory(recordPath, documents.digestHex);
    } catch (error) {
      this.#cleanupStageAfterFailure(stagePath, error, { committed });
    }
  }

  #publishReceipt(documents, manifest) {
    const recordPath = recordPathForDigest(this.#objectsRoot, documents.digestHex);
    const registrationPath = registrationPathForKey(recordPath, documents.artifactKey);
    const receiptsPath = path.join(registrationPath, RECEIPTS_DIRECTORY);
    const finalPath = receiptPathForKey(registrationPath, documents.receiptKey);
    const stagePath = createStage(this.#stagingRoot);
    let committed = false;
    try {
      const stagedReceipt = path.join(stagePath, `${documents.receiptKey}.json`);
      writeExclusive(stagedReceipt, Buffer.from(documents.receiptText, "utf8"));
      const manifestHash = schemaDigest(sha256Text(canonicalJson(manifest)));
      validateReceiptDocument({
        digestHex: documents.digestHex,
        manifest,
        manifestHash,
        receipt: parseCanonicalDocument(
          secureReadFile(stagedReceipt, { maximumBytes: MAX_METADATA_BYTES }),
          "ARTIFACT_RECEIPT",
        ),
        receiptKey: documents.receiptKey,
      });
      fsyncDirectory(stagePath);
      try {
        commitRename(stagedReceipt, finalPath);
      } catch (error) {
        if (isPublishConflict(error) && existsSync(finalPath)) {
          fail("ARTIFACT_PUBLISH_CONFLICT", "receipt appeared outside the mutation lock", {
            receiptId: documents.receipt.receipt_id,
          });
        }
        throw error;
      }
      committed = true;
      rmdirSync(stagePath);
      fsyncDirectory(this.#stagingRoot);
      fsyncDirectory(receiptsPath);
      validateObjectDirectory(recordPath, documents.digestHex);
    } catch (error) {
      this.#cleanupStageAfterFailure(stagePath, error, { committed });
    }
  }

  #writeRegistrationTree(stagePath, documents, { includeArtifactsDirectory = true } = {}) {
    const artifactsPath = includeArtifactsDirectory
      ? path.join(stagePath, ARTIFACTS_DIRECTORY)
      : stagePath;
    if (includeArtifactsDirectory) mkdirSync(artifactsPath, { recursive: false, mode: 0o700 });
    const registrationPath = path.join(artifactsPath, documents.artifactKey);
    const receiptsPath = path.join(registrationPath, RECEIPTS_DIRECTORY);
    mkdirSync(registrationPath, { recursive: false, mode: 0o700 });
    mkdirSync(receiptsPath, { recursive: false, mode: 0o700 });
    writeExclusive(
      path.join(registrationPath, MANIFEST_FILE),
      Buffer.from(documents.manifestText, "utf8"),
    );
    writeExclusive(
      path.join(receiptsPath, `${documents.receiptKey}.json`),
      Buffer.from(documents.receiptText, "utf8"),
    );
    return registrationPath;
  }

  #cleanupStageAfterFailure(stagePath, originalError, { committed = false } = {}) {
    try {
      safeCleanupStage(this.#stagingRoot, stagePath);
    } catch (cleanupError) {
      const failure =
        cleanupError instanceof ArtifactStoreError
          ? cleanupError
          : new ArtifactStoreError(
              "ARTIFACT_STAGE_CLEANUP_FAILED",
              "staging cleanup failed after publish error",
              { cause: cleanupError instanceof Error ? cleanupError.code ?? cleanupError.name : "unknown" },
            );
      this.#enterSafeMode(failure.code, failure.details);
      throw failure;
    }
    const failure =
      originalError instanceof ArtifactStoreError
        ? originalError
        : new ArtifactStoreError("ARTIFACT_PUBLISH_FAILED", "artifact could not be atomically published", {
            cause: originalError instanceof Error ? originalError.code ?? originalError.name : "unknown",
          });
    if (committed || failure.code === "ARTIFACT_PUBLISH_CONFLICT") {
      this.#enterSafeMode(
        committed ? "ARTIFACT_COMMIT_RECONCILIATION_FAILED" : failure.code,
        {
          cause: failure.code,
          committed,
          originalDetails: failure.details ?? null,
        },
      );
    }
    throw failure;
  }

  #resultForDocuments(documents, statuses) {
    const tree = this.#validatedTreeOrFail();
    const artifact = tree.artifacts.find(
      (entry) => entry.manifest.artifact_id === documents.manifest.artifact_id,
    );
    const receipt = tree.receipts.find(
      (entry) => entry.receipt.receipt_id === documents.receipt.receipt_id,
    );
    if (artifact === undefined || receipt === undefined) {
      fail("ARTIFACT_COMMIT_RECONCILIATION_FAILED", "published artifact could not be reconciled");
    }
    return deepFreeze({
      artifactStatus: statuses.artifactStatus,
      manifest: artifact.manifest,
      objectStatus: statuses.objectStatus,
      receipt: receipt.receipt,
      receiptStatus: statuses.receiptStatus,
      status: statuses.receiptStatus === "EXISTING" ? "EXISTING" : "CREATED",
    });
  }

  #readValidatedObject(digestHex, options) {
    const recordPath = recordPathForDigest(this.#objectsRoot, digestHex);
    if (!existsSync(recordPath)) {
      fail("ARTIFACT_NOT_FOUND", "content object does not exist", {
        contentHash: schemaDigest(digestHex),
      });
    }
    try {
      return validateObjectDirectory(recordPath, digestHex, options);
    } catch (error) {
      const failure =
        error instanceof ArtifactStoreError
          ? error
          : new ArtifactStoreError(
              "ARTIFACT_STORE_INTEGRITY_FAILED",
              "content object could not be verified",
              { cause: error instanceof Error ? error.code ?? error.name : "unknown" },
            );
      this.#enterSafeMode(failure.code, failure.details);
      throw failure;
    }
  }

  #validatedTreeOrFail() {
    const result = this.#validateTree();
    if (!result.ok) {
      this.#enterSafeMode(result.code, result.details);
      fail(result.code, "artifact store integrity validation failed", result.details);
    }
    return result;
  }

  #validateTree() {
    try {
      this.#assertPathIdentities();
      const rootEntries = sortedDirectoryEntries(
        this.#rootPath,
        "ARTIFACT_STORE_STRUCTURE_INVALID",
      );
      if (!sameEntrySet(rootEntries, ROOT_ENTRIES)) {
        fail("ARTIFACT_STORE_STRUCTURE_INVALID", "artifact store root has unexpected entries", {
          entries: rootEntries,
        });
      }
      const stageEntries = sortedStagingDirectoryEntries(
        this.#stagingRoot,
        "ARTIFACT_STORE_STRUCTURE_INVALID",
      );
      for (let index = 0; index < stageEntries.length; index += 1) {
        const name = stageEntries[index];
        if (name !== MUTATION_LOCK && !STAGE_PATTERN.test(name)) {
          fail("ARTIFACT_STORE_STRUCTURE_INVALID", "staging root has an invalid entry", {
            entry: name,
          });
        }
        const stagePath = path.join(this.#stagingRoot, name);
        const before = inspectStagingEntry(stagePath, name);
        if (before === null) continue;
        if (before.isSymbolicLink() || !before.isDirectory()) {
          fail("ARTIFACT_STORE_STRUCTURE_INVALID", "staging entry must be a real directory", {
            entry: name,
          });
        }
        if (name === MUTATION_LOCK) {
          inspectMutationLock(stagePath, before);
        }
      }
      const objects = [];
      const artifacts = [];
      const receipts = [];
      const artifactIds = new Set();
      const receiptIds = new Set();
      const prefixes = sortedDirectoryEntries(
        this.#objectsRoot,
        "ARTIFACT_STORE_STRUCTURE_INVALID",
      );
      for (let prefixIndex = 0; prefixIndex < prefixes.length; prefixIndex += 1) {
        const prefix = prefixes[prefixIndex];
        if (!PREFIX_PATTERN.test(prefix)) {
          fail("ARTIFACT_STORE_STRUCTURE_INVALID", "content-address root has a non-hex prefix", {
            entry: prefix,
          });
        }
        const prefixPath = path.join(this.#objectsRoot, prefix);
        requireDirectory(prefixPath, "ARTIFACT_STORE_STRUCTURE_INVALID");
        const suffixes = sortedDirectoryEntries(prefixPath, "ARTIFACT_STORE_STRUCTURE_INVALID");
        for (let suffixIndex = 0; suffixIndex < suffixes.length; suffixIndex += 1) {
          const suffix = suffixes[suffixIndex];
          if (!SUFFIX_PATTERN.test(suffix)) {
            fail("ARTIFACT_STORE_STRUCTURE_INVALID", "content-address root has a non-hex record", {
              prefix,
              entry: suffix,
            });
          }
          const digestHex = `${prefix}${suffix}`;
          const object = validateObjectDirectory(
            path.join(prefixPath, suffix),
            digestHex,
          );
          objects.push(object);
          for (let artifactIndex = 0; artifactIndex < object.registrations.length; artifactIndex += 1) {
            const registration = object.registrations[artifactIndex];
            const artifactId = registration.manifest.artifact_id;
            if (artifactIds.has(artifactId)) {
              fail("ARTIFACT_DUPLICATE_ID", "artifact ID appears more than once", { artifactId });
            }
            artifactIds.add(artifactId);
            const artifactEntry = deepFreeze({
              artifactKey: registration.artifactKey,
              digestHex,
              manifest: registration.manifest,
            });
            artifacts.push(artifactEntry);
            for (let receiptIndex = 0; receiptIndex < registration.receipts.length; receiptIndex += 1) {
              const receipt = registration.receipts[receiptIndex];
              if (receiptIds.has(receipt.receipt_id)) {
                fail("ARTIFACT_DUPLICATE_RECEIPT_ID", "receipt ID appears more than once", {
                  receiptId: receipt.receipt_id,
                });
              }
              receiptIds.add(receipt.receipt_id);
              receipts.push(
                deepFreeze({
                  digestHex,
                  manifest: registration.manifest,
                  receipt,
                }),
              );
            }
          }
        }
      }
      artifacts.sort((left, right) =>
        left.manifest.artifact_id < right.manifest.artifact_id
          ? -1
          : left.manifest.artifact_id > right.manifest.artifact_id
            ? 1
            : 0,
      );
      receipts.sort((left, right) =>
        left.receipt.receipt_id < right.receipt.receipt_id
          ? -1
          : left.receipt.receipt_id > right.receipt.receipt_id
            ? 1
            : 0,
      );
      return deepFreeze({
        artifacts: deepFreeze(artifacts),
        objects: deepFreeze(objects),
        ok: true,
        receipts: deepFreeze(receipts),
      });
    } catch (error) {
      if (error instanceof ArtifactStoreError) {
        return deepFreeze({ ok: false, code: error.code, details: error.details ?? null });
      }
      return deepFreeze({
        ok: false,
        code: "ARTIFACT_STORE_INTEGRITY_FAILED",
        details: { cause: error instanceof Error ? error.code ?? error.name : "unknown" },
      });
    }
  }

  #withMutationLock(operation) {
    this.#assertReadable();
    const deadline = Date.now() + MUTATION_LOCK_TIMEOUT_MS;
    while (true) {
      try {
        mkdirSync(this.#mutationLockPath, { recursive: false, mode: 0o700 });
        fsyncDirectory(this.#stagingRoot);
        break;
      } catch (error) {
        if (!(error instanceof Error) || error.code !== "EEXIST") {
          const failure = new ArtifactStoreError(
            "ARTIFACT_MUTATION_LOCK_FAILED",
            "artifact mutation lock could not be acquired",
            { cause: error instanceof Error ? error.code ?? error.name : "unknown" },
          );
          this.#enterSafeMode(failure.code, failure.details);
          throw failure;
        }
        let lockStats;
        try {
          lockStats = lstatSync(this.#mutationLockPath);
        } catch (lockError) {
          if (lockError instanceof Error && lockError.code === "ENOENT") {
            continue;
          }
          const failure = new ArtifactStoreError(
            "ARTIFACT_MUTATION_LOCK_INVALID",
            "artifact mutation lock could not be inspected",
            { cause: lockError instanceof Error ? lockError.code ?? lockError.name : "unknown" },
          );
          this.#enterSafeMode(failure.code, failure.details);
          throw failure;
        }
        if (lockStats.isSymbolicLink() || !lockStats.isDirectory()) {
          const failure = new ArtifactStoreError(
            "ARTIFACT_MUTATION_LOCK_INVALID",
            "artifact mutation lock must be a real directory",
          );
          this.#enterSafeMode(failure.code, failure.details);
          throw failure;
        }
        if (Date.now() >= deadline) {
          fail("ARTIFACT_STORE_BUSY", "artifact mutation lock acquisition timed out");
        }
        waitForMutationLock();
      }
    }
    let result;
    let operationError;
    try {
      result = operation();
    } catch (error) {
      operationError = error;
    }
    try {
      rmdirSync(this.#mutationLockPath);
      fsyncDirectory(this.#stagingRoot);
    } catch (error) {
      const failure = new ArtifactStoreError(
        "ARTIFACT_MUTATION_LOCK_RELEASE_FAILED",
        "artifact mutation lock could not be released",
        {
          cause: error instanceof Error ? error.code ?? error.name : "unknown",
          operationError:
            operationError instanceof ArtifactStoreError
              ? operationError.code
              : operationError instanceof Error
                ? operationError.name
                : null,
        },
      );
      this.#enterSafeMode(failure.code, failure.details);
      throw failure;
    }
    if (operationError !== undefined) throw operationError;
    return result;
  }

  #assertPathIdentities() {
    const rootStats = requireDirectory(this.#rootPath, "ARTIFACT_STORE_IDENTITY_CHANGED");
    if (!sameIdentity(pathIdentity(rootStats), this.#rootIdentity)) {
      fail("ARTIFACT_STORE_IDENTITY_CHANGED", "artifact store root identity changed");
    }
    const objectsStats = requireDirectory(
      this.#objectsRoot,
      "ARTIFACT_STORE_IDENTITY_CHANGED",
    );
    const stagingStats = requireDirectory(
      this.#stagingRoot,
      "ARTIFACT_STORE_IDENTITY_CHANGED",
    );
    if (
      !sameIdentity(pathIdentity(objectsStats), this.#objectsIdentity) ||
      !sameIdentity(pathIdentity(stagingStats), this.#stagingIdentity)
    ) {
      fail("ARTIFACT_STORE_IDENTITY_CHANGED", "artifact store directory identity changed");
    }
  }

  #assertAvailable() {
    if (this.#mode === ARTIFACT_STORE_MODE.SAFE_MODE) {
      fail("STORE_SAFE_MODE", "artifact store is in SAFE_MODE", {
        reason: this.#safeModeReason?.code ?? "unknown",
      });
    }
    if (this.#closed) fail("STORE_CLOSED", "artifact store is closed");
  }

  #assertReadable() {
    this.#assertAvailable();
    try {
      this.#assertPathIdentities();
    } catch (error) {
      if (error instanceof ArtifactStoreError) this.#enterSafeMode(error.code, error.details);
      throw error;
    }
  }

  #enterSafeMode(code, details) {
    this.#mode = ARTIFACT_STORE_MODE.SAFE_MODE;
    this.#safeModeReason = deepFreeze({ code, details: details ?? null });
    this.#closed = true;
  }

  #failSafe(code, message, details) {
    this.#enterSafeMode(code, details);
    fail(code, message, details);
  }

  #safe(code, details) {
    this.#enterSafeMode(code, details);
    return this;
  }
}

const CONSTRUCTOR_TOKEN = Symbol("ContentAddressedArtifactStore");

export const openContentAddressedArtifactStore = (rootPath) =>
  ContentAddressedArtifactStore.open(rootPath);
