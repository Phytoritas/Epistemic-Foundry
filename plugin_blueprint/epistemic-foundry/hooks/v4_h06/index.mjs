// Public entry point for the H06 degraded-mode integration gate.
//
// The gate stands between a declared host state and any claim of hook-verified
// provenance.  It holds no state, detects no degradation, and grants no
// authority: it reads what the host declares, projects H05's coverage through
// the enabled host set, and refuses every claim that outruns the declaration.

export {
  assertDegradedCoverageClaim,
  assertStepProvenance,
  DECLARING_SOURCES,
  DegradedModeError,
  degradedCoverageReport,
  degradedModeReceipt,
  deriveCoverageOrder,
  FINDING_CODES,
  loadDegradedModePolicy,
  openDegradedGate,
  POLICY_PATH,
  recoverHookHost,
  REPOSITORY_ROOT,
  UNVERIFIED_REASONS,
  unverifiedActions,
  validateDegradedModeReceipt,
} from "./degraded-mode.mjs";
