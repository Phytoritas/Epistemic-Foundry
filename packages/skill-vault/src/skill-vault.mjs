import { createHash } from "node:crypto";
import { types as utilTypes } from "node:util";

/**
 * S03 Skill Vault authority boundary.
 *
 * Remote skill material enters only as inert bytes. This module inventories and
 * scans those bytes, binds an external review to their exact normalized tree
 * hash, emits the canonical SkillLockfile shape, and authorizes activation only
 * after a disabled-install and conformance attestation. It never fetches,
 * writes, imports, evaluates, or executes candidate content.
 */

export const SIGNATURE_STATUS = Object.freeze({
  VERIFIED: "VERIFIED",
  UNVERIFIED: "UNVERIFIED",
  NOT_PROVIDED: "NOT_PROVIDED",
  FAILED: "FAILED",
});

export const REVIEW_STATUS = Object.freeze({
  QUARANTINED: "QUARANTINED",
  APPROVED: "APPROVED",
  REJECTED: "REJECTED",
  DISABLED: "DISABLED",
});

export const REVIEW_DECISION = Object.freeze({
  APPROVED: "APPROVED",
  REJECTED: "REJECTED",
});

export const CONFORMANCE_STATUS = Object.freeze({
  PASS: "PASS",
  FAIL: "FAIL",
});

export const SKILL_PERMISSION = Object.freeze({
  FILESYSTEM_READ: "filesystem_read",
  FILESYSTEM_WRITE: "filesystem_write",
  NETWORK: "network",
  PROCESS_EXECUTE: "process_execute",
  SECRET_READ: "secret_read",
});

const SIGNATURE_STATUSES = new Set(Object.values(SIGNATURE_STATUS));
const REVIEW_STATUSES = new Set(Object.values(REVIEW_STATUS));
const REVIEW_DECISIONS = new Set(Object.values(REVIEW_DECISION));
const CONFORMANCE_STATUSES = new Set(Object.values(CONFORMANCE_STATUS));
const HASH_PATTERN = /^sha256:[0-9a-f]{64}$/u;
const PORTABLE_PATH_SEGMENT = /^[^\p{Cc}\\/:*?"<>|]+$/u;
const WINDOWS_RESERVED_BASENAME =
  /^(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$/iu;
const MAX_FILES = 2_048;
const MAX_FILE_BYTES = 1_048_576;
const MAX_TOTAL_BYTES = 16_777_216;
const MAX_ARRAY_ITEMS = 4_096;
const MAX_TEXT_SCAN_BYTES = 1_048_576;
const SCRIPT_LIKE_PATH = /\.(?:bat|cjs|cmd|exe|jar|js|mjs|ps1|py|sh|ts|tsx|wasm)$/iu;

const RISK_SEVERITY = Object.freeze({
  INFO: "INFO",
  MEDIUM: "MEDIUM",
  HIGH: "HIGH",
  CRITICAL: "CRITICAL",
});

const TEXT_RISK_RULES = Object.freeze([
  Object.freeze({
    code: "SELF_AUTHORITY_CLAIM",
    severity: RISK_SEVERITY.CRITICAL,
    expression:
      /(?:approve|authorize|grant)\s+(?:this|the)\s+skill|(?:ignore|bypass|override)\s+(?:the\s+)?(?:review|approval|policy|permission)/iu,
  }),
  Object.freeze({
    code: "DYNAMIC_EVALUATION",
    severity: RISK_SEVERITY.CRITICAL,
    permission: SKILL_PERMISSION.PROCESS_EXECUTE,
    expression: /\b(?:eval|Function)\s*\(|\bInvoke-Expression\b/gu,
  }),
  Object.freeze({
    code: "SHELL_OR_PROCESS_USE",
    severity: RISK_SEVERITY.HIGH,
    permission: SKILL_PERMISSION.PROCESS_EXECUTE,
    expression:
      /\b(?:child_process|execFile|execSync|spawnSync|subprocess\.|os\.system|Start-Process|cmd\.exe|powershell(?:\.exe)?|bash\s+-c)\b/giu,
  }),
  Object.freeze({
    code: "NETWORK_USE",
    severity: RISK_SEVERITY.HIGH,
    permission: SKILL_PERMISSION.NETWORK,
    expression:
      /\b(?:fetch\s*\(|axios\.|https?\.request|urllib\.|requests\.|Invoke-WebRequest|Invoke-RestMethod|curl\s+https?:|wget\s+https?:)/giu,
  }),
  Object.freeze({
    code: "SECRET_OR_ENVIRONMENT_READ",
    severity: RISK_SEVERITY.HIGH,
    permission: SKILL_PERMISSION.SECRET_READ,
    expression:
      /(?:\b(?:process\.env|os\.environ|getenv\s*\(|GetEnvironmentVariable|credential|api[_ -]?key|access[_ -]?token)\b|\$env:)/giu,
  }),
  Object.freeze({
    code: "FILESYSTEM_WRITE_USE",
    severity: RISK_SEVERITY.HIGH,
    permission: SKILL_PERMISSION.FILESYSTEM_WRITE,
    expression:
      /\b(?:writeFile|appendFile|unlink|rmSync|rmdir|mkdir|rename|shutil\.|Path\([^)]*\)\.write_|Set-Content|Add-Content|Remove-Item|Move-Item)\b/giu,
  }),
  Object.freeze({
    code: "FILESYSTEM_READ_USE",
    severity: RISK_SEVERITY.MEDIUM,
    permission: SKILL_PERMISSION.FILESYSTEM_READ,
    expression:
      /\b(?:readFile|readdir|read_text|read_bytes|Get-Content|open\s*\([^)]*[,)]|Path\([^)]*\)\.read_)\b/giu,
  }),
  Object.freeze({
    code: "ENCODED_PAYLOAD",
    severity: RISK_SEVERITY.HIGH,
    expression:
      /\b(?:atob\s*\(|fromCharCode\s*\(|base64\.(?:b64decode|decodebytes)|Convert\.FromBase64String)\b/giu,
  }),
]);

export class SkillVaultError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "SkillVaultError";
    this.code = code;
  }
}

const fail = (code, message) => {
  throw new SkillVaultError(code, message);
};

const requirePlainRecord = (value, label) => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail("INVALID_INPUT", `${label} must be a plain object`);
  }
  if (utilTypes.isProxy(value)) {
    fail("PROXY_INPUT_DENIED", `${label} must not be a Proxy`);
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    fail("INVALID_INPUT", `${label} must not have a custom prototype`);
  }
  return value;
};

