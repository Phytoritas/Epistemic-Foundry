// H05 — evolution and holdout observability hooks with explicit coverage limits.
//
// This module declares no vocabulary of its own.  Hosts, event types, decisions
// and coverage dispositions come from the sealed hook gateway; the set of
// evolution-relevant event types comes from the plugin's own evolution and
// holdout hook bundles; the holdout material an observer may never read comes
// from the sealed holdout-manifest schema; and the runner command convention
// comes from the bundle that already uses it.  What H05 adds is the binding
// between them and the refusals that keep the binding honest.
//
// Three honesty rules drive every refusal here.
//
//   1. A registration cannot claim a host, an event type, a decision or a
//      coverage disposition that its declaring source does not declare.
//   2. Observation is not enforcement and not access.  A registration that
//      emits a control-bearing decision, or that requests payload access to
//      holdout-flagged material, is refused rather than downgraded.
//   3. Coverage is reported, never assumed.  Every host/event pair that no
//      registration observes is named in an explicit `not_observed` list, and a
//      claim of more coverage than the registrations support is refused.
//
// The module owns no state and holds no clock: every timestamp is supplied by
// the caller, and every hash is re-derivable from the values published beside
// it with the gateway's own canonical-JSON digest.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  dispatchHookEvent,
  HOOK_COVERAGE,
  HOOK_DECISIONS,
  HOOK_EVENT_TYPES,
  HOOK_HOSTS,
  sha256HookJson,
  validateHookEventEnvelope,
} from "../../../../packages/plugin-host/src/hooks/gateway/hook-gateway.mjs";

/** Repository root, resolved from this file rather than the process cwd. */
export const REPOSITORY_ROOT = fileURLToPath(new URL("../../../../", import.meta.url));

export const REGISTRATIONS_PATH =
  "plugin_blueprint/epistemic-foundry/hooks/v4_h05/observability-registrations.json";
export const EVOLUTION_BUNDLE_PATH = "plugin_blueprint/epistemic-foundry/hooks/evolution.json";
export const HOLDOUT_BUNDLE_PATH = "plugin_blueprint/epistemic-foundry/hooks/holdout.json";
export const HOLDOUT_MANIFEST_SCHEMA_PATH = "schemas/holdout-manifest.schema.json";
export const HOOK_EVENT_ENVELOPE_SCHEMA_PATH = "schemas/hook-event-envelope.schema.json";
export const PLUGIN_MANIFEST_PATH = "plugin_blueprint/epistemic-foundry/.codex-plugin/plugin.json";

/** The declaring sources this module binds, in the order the receipt sorts them. */
export const DECLARING_SOURCES = Object.freeze([
  EVOLUTION_BUNDLE_PATH,
  HOLDOUT_BUNDLE_PATH,
  HOLDOUT_MANIFEST_SCHEMA_PATH,
  HOOK_EVENT_ENVELOPE_SCHEMA_PATH,
  REGISTRATIONS_PATH,
]);

