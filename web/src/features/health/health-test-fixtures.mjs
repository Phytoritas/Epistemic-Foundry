/**
 * Deterministic fixtures for the U02 health view suites.
 *
 * Every value here is a literal.  No clock, no random source and no
 * environment read, so two runs of the same suite hash identically.
 */

const HASH = `sha256:${"a".repeat(64)}`;
const REPORT_HASH = `sha256:${"b".repeat(64)}`;

/** One declared check, overridable field by field. */
export const healthCheck = (overrides = {}) => ({
  check_id: "kernel.ledger.append",
  details: "The ledger accepted an append and returned a receipt.",
  remediation: [],
  status: "PASS",
  ...overrides,
});

/** A plugin health report matching `schemas/plugin-health-report.schema.json`. */
export const healthReport = (overrides = {}) => ({
  checks: [healthCheck(), healthCheck({ check_id: "kernel.artifact.store" })],
  generated_at: "2026-01-01T00:00:00Z",
  health_id: "HR-0001",
  host_capability_report_id: "HCR-0001",
  overall: "PASS",
  plugin_version: "4.0.0",
  profile: "RESEARCH",
  report_hash: REPORT_HASH,
  ...overrides,
});

/** A degraded report: one warning check, overall DEGRADED rather than PASS. */
export const degradedHealthReport = (overrides = {}) =>
  healthReport({
    checks: [
      healthCheck(),
      healthCheck({
        check_id: "search.provider.reachable",
        details: "One configured search provider did not answer within the budget.",
        remediation: ["run `efoundry doctor --json` and inspect the provider lane"],
        status: "WARN",
      }),
    ],
    overall: "DEGRADED",
    ...overrides,
  });

/** A readiness receipt carrying a report. */
export const readinessReceipt = (report = healthReport(), overrides = {}) => ({
  body: report,
  body_hash: HASH,
  operation_id: "getReadiness",
  outcome: "SUCCESS",
  status: "200",
  ...overrides,
});

/** A readiness receipt recording a backend problem rather than a report. */
export const readinessProblemReceipt = (overrides = {}) => ({
  body: null,
  body_hash: null,
  operation_id: "getReadiness",
  outcome: "PROBLEM",
  status: "503",
  ...overrides,
});

/** A liveness receipt carrying the declared liveness constant. */
export const livenessReceipt = (overrides = {}) => ({
  body: { status: "live" },
  body_hash: HASH,
  operation_id: "getLiveness",
  outcome: "SUCCESS",
  status: "200",
  ...overrides,
});

/** An authenticated session state, which readiness requires. */
export const authenticatedSession = () => ({
  scheme: "LocalSession",
  session_label: "workspace-alpha",
  state: "AUTHENTICATED",
  transition_count: 2,
});

export const HEALTH_FIXTURE_BODY_HASH = HASH;
export const HEALTH_FIXTURE_REPORT_HASH = REPORT_HASH;