const rejectUnknownFields = (record, allowed, label) => {
  for (const key of Reflect.ownKeys(record)) {
    if (typeof key !== "string" || !allowed.has(key)) {
      fail("UNEXPECTED_FIELD", `${label} contains an unexpected field: ${String(key)}`);
    }
  }
};

const readDataProperty = (record, key, { optional = false } = {}) => {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  if (descriptor === undefined) {
    if (optional) return undefined;
    fail("MISSING_FIELD", `missing required field: ${key}`);
  }
  if (!("value" in descriptor)) {
    fail("ACCESSOR_FIELD_DENIED", `${key} must be a data property`);
  }
  return descriptor.value;
};

const readPlainArray = (value, label, { maxItems = MAX_ARRAY_ITEMS } = {}) => {
  if (value === null || typeof value !== "object" || utilTypes.isProxy(value)) {
    fail("INVALID_INPUT", `${label} must be a plain array`);
  }
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) {
    fail("INVALID_INPUT", `${label} must be a plain array`);
  }
  const length = Object.getOwnPropertyDescriptor(value, "length")?.value;
  if (!Number.isSafeInteger(length) || length < 0 || length > maxItems) {
    fail("INPUT_LIMIT_EXCEEDED", `${label} has an invalid length`);
  }
  for (const key of Reflect.ownKeys(value)) {
    if (key === "length") continue;
    if (typeof key !== "string" || !/^(?:0|[1-9][0-9]*)$/u.test(key)) {
      fail("UNEXPECTED_FIELD", `${label} contains a non-index field`);
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index >= length || String(index) !== key) {
      fail("UNEXPECTED_FIELD", `${label} contains an invalid index`);
    }
  }
  const values = [];
  for (let index = 0; index < length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (descriptor === undefined) {
      fail("SPARSE_ARRAY_DENIED", `${label} must not be sparse`);
    }
    if (!("value" in descriptor)) {
      fail("ACCESSOR_FIELD_DENIED", `${label} elements must be data properties`);
    }
    values.push(descriptor.value);
  }
  return values;
};

const requireString = (
  value,
  label,
  { minLength = 1, maxLength = 512, normalize = true } = {},
) => {
  if (typeof value !== "string") {
    fail("INVALID_STRING", `${label} must be a string`);
  }
  const output = normalize ? value.normalize("NFC") : value;
  if (
    output.length < minLength ||
    output.length > maxLength ||
    /\p{Cc}/u.test(output)
  ) {
    fail("INVALID_STRING", `${label} is outside the accepted string contract`);
  }
  return output;
};

const requireIdentifier = (value, label) =>
  requireString(value, label, { minLength: 3, maxLength: 128 });

const requireHash = (value, label) => {
  if (typeof value !== "string" || !HASH_PATTERN.test(value)) {
    fail("INVALID_HASH", `${label} must be a lowercase sha256 digest`);
  }
  return value;
};

const requireCanonicalTimestamp = (value, label) => {
  const text = requireString(value, label, { maxLength: 64, normalize: false });
  const milliseconds = Date.parse(text);
  if (!Number.isFinite(milliseconds)) {
    fail("INVALID_TIMESTAMP", `${label} must be an RFC 3339 timestamp`);
  }
  const canonical = new Date(milliseconds).toISOString();
  if (canonical !== text) {
    fail("NON_CANONICAL_TIMESTAMP", `${label} must be canonical UTC ISO-8601`);
  }
  return canonical;
};

const requireEnum = (value, values, label) => {
  if (!values.has(value)) fail("INVALID_ENUM", `${label} is not supported`);
  return value;
};

const requireBoolean = (value, label) => {
  if (typeof value !== "boolean") fail("INVALID_BOOLEAN", `${label} must be boolean`);
  return value;
};

const compareUtf8 = (left, right) =>
  Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));

const sortedUniqueStrings = (
  value,
  label,
  { identifiers = false, maxItems = MAX_ARRAY_ITEMS } = {},
) => {
  const values = readPlainArray(value, label, { maxItems }).map((item, index) =>
    identifiers
      ? requireIdentifier(item, `${label}[${index}]`)
      : requireString(item, `${label}[${index}]`, { maxLength: 256 }),
  );
  const unique = new Set(values);
  if (unique.size !== values.length) {
    fail("DUPLICATE_VALUE", `${label} must contain unique values`);
  }
  return Object.freeze([...unique].sort(compareUtf8));
};

const canonicalOrderedUniqueStrings = (
  value,
  label,
  { identifiers = false, maxItems = MAX_ARRAY_ITEMS } = {},
) => {
  const values = readPlainArray(value, label, { maxItems }).map((item, index) =>
    identifiers
      ? requireIdentifier(item, `${label}[${index}]`)
      : requireString(item, `${label}[${index}]`, { maxLength: 256 }),
  );
  if (new Set(values).size !== values.length) {
    fail("DUPLICATE_VALUE", `${label} must contain unique values`);
  }
  assertSorted(values, label);
  return Object.freeze(values);
};