/** Every way this observability surface refuses, and why that refusal exists. */
export const FINDING_CODES = Object.freeze({
  COVERAGE_OVERCLAIMED:
    "a coverage disposition claimed more observation than the registrations support, which would let an unobserved host or event pair be read as covered",
  COVERAGE_UNDECLARED:
    "a coverage disposition, or the rank that orders them, is not the vocabulary the sealed hook gateway declares",
  COVERAGE_UNDERSTATED:
    "a coverage disposition claimed less observation than the registrations support, which hides observation that actually happens",
  DECISION_PARTITION_INCOMPLETE:
    "the observer and control decision sets are not an exact partition of the gateway decision vocabulary, so a new decision would be classified by nobody",
  DECISION_UNDECLARED:
    "a registration declared a decision the sealed hook gateway does not declare, so the host would receive an unmapped outcome",
  DECLARATION_NONCANONICAL:
    "the declaration is not in canonical form (sorted, unique, exactly the declared fields), so two equal registration sets could hash differently",
  ENVELOPE_REJECTED:
    "an emitted observation did not survive revalidation as a HookEventEnvelope, so it is not evidence of anything and must not be recorded",
  EVENT_TYPE_OUT_OF_SURFACE:
    "a registration observes an event type that no evolution or holdout hook bundle declares, so it reaches past the surface H05 is allowed to observe",
  EVENT_TYPE_UNDECLARED:
    "a registration or bundle named an event type the sealed hook gateway does not declare, so the registration describes an event that cannot arrive",
  EVOLUTION_SURFACE_EMPTY:
    "the evolution event surface derived from the plugin hook bundles is empty, which would make every coverage statement vacuously satisfied",
  HOLDOUT_FLAG_UNDECLARED:
    "a registration named a holdout manifest field the sealed holdout schema does not declare, so a mistyped field would silently escape the denial check",
  HOLDOUT_OBSERVATION_DENIED:
    "a hook requested payload access to holdout-flagged material; observability may watch evolution events but never reads the sealed hidden partitions or their access flags",
  HOLDOUT_PREDICATE_EMPTY:
    "the holdout isolation predicate matched no field of the sealed schema, so the denial check would be vacuous rather than satisfied",
  HOST_UNDECLARED:
    "a registration named a host the sealed hook gateway does not declare, so it claims coverage of a host that cannot deliver events",
  OBSERVATION_UNREGISTERED:
    "an observation was offered for a registration, host or event type that the registration set does not declare, so it would be coverage nobody registered",
  OBSERVER_AUTHORITY_CLAIMED:
    "an observability registration declared a control-bearing decision; observing a host event never grants authority to allow, block or rewrite it",
  REGISTRATION_DUPLICATED:
    "two registrations claim the same identifier or the same host and event type pair, so that part of the coverage map would have no single owner",
  REGISTRATION_UNREADABLE:
    "the registration set, a hook bundle, a coverage claim or a declaring schema could not be read as the object this module requires",
  TIMESTAMP_REQUIRED:
    "an observation supplied no caller timestamp; this module holds no clock, so a missing timestamp is refused rather than invented",
});

export class HookObservabilityError extends Error {
  constructor(code, message, context = {}) {
    super(message);
    this.name = "HookObservabilityError";
    this.code = code;
    this.context = context;
  }
}

const fail = (code, message, context = {}) => {
  throw new HookObservabilityError(code, message, context);
};

const SET_FIELDS = Object.freeze([
  "control_decisions",
  "coverage_rank",
  "observed_hosts",
  "observer_decisions",
  "registration_set_id",
  "registration_set_version",
  "registrations",
]);
const REGISTRATION_FIELDS = Object.freeze([
  "coverage",
  "emits_decision",
  "event_types",
  "hosts",
  "matcher",
  "payload_access",
  "registration_id",
  "runner_argument",
  "status_message",
  "timeout_seconds",
]);
const CLAIM_FIELDS = Object.freeze(["coverage_by_event_type", "not_observed"]);

const HOST_SET = new Set(HOOK_HOSTS);
const EVENT_TYPE_SET = new Set(HOOK_EVENT_TYPES);
const DECISION_SET = new Set(HOOK_DECISIONS);
const COVERAGE_SET = new Set(HOOK_COVERAGE);

const isPlainObject = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const readText = (root, relative) => {
  try {
    return readFileSync(join(root, relative), "utf8");
  } catch (error) {
    fail("REGISTRATION_UNREADABLE", `cannot read ${relative}: ${error.message}`, {
      path: relative,
    });
    return "";
  }
};

const readJson = (root, relative) => {
  const text = readText(root, relative);
  try {
    return JSON.parse(text);
  } catch (error) {
    fail("REGISTRATION_UNREADABLE", `${relative} is not JSON: ${error.message}`, {
      path: relative,
    });
    return undefined;
  }
};

const requireFields = (value, fields, label) => {
  if (!isPlainObject(value)) {
    fail("REGISTRATION_UNREADABLE", `${label} must be an object`, { label });
  }
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail("REGISTRATION_UNREADABLE", `${label} must declare exactly ${expected.join(", ")}`, {
      actual,
      expected,
      label,
    });
  }
  return value;
};

