// Public entry point for the H05 evolution/holdout observability hooks.
//
// Observability is a declaration plus the refusals that keep it honest.  Nothing
// here enforces a host decision, reads holdout material, or holds state; the one
// asynchronous function observes an event the host already delivered and returns
// the gateway's sealed envelope.

export {
  assertCoverageClaim,
  assertObservationEnvelope,
  coverageReport,
  DECLARING_SOURCES,
  deriveEvolutionEventTypes,
  deriveHoldoutIsolation,
  deriveRunnerCommandPrefix,
  EVOLUTION_BUNDLE_PATH,
  FINDING_CODES,
  HOLDOUT_BUNDLE_PATH,
  HOLDOUT_MANIFEST_SCHEMA_PATH,
  HOOK_EVENT_ENVELOPE_SCHEMA_PATH,
  HookObservabilityError,
  holdoutFlaggedPaths,
  loadObservability,
  observabilityReceipt,
  observeEvolutionEvent,
  PLUGIN_MANIFEST_PATH,
  pluginManifestWiring,
  projectHookBundle,
  REGISTRATIONS_PATH,
  REPOSITORY_ROOT,
} from "./observability.mjs";