const assertSorted = (values, label) => {
  const sorted = [...values].sort(compareUtf8);
  if (values.some((value, index) => value !== sorted[index])) {
    fail("NON_CANONICAL_ORDER", `${label} must be sorted`);
  }
};

const parsePortablePath = (value, label) => {
  const text = requireString(value, label, { maxLength: 512 });
  if (text.startsWith("/") || text.includes("\\") || /^[A-Za-z]:/u.test(text)) {
    fail("PATH_ESCAPE_DENIED", `${label} must be a portable relative path`);
  }
  const segments = text.split("/");
  for (const segment of segments) {
    const baseName = segment.split(".", 1)[0].replace(/[ .]+$/u, "");
    if (
      segment.length === 0 ||
      segment === "." ||
      segment === ".." ||
      segment.endsWith(".") ||
      segment.endsWith(" ") ||
      !PORTABLE_PATH_SEGMENT.test(segment) ||
      WINDOWS_RESERVED_BASENAME.test(baseName)
    ) {
      fail("PATH_ESCAPE_DENIED", `${label} contains an unsafe component`);
    }
  }
  return segments.join("/");
};

const copyBytes = (value, label) => {
  let bytes;
  if (typeof value === "string") {
    bytes = Buffer.from(value, "utf8");
  } else {
    if (value === null || typeof value !== "object" || utilTypes.isProxy(value)) {
      fail("INVALID_BYTES", `${label} must be a string, Buffer, or Uint8Array`);
    }
    if (!Buffer.isBuffer(value) && Object.getPrototypeOf(value) !== Uint8Array.prototype) {
      fail("INVALID_BYTES", `${label} must be a string, Buffer, or Uint8Array`);
    }
    if (typeof SharedArrayBuffer !== "undefined" && value.buffer instanceof SharedArrayBuffer) {
      fail("SHARED_MEMORY_DENIED", `${label} must not use shared memory`);
    }
    bytes = Buffer.from(value);
  }
  if (bytes.byteLength > MAX_FILE_BYTES) {
    fail("INPUT_LIMIT_EXCEEDED", `${label} exceeds the per-file byte limit`);
  }
  return bytes;
};

const addLengthPrefixed = (hash, value) => {
  const bytes = Buffer.isBuffer(value) ? value : Buffer.from(value, "utf8");
  hash.update(String(bytes.byteLength));
  hash.update(":");
  hash.update(bytes);
  hash.update(";");
};

const digest = (domain, callback) => {
  const hash = createHash("sha256");
  hash.update(domain);
  hash.update("\0");
  callback(hash);
  return `sha256:${hash.digest("hex")}`;
};