const requireCanonicalStrings = (value, label) => {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    fail("DECLARATION_NONCANONICAL", `${label} must be an array of strings`, { label });
  }
  const sorted = [...value].sort();
  if (value.some((entry, index) => entry !== sorted[index])) {
    fail("DECLARATION_NONCANONICAL", `${label} must be sorted`, { label, value: [...value] });
  }
  if (new Set(value).size !== value.length) {
    fail("DECLARATION_NONCANONICAL", `${label} must not repeat an entry`, {
      label,
      value: [...value],
    });
  }
  return Object.freeze([...value]);
};

const requireMembers = (values, allowed, code, label) => {
  for (const value of values) {
    if (!allowed.has(value)) {
      fail(code, `${label} names "${value}", which its declaring source does not declare`, {
        declared: [...allowed].sort(),
        label,
        value,
      });
    }
  }
  return values;
};

/**
 * The event types the plugin's own evolution and holdout hook bundles register.
 *
 * H05 observes the evolution surface the plugin already declares; it does not
 * invent one.  A bundle key the gateway does not declare fails closed, because
 * a registration for an event that can never arrive is coverage on paper only.
 */
export const deriveEvolutionEventTypes = (bundles) => {
  const found = new Set();
  for (const [path, bundle] of bundles) {
    if (!isPlainObject(bundle) || !isPlainObject(bundle.hooks)) {
      fail("REGISTRATION_UNREADABLE", `${path} does not declare a hooks object`, { path });
    }
    for (const eventType of Object.keys(bundle.hooks)) {
      if (!EVENT_TYPE_SET.has(eventType)) {
        fail("EVENT_TYPE_UNDECLARED", `${path} registers undeclared event type ${eventType}`, {
          event_type: eventType,
          path,
        });
      }
      found.add(eventType);
    }
  }
  if (found.size === 0) {
    fail("EVOLUTION_SURFACE_EMPTY", "no evolution or holdout hook bundle registers any event");
  }
  return Object.freeze([...found].sort());
};

/**
 * The holdout material an observability hook may never request.
 *
 * The sealed holdout manifest pins four access flags to `false`; those names are
 * exactly the accesses the firewall closes.  The partition arrays whose names
 * end in `_partition_handles` are the opaque handles for hidden, OOD and
 * adversarial material — the schema's own naming separates them from
 * `public_partition_refs`, which is public by construction.  Both halves are
 * read from the schema, so a schema that adds an isolated partition closes it
 * here without this module being edited.
 */
export const deriveHoldoutIsolation = (schema) => {
  const properties = isPlainObject(schema) ? schema.properties : undefined;
  if (!isPlainObject(properties)) {
    fail("REGISTRATION_UNREADABLE", "the holdout manifest schema declares no properties object");
  }
  const deniedAccessFlags = [];
  const isolatedPartitions = [];
  for (const [name, definition] of Object.entries(properties)) {
    if (isPlainObject(definition) && definition.const === false) deniedAccessFlags.push(name);
    if (name.endsWith("_partition_handles")) isolatedPartitions.push(name);
  }
  if (deniedAccessFlags.length === 0 || isolatedPartitions.length === 0) {
    fail(
      "HOLDOUT_PREDICATE_EMPTY",
      "the holdout isolation predicate matched no sealed access flag or isolated partition",
      {
        denied_access_flags: deniedAccessFlags.sort(),
        isolated_partitions: isolatedPartitions.sort(),
      },
    );
  }
  return Object.freeze({
    declaredFields: Object.freeze(Object.keys(properties).sort()),
    deniedAccessFlags: Object.freeze(deniedAccessFlags.sort()),
    isolatedFields: Object.freeze([...deniedAccessFlags, ...isolatedPartitions].sort()),
    isolatedPartitions: Object.freeze(isolatedPartitions.sort()),
  });
};

/**
 * The runner command prefix the plugin's own evolution bundle already uses.
 *
 * The projection below reuses it rather than restating a command template, so a
 * plugin that moves its hook runner breaks this derivation instead of silently
 * projecting a command that no longer exists.
 */
export const deriveRunnerCommandPrefix = (bundle, path) => {
  const entries = isPlainObject(bundle) && isPlainObject(bundle.hooks) ? bundle.hooks : {};
  for (const group of Object.values(entries)) {
    if (!Array.isArray(group)) continue;
    for (const row of group) {
      for (const hook of Array.isArray(row?.hooks) ? row.hooks : []) {
        if (typeof hook?.command !== "string") continue;
        const cut = hook.command.lastIndexOf(" ");
        if (cut > 0) return hook.command.slice(0, cut);
      }
    }
  }
  fail("REGISTRATION_UNREADABLE", `${path} declares no runner command to derive a prefix from`, {
    path,
  });
  return "";
};

