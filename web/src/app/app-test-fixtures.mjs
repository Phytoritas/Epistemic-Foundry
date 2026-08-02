/**
 * Deterministic fixtures for the U02 console shell and auth suites.
 *
 * Every value here is a literal.  No clock, no random source and no environment
 * read is used, so two runs of the same suite build byte-identical inputs and
 * the records derived from them hash identically.
 */

const HASH = `sha256:${"c".repeat(64)}`;

export const APP_FIXTURE_BODY_HASH = HASH;

/** A view specification, overridable field by field. */
export const viewSpec = (overrides = {}) => ({
  declares_mutation: false,
  operation_id: "listRuns",
  requires_auth: true,
  title: "Forge docket",
  view_id: "forge-docket",
  ...overrides,
});

/** A single-view specification list bound to one public read operation. */
export const publicViewSpecs = () => [
  viewSpec({
    operation_id: "getLiveness",
    requires_auth: false,
    title: "Process liveness",
    view_id: "liveness",
  }),
];

/** An unauthenticated console session, the state every session starts in. */
export const unauthenticatedSession = () => ({
  scheme: null,
  session_label: null,
  state: "UNAUTHENTICATED",
  transition_count: 0,
});

/** An authenticated console session, which secured views require. */
export const authenticatedSession = (overrides = {}) => ({
  scheme: "LocalSession",
  session_label: "workspace-alpha",
  state: "AUTHENTICATED",
  transition_count: 2,
  ...overrides,
});

/** An expired console session, still not authorized for secured views. */
export const expiredSession = () => ({
  scheme: "BearerAuth",
  session_label: "workspace-alpha",
  state: "EXPIRED",
  transition_count: 3,
});

/**
 * A response receipt for a read operation, overridable field by field.  The
 * default describes a populated, non-degraded success on `listRuns`.
 */
export const successReceipt = (overrides = {}) => ({
  body_hash: HASH,
  degraded_reasons: [],
  item_count: 3,
  operation_id: "listRuns",
  outcome: "SUCCESS",
  status: "200",
  ...overrides,
});

/** A receipt recording a confirmed-empty successful read. */
export const emptyReceipt = (overrides = {}) => successReceipt({ item_count: 0, ...overrides });

/** A receipt recording a success with declared degradations. */
export const degradedReceipt = (overrides = {}) =>
  successReceipt({ degraded_reasons: ["one search lane did not answer"], ...overrides });

/** A receipt recording a backend problem rather than a body. */
export const problemReceipt = (overrides = {}) => ({
  body_hash: null,
  degraded_reasons: [],
  item_count: null,
  operation_id: "listRuns",
  outcome: "PROBLEM",
  status: "503",
  ...overrides,
});

/** A receipt recording a transport failure with no HTTP status. */
export const transportFailureReceipt = (overrides = {}) => ({
  body_hash: null,
  degraded_reasons: [],
  item_count: null,
  operation_id: "listRuns",
  outcome: "TRANSPORT_FAILURE",
  status: null,
  ...overrides,
});