const canonicalJson = (value) => {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) fail("NON_CANONICAL_NUMBER", "canonical JSON accepts safe integers only");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value === "object") {
    return `{${Object.keys(value)
      .sort(compareUtf8)
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  fail("NON_CANONICAL_VALUE", "canonical JSON contains an unsupported value");
};

const freezeFinding = (finding) => Object.freeze(finding);

const freezeEntry = (entry) =>
  Object.freeze({
    skill_id: entry.skill_id,
    source: entry.source,
    revision: entry.revision,
    content_hash: entry.content_hash,
    signature_status: entry.signature_status,
    license: entry.license,
    permissions: Object.freeze([...entry.permissions]),
    review_status: entry.review_status,
    approved_by_ids: Object.freeze([...entry.approved_by_ids]),
  });

const lockPayload = (lockfile) => ({
  lock_version: lockfile.lock_version,
  workspace_id: lockfile.workspace_id,
  skills: lockfile.skills.map((entry) => ({
    skill_id: entry.skill_id,
    source: entry.source,
    revision: entry.revision,
    content_hash: entry.content_hash,
    signature_status: entry.signature_status,
    license: entry.license,
    permissions: [...entry.permissions],
    review_status: entry.review_status,
    approved_by_ids: [...entry.approved_by_ids],
  })),
  generated_at: lockfile.generated_at,
  policy_hash: lockfile.policy_hash,
});

const computeLockHash = (payload) =>
  digest("epistemic-foundry.skill-lockfile.v1", (hash) => {
    hash.update(canonicalJson(payload), "utf8");
  });

const validateLockfileSnapshot = (input) => {
  const lockfile = requirePlainRecord(input, "skillLockfile");
  rejectUnknownFields(
    lockfile,
    new Set([
      "lock_version",
      "workspace_id",
      "skills",
      "generated_at",
      "policy_hash",
      "lock_hash",
    ]),
    "skillLockfile",
  );

  const lockVersion = readDataProperty(lockfile, "lock_version");
  if (lockVersion !== 1) fail("UNSUPPORTED_LOCK_VERSION", "only SkillLockfile v1 is supported");
  const workspaceId = requireIdentifier(readDataProperty(lockfile, "workspace_id"), "workspace_id");
  const generatedAt = requireCanonicalTimestamp(readDataProperty(lockfile, "generated_at"), "generated_at");
  const policyHash = requireHash(readDataProperty(lockfile, "policy_hash"), "policy_hash");
  const claimedLockHash = requireHash(readDataProperty(lockfile, "lock_hash"), "lock_hash");
  const skillValues = readPlainArray(readDataProperty(lockfile, "skills"), "skills");
  const entries = [];
  const skillIds = new Set();

  for (let index = 0; index < skillValues.length; index += 1) {
    const item = requirePlainRecord(skillValues[index], `skills[${index}]`);
    rejectUnknownFields(
      item,
      new Set([
        "skill_id",
        "source",
        "revision",
        "content_hash",
        "signature_status",
        "license",
        "permissions",
        "review_status",
        "approved_by_ids",
      ]),
      `skills[${index}]`,
    );
    const skillId = requireIdentifier(readDataProperty(item, "skill_id"), `skills[${index}].skill_id`);
    if (skillIds.has(skillId)) fail("DUPLICATE_SKILL", `duplicate lock entry: ${skillId}`);
    skillIds.add(skillId);
    const permissions = canonicalOrderedUniqueStrings(
      readDataProperty(item, "permissions"),
      `skills[${index}].permissions`,
    );
    const approvedByIds = canonicalOrderedUniqueStrings(
      readDataProperty(item, "approved_by_ids"),
      `skills[${index}].approved_by_ids`,
      { identifiers: true },
    );
    const reviewStatus = requireEnum(
      readDataProperty(item, "review_status"),
      REVIEW_STATUSES,
      `skills[${index}].review_status`,
    );
    if (reviewStatus === REVIEW_STATUS.APPROVED && approvedByIds.length === 0) {
      fail("APPROVAL_IDENTITY_MISSING", `${skillId} is approved without an approval identity`);
    }
    if (reviewStatus !== REVIEW_STATUS.APPROVED && approvedByIds.length !== 0) {
      fail("INVALID_APPROVAL_IDENTITY", `${skillId} is not approved but carries approver IDs`);
    }
    entries.push(
      freezeEntry({
        skill_id: skillId,
        source: requireString(readDataProperty(item, "source"), `skills[${index}].source`, { maxLength: 2_048 }),
        revision: requireString(readDataProperty(item, "revision"), `skills[${index}].revision`, { maxLength: 512 }),
        content_hash: requireHash(readDataProperty(item, "content_hash"), `skills[${index}].content_hash`),
        signature_status: requireEnum(
          readDataProperty(item, "signature_status"),
          SIGNATURE_STATUSES,
          `skills[${index}].signature_status`,
        ),
        license: requireString(readDataProperty(item, "license"), `skills[${index}].license`, { maxLength: 256 }),
        permissions,
        review_status: reviewStatus,
        approved_by_ids: approvedByIds,
      }),
    );
  }
  assertSorted(entries.map(({ skill_id: skillId }) => skillId), "skills");

  const payload = {
    lock_version: lockVersion,
    workspace_id: workspaceId,
    skills: entries,
    generated_at: generatedAt,
    policy_hash: policyHash,
  };
  const actualLockHash = computeLockHash(lockPayload(payload));
  if (actualLockHash !== claimedLockHash) {
    fail("LOCK_HASH_MISMATCH", "SkillLockfile content does not match lock_hash");
  }
  return Object.freeze({
    valid: true,
    schemaRef: "schemas/skill-lockfile.schema.json",
    lockHash: claimedLockHash,
    workspaceId,
    skillCount: entries.length,
    authorityEligible: false,
  });
};

const getBranded = (registry, value, code, message) => {
  if (value === null || typeof value !== "object") fail(code, message);
  const record = registry.get(value);
  if (record === undefined) fail(code, message);
  return record;
};

const isSubset = (subset, superset) => subset.every((value) => superset.includes(value));

export const createSkillVaultBoundary = () => {
  const candidates = new WeakMap();
  const scans = new WeakMap();
  const reviews = new WeakMap();
  const lockfiles = new WeakMap();
  const installations = new WeakMap();
  const conformanceReports = new WeakMap();
  const activationAuthorizations = new WeakSet();

  const quarantineCandidate = (input) => {
    const record = requirePlainRecord(input, "candidate");
    rejectUnknownFields(
      record,
      new Set([
        "skillId",
        "source",
        "revision",
        "signatureStatus",
        "declaredLicense",
        "declaredPermissions",
        "files",
      ]),
      "candidate",
    );
    const skillId = requireIdentifier(readDataProperty(record, "skillId"), "skillId");
    const source = requireString(readDataProperty(record, "source"), "source", { maxLength: 2_048 });
    const revision = requireString(readDataProperty(record, "revision"), "revision", { maxLength: 512 });
    const claimedSignatureStatus = requireEnum(
      readDataProperty(record, "signatureStatus"),
      SIGNATURE_STATUSES,
      "signatureStatus",
    );
    const declaredLicense = requireString(
      readDataProperty(record, "declaredLicense"),
      "declaredLicense",
      { maxLength: 256 },
    );
    const declaredPermissions = sortedUniqueStrings(
      readDataProperty(record, "declaredPermissions"),
      "declaredPermissions",
    );
    const fileValues = readPlainArray(readDataProperty(record, "files"), "files", {
      maxItems: MAX_FILES,
    });
    if (fileValues.length === 0) fail("EMPTY_SKILL", "a skill must contain at least one entry");

    const files = [];
    const pathKeys = new Set();
    let totalBytes = 0;
    for (let index = 0; index < fileValues.length; index += 1) {
      const file = requirePlainRecord(fileValues[index], `files[${index}]`);
      rejectUnknownFields(
        file,
        new Set(["path", "kind", "content", "target", "executable"]),
        `files[${index}]`,
      );
      const portablePath = parsePortablePath(
        readDataProperty(file, "path"),
        `files[${index}].path`,
      );
      const collisionKey = portablePath.normalize("NFKC").toLocaleLowerCase("en-US");
      if (pathKeys.has(collisionKey)) {
        fail("PATH_COLLISION", `skill entries collide on a portable filesystem: ${portablePath}`);
      }
      pathKeys.add(collisionKey);
      const kind = requireEnum(
        readDataProperty(file, "kind"),
        new Set(["file", "symlink"]),
        `files[${index}].kind`,
      );
      const executableValue = readDataProperty(file, "executable", { optional: true });
      const executable = executableValue === undefined
        ? false
        : requireBoolean(executableValue, `files[${index}].executable`);
      if (kind === "file") {
        if (Object.hasOwn(file, "target")) {
          fail("UNEXPECTED_FIELD", `files[${index}].target is valid only for symlinks`);
        }
        const bytes = copyBytes(readDataProperty(file, "content"), `files[${index}].content`);
        totalBytes += bytes.byteLength;
        if (totalBytes > MAX_TOTAL_BYTES) {
          fail("INPUT_LIMIT_EXCEEDED", "candidate exceeds the total byte limit");
        }
        files.push(Object.freeze({ path: portablePath, kind, executable, bytes }));
      } else {
        if (Object.hasOwn(file, "content") || executable) {
          fail("INVALID_SYMLINK", "symlink entries cannot contain bytes or be executable");
        }
        const target = requireString(
          readDataProperty(file, "target"),
          `files[${index}].target`,
          { maxLength: 512 },
        );
        files.push(Object.freeze({ path: portablePath, kind, executable: false, target }));
      }
    }
    for (const collisionKey of pathKeys) {
      for (
        let slashIndex = collisionKey.indexOf("/");
        slashIndex !== -1;
        slashIndex = collisionKey.indexOf("/", slashIndex + 1)
      ) {
        if (pathKeys.has(collisionKey.slice(0, slashIndex))) {
          fail("PATH_COLLISION", `skill entries collide on a portable filesystem: ${collisionKey}`);
        }
      }
    }
    files.sort((left, right) => compareUtf8(left.path, right.path));

    const contentHash = digest("epistemic-foundry.skill-tree.v1", (hash) => {
      for (const file of files) {
        addLengthPrefixed(hash, file.path);
        addLengthPrefixed(hash, file.kind);
        addLengthPrefixed(hash, file.executable ? "1" : "0");
        addLengthPrefixed(hash, file.kind === "file" ? file.bytes : file.target);
      }
    });
    const candidate = Object.freeze({
      schemaVersion: 1,
      kind: "quarantined_skill_candidate",
      skillId,
      source,
      revision,
      contentHash,
      claimedSignatureStatus,
      declaredLicense,
      declaredPermissions,
      fileCount: files.length,
      totalBytes,
      state: REVIEW_STATUS.QUARANTINED,
      executable: false,
      active: false,
      authorityEligible: false,
    });
    candidates.set(candidate, Object.freeze({
      skillId,
      source,
      revision,
      contentHash,
      claimedSignatureStatus,
      declaredLicense,
      declaredPermissions,
      files: Object.freeze(files),
    }));
    return candidate;
  };

  const scanCandidate = (candidate) => {
    const candidateRecord = getBranded(
      candidates,
      candidate,
      "UNRECOGNIZED_CANDIDATE",
      "candidate must be quarantined by this Skill Vault boundary",
    );
    const cached = scans.get(candidate);
    if (cached !== undefined) return cached.publicReport;

    const findings = [];
    const findingKeys = new Set();
    const inferredPermissions = new Set();
    const executableInventory = [];
    const addFinding = ({ code, severity, path, detail, permission }) => {
      const key = `${code}\0${path}`;
      if (findingKeys.has(key)) return;
      findingKeys.add(key);
      if (permission !== undefined) inferredPermissions.add(permission);
      findings.push(freezeFinding({ code, severity, path, detail }));
    };

    if (candidateRecord.claimedSignatureStatus === SIGNATURE_STATUS.FAILED) {
      addFinding({
        code: "SIGNATURE_VERIFICATION_FAILED",
        severity: RISK_SEVERITY.CRITICAL,
        path: "<candidate>",
        detail: "provided signature failed verification",
      });
    }

    for (const file of candidateRecord.files) {
      if (file.kind === "symlink") {
        addFinding({
          code: "SYMLINK_CONTENT",
          severity: RISK_SEVERITY.CRITICAL,
          path: file.path,
          detail: "remote skill contains a symlink and remains non-activatable",
        });
        continue;
      }
      const scriptLike = SCRIPT_LIKE_PATH.test(file.path) || file.bytes.subarray(0, 2).toString("ascii") === "#!";
      if (file.executable || scriptLike) {
        executableInventory.push(file.path);
        addFinding({
          code: file.executable ? "EXECUTABLE_CONTENT" : "SCRIPT_CONTENT",
          severity: RISK_SEVERITY.HIGH,
          path: file.path,
          detail: file.executable
            ? "entry is marked executable"
            : "entry has a script or executable artifact form",
          permission: SKILL_PERMISSION.PROCESS_EXECUTE,
        });
      }
      if (file.bytes.includes(0)) {
        addFinding({
          code: "BINARY_CONTENT",
          severity: RISK_SEVERITY.HIGH,
          path: file.path,
          detail: "binary content requires separate provenance and sandbox review",
        });
        continue;
      }
      const text = file.bytes.subarray(0, MAX_TEXT_SCAN_BYTES).toString("utf8");
      if (file.path.toLocaleLowerCase("en-US") === "package.json" &&
          /"(?:preinstall|install|postinstall|prepare)"\s*:/u.test(text)) {
        addFinding({
          code: "PACKAGE_INSTALL_HOOK",
          severity: RISK_SEVERITY.CRITICAL,
          path: file.path,
          detail: "package lifecycle hook is executable during installation",
          permission: SKILL_PERMISSION.PROCESS_EXECUTE,
        });
      }
      for (const rule of TEXT_RISK_RULES) {
        rule.expression.lastIndex = 0;
        if (rule.expression.test(text)) {
          addFinding({
            code: rule.code,
            severity: rule.severity,
            path: file.path,
            detail: "static risk signal requires explicit review",
            permission: rule.permission,
          });
        }
      }
    }
    findings.sort((left, right) =>
      compareUtf8(
        `${left.severity}\0${left.code}\0${left.path}`,
        `${right.severity}\0${right.code}\0${right.path}`,
      ),
    );
    const permissionList = Object.freeze([...inferredPermissions].sort(compareUtf8));
    const criticalFindingIds = Object.freeze(
      findings
        .filter(({ severity }) => severity === RISK_SEVERITY.CRITICAL)
        .map(({ code, path }) => `${code}:${path}`),
    );
    const inventoryHash = digest("epistemic-foundry.skill-inventory.v1", (hash) => {
      for (const file of candidateRecord.files) {
        addLengthPrefixed(hash, file.path);
        addLengthPrefixed(hash, file.kind);
        addLengthPrefixed(hash, file.executable ? "1" : "0");
        addLengthPrefixed(
          hash,
          file.kind === "file"
            ? digest("epistemic-foundry.skill-file.v1", (fileHash) => fileHash.update(file.bytes))
            : file.target,
        );
      }
    });
    const publicReport = Object.freeze({
      schemaVersion: 1,
      kind: "skill_quarantine_scan",
      skillId: candidateRecord.skillId,
      candidateContentHash: candidateRecord.contentHash,
      inventoryHash,
      status: criticalFindingIds.length > 0
        ? "CRITICAL"
        : findings.length > 0
          ? "FINDINGS"
          : "CLEAN",
      findings: Object.freeze(findings),
      inferredPermissions: permissionList,
      criticalFindingIds,
      executableInventory: Object.freeze(executableInventory.sort(compareUtf8)),
      noScriptsExecuted: true,
      active: false,
      authorityEligible: false,
    });
    const privateRecord = Object.freeze({ candidate, candidateRecord, publicReport });
    scans.set(publicReport, privateRecord);
    scans.set(candidate, Object.freeze({ publicReport }));
    return publicReport;
  };

  const issueReviewDecision = (input) => {
    const record = requirePlainRecord(input, "reviewDecision");
    rejectUnknownFields(
      record,
      new Set([
        "decisionId",
        "candidate",
        "scanReport",
        "reviewerIds",
        "decision",
        "reviewedSource",
        "reviewedRevision",
        "reviewedContentHash",
        "signatureStatus",
        "license",
        "permissions",
        "rationale",
      ]),
      "reviewDecision",
    );
    const candidate = readDataProperty(record, "candidate");
    const candidateRecord = getBranded(
      candidates,
      candidate,
      "UNRECOGNIZED_CANDIDATE",
      "review candidate must belong to this boundary",
    );
    const scanReport = readDataProperty(record, "scanReport");
    const scanRecord = getBranded(
      scans,
      scanReport,
      "UNRECOGNIZED_SCAN",
      "review requires this boundary's scan report",
    );
    if (scanRecord.candidate !== candidate) {
      fail("SCAN_CANDIDATE_MISMATCH", "scan report belongs to a different candidate");
    }
    const decisionId = requireIdentifier(readDataProperty(record, "decisionId"), "decisionId");
    const reviewerIds = sortedUniqueStrings(
      readDataProperty(record, "reviewerIds"),
      "reviewerIds",
      { identifiers: true },
    );
    if (reviewerIds.length === 0) fail("REVIEWER_REQUIRED", "review requires an external reviewer identity");
    const decision = requireEnum(
      readDataProperty(record, "decision"),
      REVIEW_DECISIONS,
      "decision",
    );
    const reviewedSource = requireString(readDataProperty(record, "reviewedSource"), "reviewedSource", { maxLength: 2_048 });
    const reviewedRevision = requireString(readDataProperty(record, "reviewedRevision"), "reviewedRevision", { maxLength: 512 });
    const reviewedContentHash = requireHash(readDataProperty(record, "reviewedContentHash"), "reviewedContentHash");
    if (
      reviewedSource !== candidateRecord.source ||
      reviewedRevision !== candidateRecord.revision ||
      reviewedContentHash !== candidateRecord.contentHash
    ) {
      fail("REVIEW_SUBJECT_MISMATCH", "review does not bind the exact source, revision, and content hash");
    }
    const signatureStatus = requireEnum(
      readDataProperty(record, "signatureStatus"),
      SIGNATURE_STATUSES,
      "signatureStatus",
    );
    const license = requireString(readDataProperty(record, "license"), "license", { maxLength: 256 });
    const permissions = sortedUniqueStrings(readDataProperty(record, "permissions"), "permissions");
    const rationale = requireString(readDataProperty(record, "rationale"), "rationale", { maxLength: 2_048 });
    if (decision === REVIEW_DECISION.APPROVED) {
      if (scanReport.criticalFindingIds.length > 0) {
        fail("CRITICAL_FINDING_BLOCKS_APPROVAL", "critical quarantine findings prohibit approval");
      }
      if (signatureStatus === SIGNATURE_STATUS.FAILED) {
        fail("SIGNATURE_FAILURE_BLOCKS_APPROVAL", "a failed signature status prohibits approval");
      }
      if (!isSubset(scanReport.inferredPermissions, permissions)) {
        fail("INFERRED_PERMISSION_MISSING", "approval omits a permission inferred by the scan");
      }
    }
    const publicDecision = Object.freeze({
      schemaVersion: 1,
      kind: "skill_review_decision",
      decisionId,
      skillId: candidateRecord.skillId,
      source: reviewedSource,
      revision: reviewedRevision,
      contentHash: reviewedContentHash,
      signatureStatus,
      license,
      permissions,
      decision,
      reviewerIds,
      rationale,
      scanInventoryHash: scanReport.inventoryHash,
      active: false,
      authorityEligible: false,
    });
    reviews.set(publicDecision, Object.freeze({
      candidate,
      candidateRecord,
      scanReport,
      decision: publicDecision,
    }));
    return publicDecision;
  };

  const createSkillLockfile = (input) => {
    const record = requirePlainRecord(input, "lockfileRequest");
    rejectUnknownFields(
      record,
      new Set(["workspaceId", "generatedAt", "policyHash", "reviewDecisions"]),
      "lockfileRequest",
    );
    const workspaceId = requireIdentifier(readDataProperty(record, "workspaceId"), "workspaceId");
    const generatedAt = requireCanonicalTimestamp(readDataProperty(record, "generatedAt"), "generatedAt");
    const policyHash = requireHash(readDataProperty(record, "policyHash"), "policyHash");
    const decisionValues = readPlainArray(
      readDataProperty(record, "reviewDecisions"),
      "reviewDecisions",
    );
    const entries = [];
    const decisionRecords = new Map();
    for (const value of decisionValues) {
      const reviewRecord = getBranded(
        reviews,
        value,
        "UNRECOGNIZED_REVIEW",
        "lockfile entries require review decisions issued by this boundary",
      );
      const decision = reviewRecord.decision;
      if (decisionRecords.has(decision.skillId)) {
        fail("DUPLICATE_SKILL", `multiple decisions target ${decision.skillId}`);
      }
      decisionRecords.set(decision.skillId, reviewRecord);
      entries.push(
        freezeEntry({
          skill_id: decision.skillId,
          source: decision.source,
          revision: decision.revision,
          content_hash: decision.contentHash,
          signature_status: decision.signatureStatus,
          license: decision.license,
          permissions: decision.permissions,
          review_status: decision.decision,
          approved_by_ids: decision.decision === REVIEW_DECISION.APPROVED
            ? decision.reviewerIds
            : Object.freeze([]),
        }),
      );
    }
    entries.sort((left, right) => compareUtf8(left.skill_id, right.skill_id));
    const payload = {
      lock_version: 1,
      workspace_id: workspaceId,
      skills: Object.freeze(entries),
      generated_at: generatedAt,
      policy_hash: policyHash,
    };
    const lockHash = computeLockHash(lockPayload(payload));
    const lockfile = Object.freeze({ ...payload, lock_hash: lockHash });
    validateLockfileSnapshot(lockfile);
    lockfiles.set(lockfile, Object.freeze({
      lockHash,
      workspaceId,
      policyHash,
      entries: new Map(entries.map((entry) => [entry.skill_id, entry])),
      decisionRecords,
    }));
    return lockfile;
  };

  const issueDisabledInstallation = (input) => {
    const record = requirePlainRecord(input, "disabledInstallation");
    rejectUnknownFields(
      record,
      new Set([
        "installId",
        "lockfile",
        "skillId",
        "observedContentHash",
        "collisionSkillIds",
      ]),
      "disabledInstallation",
    );
    const lockfile = readDataProperty(record, "lockfile");
    const lockRecord = getBranded(
      lockfiles,
      lockfile,
      "UNRECOGNIZED_LOCKFILE",
      "installation requires a lockfile created by this boundary",
    );
    const skillId = requireIdentifier(readDataProperty(record, "skillId"), "skillId");
    const entry = lockRecord.entries.get(skillId);
    if (entry === undefined) fail("SKILL_NOT_LOCKED", `${skillId} is absent from the lockfile`);
    if (entry.review_status !== REVIEW_STATUS.APPROVED) {
      fail("SKILL_NOT_APPROVED", `${skillId} is not approved in the lockfile`);
    }
    const observedContentHash = requireHash(
      readDataProperty(record, "observedContentHash"),
      "observedContentHash",
    );
    if (observedContentHash !== entry.content_hash) {
      fail("INSTALL_HASH_MISMATCH", "installed content does not match the approved lock entry");
    }
    const collisionSkillIds = sortedUniqueStrings(
      readDataProperty(record, "collisionSkillIds"),
      "collisionSkillIds",
      { identifiers: true },
    );
    const installation = Object.freeze({
      schemaVersion: 1,
      kind: "disabled_skill_installation",
      installId: requireIdentifier(readDataProperty(record, "installId"), "installId"),
      skillId,
      contentHash: observedContentHash,
      lockHash: lockRecord.lockHash,
      permissions: entry.permissions,
      state: collisionSkillIds.length > 0 ? "BLOCKED_NAME_COLLISION" : "DISABLED",
      collisionSkillIds,
      disabled: true,
      active: false,
      authorityEligible: false,
    });
    installations.set(installation, Object.freeze({ lockfile, lockRecord, entry, installation }));
    return installation;
  };

  const issueConformanceAttestation = (input) => {
    const record = requirePlainRecord(input, "conformanceAttestation");
    rejectUnknownFields(
      record,
      new Set([
        "conformanceId",
        "installation",
        "status",
        "observedPermissions",
        "uninstallVerified",
        "explicitInvocationOnly",
        "sandboxProfileId",
      ]),
      "conformanceAttestation",
    );
    const installation = readDataProperty(record, "installation");
    const installRecord = getBranded(
      installations,
      installation,
      "UNRECOGNIZED_INSTALLATION",
      "conformance requires this boundary's disabled installation record",
    );
    const status = requireEnum(
      readDataProperty(record, "status"),
      CONFORMANCE_STATUSES,
      "status",
    );
    const observedPermissions = sortedUniqueStrings(
      readDataProperty(record, "observedPermissions"),
      "observedPermissions",
    );
    const uninstallVerified = requireBoolean(
      readDataProperty(record, "uninstallVerified"),
      "uninstallVerified",
    );
    const explicitInvocationOnly = requireBoolean(
      readDataProperty(record, "explicitInvocationOnly"),
      "explicitInvocationOnly",
    );
    if (status === CONFORMANCE_STATUS.PASS) {
      if (installation.state !== "DISABLED") {
        fail("INSTALLATION_NOT_CONFORMABLE", "name collisions or non-disabled state block conformance");
      }
      if (!isSubset(observedPermissions, installRecord.entry.permissions)) {
        fail("UNDECLARED_PERMISSION", "conformance observed a capability absent from the lockfile");
      }
      if (!uninstallVerified || !explicitInvocationOnly) {
        fail(
          "CONFORMANCE_REQUIREMENT_FAILED",
          "passing conformance requires clean uninstall and explicit-only invocation",
        );
      }
    }
    const report = Object.freeze({
      schemaVersion: 1,
      kind: "skill_activation_conformance",
      conformanceId: requireIdentifier(
        readDataProperty(record, "conformanceId"),
        "conformanceId",
      ),
      installId: installation.installId,
      skillId: installation.skillId,
      contentHash: installation.contentHash,
      lockHash: installation.lockHash,
      status,
      observedPermissions,
      uninstallVerified,
      explicitInvocationOnly,
      sandboxProfileId: requireIdentifier(
        readDataProperty(record, "sandboxProfileId"),
        "sandboxProfileId",
      ),
      active: false,
      authorityEligible: false,
    });
    conformanceReports.set(report, Object.freeze({ installation, installRecord, report }));
    return report;
  };

  const authorizeActivation = (input) => {
    const record = requirePlainRecord(input, "activationRequest");
    rejectUnknownFields(
      record,
      new Set([
        "requestId",
        "skillId",
        "lockfile",
        "installation",
        "conformanceReport",
        "expectedPolicyHash",
        "requestedPermissions",
        "activationScopeId",
      ]),
      "activationRequest",
    );
    const lockfile = readDataProperty(record, "lockfile");
    const lockRecord = getBranded(
      lockfiles,
      lockfile,
      "UNRECOGNIZED_LOCKFILE",
      "activation requires this boundary's lockfile authority",
    );
    const installation = readDataProperty(record, "installation");
    const installRecord = getBranded(
      installations,
      installation,
      "UNRECOGNIZED_INSTALLATION",
      "activation requires this boundary's disabled installation record",
    );
    const conformanceReport = readDataProperty(record, "conformanceReport");
    const conformanceRecord = getBranded(
      conformanceReports,
      conformanceReport,
      "UNRECOGNIZED_CONFORMANCE",
      "activation requires this boundary's conformance attestation",
    );
    const skillId = requireIdentifier(readDataProperty(record, "skillId"), "skillId");
    if (
      installRecord.lockfile !== lockfile ||
      conformanceRecord.installation !== installation ||
      installation.skillId !== skillId ||
      conformanceReport.skillId !== skillId
    ) {
      fail("ACTIVATION_SUBJECT_MISMATCH", "activation artifacts do not bind the same skill and lockfile");
    }
    if (installation.state !== "DISABLED" || !installation.disabled || installation.active) {
      fail("INSTALLATION_NOT_DISABLED", "activation begins only from a verified disabled installation");
    }
    if (conformanceReport.status !== CONFORMANCE_STATUS.PASS) {
      fail("CONFORMANCE_NOT_PASSED", "activation requires a passing conformance attestation");
    }
    const expectedPolicyHash = requireHash(
      readDataProperty(record, "expectedPolicyHash"),
      "expectedPolicyHash",
    );
    if (expectedPolicyHash !== lockRecord.policyHash) {
      fail("POLICY_HASH_MISMATCH", "lockfile was generated under a different policy hash");
    }
    const requestedPermissions = sortedUniqueStrings(
      readDataProperty(record, "requestedPermissions"),
      "requestedPermissions",
    );
    if (!isSubset(requestedPermissions, installRecord.entry.permissions)) {
      fail("PERMISSION_EXPANSION_DENIED", "activation cannot expand locked permissions");
    }
    if (!isSubset(requestedPermissions, conformanceReport.observedPermissions)) {
      fail(
        "UNVERIFIED_PERMISSION_DENIED",
        "activation cannot use a locked permission absent from conformance observations",
      );
    }
    const authorization = Object.freeze({
      decision: "ALLOW",
      purpose: "explicit_skill_activation",
      requestId: requireIdentifier(readDataProperty(record, "requestId"), "requestId"),
      skillId,
      workspaceId: lockRecord.workspaceId,
      lockHash: lockRecord.lockHash,
      contentHash: installation.contentHash,
      policyHash: lockRecord.policyHash,
      permissions: requestedPermissions,
      activationScopeId: requireIdentifier(
        readDataProperty(record, "activationScopeId"),
        "activationScopeId",
      ),
      explicitApprovalLinked: installRecord.entry.approved_by_ids.length > 0,
      conformanceId: conformanceReport.conformanceId,
      rollbackAvailable: conformanceReport.uninstallVerified,
      effectPerformed: false,
    });
    activationAuthorizations.add(authorization);
    return authorization;
  };

  const issuer = Object.freeze({
    issueReviewDecision,
    createSkillLockfile,
    issueDisabledInstallation,
    issueConformanceAttestation,
  });
  const guard = Object.freeze({
    quarantineCandidate,
    scanCandidate,
    verifySkillLockfileSnapshot: validateLockfileSnapshot,
    authorizeActivation,
    isQuarantinedCandidate: (value) =>
      value !== null && typeof value === "object" && candidates.has(value),
    isSkillLockfile: (value) =>
      value !== null && typeof value === "object" && lockfiles.has(value),
    isActivationAuthorization: (value) =>
      value !== null && typeof value === "object" && activationAuthorizations.has(value),
  });
  return Object.freeze({ issuer, guard });
};