const coverageRank = (declaration, disposition) => declaration.coverage_rank[disposition];

const derivedRegistrationCoverage = (declaration, registration) => {
  const observed = registration.hosts.length;
  if (observed === 0) return "UNOBSERVED";
  return observed === declaration.observed_hosts.length ? "OBSERVED" : "PARTIAL";
};

const compareCoverage = (declaration, declared, derived, context) => {
  const declaredRank = coverageRank(declaration, declared);
  const derivedRank = coverageRank(declaration, derived);
  if (declaredRank > derivedRank) {
    fail("COVERAGE_OVERCLAIMED", `${context.label} claims ${declared} but only ${derived} holds`, {
      ...context,
      declared,
      derived,
    });
  }
  if (declaredRank < derivedRank) {
    fail("COVERAGE_UNDERSTATED", `${context.label} claims ${declared} while ${derived} holds`, {
      ...context,
      declared,
      derived,
    });
  }
};

const verifyVocabularyBindings = (declaration) => {
  const rankKeys = Object.keys(declaration.coverage_rank).sort();
  const coverageVocabulary = [...HOOK_COVERAGE].sort();
  if (
    rankKeys.length !== coverageVocabulary.length ||
    rankKeys.some((key, index) => key !== coverageVocabulary[index]) ||
    rankKeys.some((key) => !Number.isSafeInteger(declaration.coverage_rank[key]))
  ) {
    fail("COVERAGE_UNDECLARED", "coverage_rank must rank exactly the gateway coverage vocabulary", {
      declared: rankKeys,
      expected: coverageVocabulary,
    });
  }
  const observer = requireCanonicalStrings(declaration.observer_decisions, "observer_decisions");
  const control = requireCanonicalStrings(declaration.control_decisions, "control_decisions");
  requireMembers(observer, DECISION_SET, "DECISION_UNDECLARED", "observer_decisions");
  requireMembers(control, DECISION_SET, "DECISION_UNDECLARED", "control_decisions");
  const union = [...new Set([...observer, ...control])].sort();
  const vocabulary = [...HOOK_DECISIONS].sort();
  if (
    union.length !== observer.length + control.length ||
    union.length !== vocabulary.length ||
    union.some((entry, index) => entry !== vocabulary[index])
  ) {
    fail(
      "DECISION_PARTITION_INCOMPLETE",
      "observer_decisions and control_decisions must partition the gateway decision vocabulary",
      { control: [...control], observer: [...observer], vocabulary },
    );
  }
  return Object.freeze({ control: new Set(control), observer: new Set(observer) });
};

const verifyRegistration = (loaded, registration) => {
  const label = registration?.registration_id ?? "<unnamed registration>";
  requireFields(registration, REGISTRATION_FIELDS, `registrations[${label}]`);
  const hosts = requireCanonicalStrings(registration.hosts, `${label}.hosts`);
  const eventTypes = requireCanonicalStrings(registration.event_types, `${label}.event_types`);
  const payloadAccess = requireCanonicalStrings(
    registration.payload_access,
    `${label}.payload_access`,
  );
  requireMembers(hosts, HOST_SET, "HOST_UNDECLARED", `${label}.hosts`);
  requireMembers(
    hosts,
    new Set(loaded.declaration.observed_hosts),
    "HOST_UNDECLARED",
    `${label}.hosts`,
  );
  requireMembers(eventTypes, EVENT_TYPE_SET, "EVENT_TYPE_UNDECLARED", `${label}.event_types`);
  for (const eventType of eventTypes) {
    if (!loaded.evolutionEventTypes.includes(eventType)) {
      fail("EVENT_TYPE_OUT_OF_SURFACE", `${label} observes ${eventType} outside the surface`, {
        evolution_event_types: [...loaded.evolutionEventTypes],
        event_type: eventType,
        registration_id: label,
      });
    }
  }

  if (!COVERAGE_SET.has(registration.coverage)) {
    fail("COVERAGE_UNDECLARED", `${label} declares coverage the gateway does not declare`, {
      coverage: registration.coverage,
      declared: [...HOOK_COVERAGE],
      registration_id: label,
    });
  }
  if (loaded.decisions.control.has(registration.emits_decision)) {
    fail("OBSERVER_AUTHORITY_CLAIMED", `${label} emits control decision ${registration.emits_decision}`, {
      decision: registration.emits_decision,
      registration_id: label,
    });
  }
  if (!loaded.decisions.observer.has(registration.emits_decision)) {
    fail("DECISION_UNDECLARED", `${label} emits undeclared decision ${registration.emits_decision}`, {
      decision: registration.emits_decision,
      registration_id: label,
    });
  }

  for (const field of payloadAccess) {
    if (!loaded.holdout.declaredFields.includes(field)) {
      fail("HOLDOUT_FLAG_UNDECLARED", `${label} requests undeclared holdout field ${field}`, {
        field,
        registration_id: label,
      });
    }
    if (loaded.holdout.isolatedFields.includes(field)) {
      fail("HOLDOUT_OBSERVATION_DENIED", `${label} requests holdout-flagged field ${field}`, {
        field,
        isolated_fields: [...loaded.holdout.isolatedFields],
        registration_id: label,
      });
    }
  }

  if (registration.matcher !== null && typeof registration.matcher !== "string") {
    fail("REGISTRATION_UNREADABLE", `${label}.matcher must be a string or null`, {
      registration_id: label,
    });
  }
  for (const field of ["registration_id", "runner_argument", "status_message"]) {
    if (typeof registration[field] !== "string" || registration[field].length === 0) {
      fail("REGISTRATION_UNREADABLE", `${label}.${field} must be a non-empty string`, {
        field,
        registration_id: label,
      });
    }
  }
  if (!Number.isSafeInteger(registration.timeout_seconds) || registration.timeout_seconds < 1) {
    fail("REGISTRATION_UNREADABLE", `${label}.timeout_seconds must be a positive integer`, {
      registration_id: label,
    });
  }

  compareCoverage(
    loaded.declaration,
    registration.coverage,
    derivedRegistrationCoverage(loaded.declaration, registration),
    { label, registration_id: label },
  );
};

/** Read, cross-check and freeze the whole H05 observability registration set. */
export const loadObservability = ({ root = REPOSITORY_ROOT } = {}) => {
  const declaration = requireFields(readJson(root, REGISTRATIONS_PATH), SET_FIELDS, "registrations");
  const observedHosts = requireCanonicalStrings(declaration.observed_hosts, "observed_hosts");
  requireMembers(observedHosts, HOST_SET, "HOST_UNDECLARED", "observed_hosts");
  const decisions = verifyVocabularyBindings(declaration);

  const evolutionBundle = readJson(root, EVOLUTION_BUNDLE_PATH);
  const holdoutBundle = readJson(root, HOLDOUT_BUNDLE_PATH);
  const evolutionEventTypes = deriveEvolutionEventTypes([
    [EVOLUTION_BUNDLE_PATH, evolutionBundle],
    [HOLDOUT_BUNDLE_PATH, holdoutBundle],
  ]);
  const holdout = deriveHoldoutIsolation(readJson(root, HOLDOUT_MANIFEST_SCHEMA_PATH));

  if (!Array.isArray(declaration.registrations)) {
    fail("REGISTRATION_UNREADABLE", "registrations must be an array");
  }
  const idList = declaration.registrations.map((row) => row?.registration_id);
  const duplicate = idList.find((id, index) => idList.indexOf(id) !== index);
  if (duplicate !== undefined) {
    fail("REGISTRATION_DUPLICATED", `${duplicate} is declared by two registrations`, {
      registration_id: duplicate,
    });
  }
  const ids = requireCanonicalStrings(idList, "registrations[].registration_id");
  const loaded = {
    commandPrefix: deriveRunnerCommandPrefix(evolutionBundle, EVOLUTION_BUNDLE_PATH),
    declaration,
    decisions,
    evolutionEventTypes,
    holdout,
    root,
  };

  const claimed = new Map();
  for (const registration of declaration.registrations) {
    verifyRegistration(loaded, registration);
    for (const host of registration.hosts) {
      for (const eventType of registration.event_types) {
        const key = `${host}:${eventType}`;
        if (claimed.has(key)) {
          fail("REGISTRATION_DUPLICATED", `${key} is claimed by two registrations`, {
            pair: key,
            registration_ids: [claimed.get(key), registration.registration_id],
          });
        }
        claimed.set(key, registration.registration_id);
      }
    }
  }

  return Object.freeze({
    ...loaded,
    observedHosts,
    observedPairs: Object.freeze(new Map(claimed)),
    registrationIds: ids,
    registrationsById: Object.freeze(
      new Map(declaration.registrations.map((row) => [row.registration_id, Object.freeze(row)])),
    ),
  });
};

/**
 * The plugin hook bundle these registrations project into.
 *
 * The shape mirrors the bundles the plugin already ships, and the command
 * prefix is the one derived from those bundles.  Projecting is not installing:
 * `pluginManifestWiring` below records that the plugin manifest does not list
 * this projection, and the receipt publishes that fact rather than implying it.
 */
export const projectHookBundle = (loaded) => {
  const hooks = {};
  for (const eventType of HOOK_EVENT_TYPES) {
    const rows = loaded.declaration.registrations
      .filter((row) => row.event_types.includes(eventType))
      .map((row) => {
        const entry = {
          hooks: [
            {
              type: "command",
              command: `${loaded.commandPrefix} ${row.runner_argument}`,
              timeout: row.timeout_seconds,
              statusMessage: row.status_message,
            },
          ],
        };
        return row.matcher === null ? entry : { ...entry, matcher: row.matcher };
      });
    if (rows.length > 0) hooks[eventType] = rows;
  }
  return Object.freeze({ hooks });
};

/** Whether the plugin manifest lists this projection; it does not, and says so. */
export const pluginManifestWiring = (loaded) => {
  const manifest = readJson(loaded.root, PLUGIN_MANIFEST_PATH);
  const declared = Array.isArray(manifest?.hooks) ? manifest.hooks : [];
  const wired = declared.filter((entry) => typeof entry === "string" && entry.includes("v4_h05"));
  return Object.freeze({
    manifest_hook_count: declared.length,
    manifest_wired: wired.length > 0,
    wired_paths: Object.freeze([...wired].sort()),
  });
};

/**
 * The coverage report: for every host and event type the gateway declares, the
 * disposition the registrations actually support, plus the explicit list of
 * pairs nobody observes.  Nothing here is optimistic by default; a pair with no
 * registration is `UNOBSERVED` and appears in `not_observed`.
 *
 * The two coverage scopes in this module are deliberately different and must
 * not be conflated.  A registration's own disposition is scoped to the hosts the
 * set declares it observes, so a registration may honestly read `OBSERVED`; this
 * report is scoped to every host the gateway declares, so the same event type
 * reads `PARTIAL` while a declared host goes unwatched.  The absolute scope is
 * the one a coverage claim is checked against.
 */
export const coverageReport = (loaded) => {
  const notObserved = [];
  const eventTypes = HOOK_EVENT_TYPES.map((eventType) => {
    const observedHosts = [];
    const unobservedHosts = [];
    for (const host of HOOK_HOSTS) {
      const key = `${host}:${eventType}`;
      if (loaded.observedPairs.has(key)) observedHosts.push(host);
      else {
        unobservedHosts.push(host);
        notObserved.push(key);
      }
    }
    const coverage =
      observedHosts.length === 0
        ? "UNOBSERVED"
        : observedHosts.length === HOOK_HOSTS.length
          ? "OBSERVED"
          : "PARTIAL";
    return {
      coverage,
      event_type: eventType,
      hosts_observed: observedHosts.sort(),
      hosts_unobserved: unobservedHosts.sort(),
      in_evolution_surface: loaded.evolutionEventTypes.includes(eventType),
    };
  }).sort((left, right) => (left.event_type < right.event_type ? -1 : 1));

  return Object.freeze({
    coverage_by_event_type: Object.fromEntries(
      eventTypes.map((row) => [row.event_type, row.coverage]),
    ),
    declared_event_type_count: HOOK_EVENT_TYPES.length,
    declared_host_count: HOOK_HOSTS.length,
    event_types: eventTypes,
    evolution_event_types: [...loaded.evolutionEventTypes],
    hosts_never_observed: HOOK_HOSTS.filter(
      (host) => !loaded.observedHosts.includes(host),
    ).sort(),
    not_observed: notObserved.sort(),
    observed_pair_count: loaded.observedPairs.size,
  });
};

/**
 * Verify an externally supplied coverage claim against the derived report.
 *
 * A report that claims full coverage while a registration is missing is refused
 * as `COVERAGE_OVERCLAIMED`; a report that hides observation that does happen is
 * refused as `COVERAGE_UNDERSTATED`.  Both directions matter: the first sells
 * blindness as sight, the second hides what the plugin can see.
 */
export const assertCoverageClaim = (loaded, claim) => {
  requireFields(claim, CLAIM_FIELDS, "coverage claim");
  const derived = coverageReport(loaded);
  const claimed = claim.coverage_by_event_type;
  requireFields(claimed, HOOK_EVENT_TYPES, "coverage claim.coverage_by_event_type");
  for (const eventType of HOOK_EVENT_TYPES) {
    if (!COVERAGE_SET.has(claimed[eventType])) {
      fail("COVERAGE_UNDECLARED", `the claim for ${eventType} is outside the gateway vocabulary`, {
        coverage: claimed[eventType],
        event_type: eventType,
      });
    }
    compareCoverage(loaded.declaration, claimed[eventType], derived.coverage_by_event_type[eventType], {
      event_type: eventType,
      label: `coverage claim for ${eventType}`,
    });
  }

  const claimedMissing = requireCanonicalStrings(claim.not_observed, "coverage claim.not_observed");
  const derivedMissing = new Set(derived.not_observed);
  const omitted = [...derivedMissing].filter((pair) => !claimedMissing.includes(pair)).sort();
  if (omitted.length > 0) {
    fail("COVERAGE_OVERCLAIMED", "the claim omits host/event pairs nobody observes", { omitted });
  }
  const invented = claimedMissing.filter((pair) => !derivedMissing.has(pair)).sort();
  if (invented.length > 0) {
    fail("COVERAGE_UNDERSTATED", "the claim lists observed host/event pairs as unobserved", {
      invented,
    });
  }
  return derived;
};

const holdoutFieldsInPayload = (value, isolated, path, found, seen) => {
  if (value === null || typeof value !== "object") return found;
  if (seen.has(value)) return found;
  seen.add(value);
  if (Array.isArray(value)) {
    value.forEach((entry, index) =>
      holdoutFieldsInPayload(entry, isolated, `${path}[${index}]`, found, seen),
    );
    return found;
  }
  for (const key of Object.keys(value)) {
    const next = `${path}.${key}`;
    if (isolated.has(key)) found.push(next);
    holdoutFieldsInPayload(value[key], isolated, next, found, seen);
  }
  return found;
};

/** The holdout-flagged fields a candidate payload carries, by path. */
export const holdoutFlaggedPaths = (loaded, payload) =>
  Object.freeze(
    holdoutFieldsInPayload(
      payload,
      new Set(loaded.holdout.isolatedFields),
      "payload",
      [],
      new WeakSet(),
    ).sort(),
  );

/**
 * Revalidate an emitted observation as a HookEventEnvelope.
 *
 * The gateway seals and validates its own output; revalidating here means a
 * candidate that reached this module by any other route, or that was altered
 * after sealing, is refused rather than recorded as evidence.
 */
export const assertObservationEnvelope = (candidate, context = {}) => {
  try {
    return validateHookEventEnvelope(candidate);
  } catch (error) {
    fail("ENVELOPE_REJECTED", "an observation did not survive revalidation as a HookEventEnvelope", {
      ...context,
      gateway_code: error.code ?? null,
    });
    return undefined;
  }
};

/**
 * Observe one already-delivered host event through a declared registration.
 *
 * The registration supplies the coverage disposition the envelope is stamped
 * with and the decision the observer may emit; the caller supplies the clock.
 * A payload carrying holdout-flagged material is refused before anything is
 * hashed, so denied material never reaches a receipt.  Sealing and validation
 * belong to the gateway; this function revalidates the result and refuses to
 * return an envelope that does not survive it.
 */
export const observeEvolutionEvent = async (
  loaded,
  { registrationId, eventId, host, eventType, sessionId = null, toolName = null, observedAt, payload },
) => {
  const registration = loaded.registrationsById.get(registrationId);
  if (registration === undefined) {
    fail("OBSERVATION_UNREGISTERED", `${registrationId} is not a declared registration`, {
      registration_id: registrationId,
    });
  }
  if (!registration.hosts.includes(host) || !registration.event_types.includes(eventType)) {
    fail("OBSERVATION_UNREGISTERED", `${registrationId} does not observe ${host}:${eventType}`, {
      event_type: eventType,
      host,
      registration_id: registrationId,
    });
  }
  if (typeof observedAt !== "string" || observedAt.length === 0) {
    fail("TIMESTAMP_REQUIRED", `${registrationId} received no caller timestamp`, {
      registration_id: registrationId,
    });
  }
  if (!isPlainObject(payload)) {
    fail("REGISTRATION_UNREADABLE", `${registrationId} received a non-object payload`, {
      registration_id: registrationId,
    });
  }
  const flagged = holdoutFlaggedPaths(loaded, payload);
  if (flagged.length > 0) {
    fail("HOLDOUT_OBSERVATION_DENIED", `${registrationId} was offered holdout-flagged material`, {
      paths: [...flagged],
      registration_id: registrationId,
    });
  }

  const envelope = await dispatchHookEvent(
    {
      event_id: eventId,
      host,
      event_type: eventType,
      session_id: sessionId,
      tool_name: toolName,
      received_at: observedAt,
      raw_payload: payload,
      coverage: registration.coverage,
    },
    {
      decide: () => ({
        decision: registration.emits_decision,
        reasons: [
          `H05_OBSERVATION_ONLY:${registration.registration_id}`,
          `H05_DECLARED_COVERAGE:${registration.coverage}`,
        ],
        action_intent_id: null,
        effect_receipt_id: null,
      }),
      timeout_ms: registration.timeout_seconds * 1000,
    },
  );

  return assertObservationEnvelope({ ...envelope }, { registration_id: registrationId });
};

/**
 * An immutable receipt for the observability surface: what it read, what it
 * observes, what it explicitly does not observe, and the hash of exactly those
 * fields.  Every declaring source is bound by the gateway's own canonical-JSON
 * digest of its UTF-8 text, so a changed source changes the receipt.
 */
export const observabilityReceipt = (loaded) => {
  const report = coverageReport(loaded);
  const wiring = pluginManifestWiring(loaded);
  const preimage = {
    coverage_by_event_type: report.coverage_by_event_type,
    declaring_sources: [...DECLARING_SOURCES]
      .sort()
      .map((path) => ({ path, text_hash: sha256HookJson(readText(loaded.root, path)) })),
    evolution_event_types: [...report.evolution_event_types],
    gateway_vocabulary: {
      coverage: [...HOOK_COVERAGE],
      decisions: [...HOOK_DECISIONS],
      event_types: [...HOOK_EVENT_TYPES],
      hosts: [...HOOK_HOSTS],
    },
    holdout_denied_access_flags: [...loaded.holdout.deniedAccessFlags],
    holdout_isolated_fields: [...loaded.holdout.isolatedFields],
    hosts_never_observed: [...report.hosts_never_observed],
    not_observed: [...report.not_observed],
    observed_hosts: [...loaded.observedHosts],
    observed_pair_count: report.observed_pair_count,
    plugin_manifest_hook_count: wiring.manifest_hook_count,
    plugin_manifest_wired: wiring.manifest_wired,
    projected_bundle_hash: sha256HookJson(projectHookBundle(loaded)),
    registration_count: loaded.declaration.registrations.length,
    registration_ids: [...loaded.registrationIds],
    registration_set_id: loaded.declaration.registration_set_id,
    registration_set_version: loaded.declaration.registration_set_version,
  };
  const receiptHash = sha256HookJson(preimage);
  return Object.freeze({
    receipt_id: `EFH05-OBSERVABILITY-${receiptHash.slice("sha256:".length, "sha256:".length + 16)}`,
    ...preimage,
    receipt_hash: receiptHash,
  });
};
