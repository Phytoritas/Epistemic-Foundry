// Public entry point for the G05 evolution plugin surface.
//
// The surface is a declaration plus the refusals that keep it honest; nothing
// here executes a command, activates a skill, or holds state.

export {
  assertWithinBudget,
  deriveAuthorityBearingCommands,
  deriveEvolutionSkillIds,
  EvolutionSurfaceError,
  FAMILY_INDEX_PATH,
  FINDING_CODES,
  INVENTORY_PATH,
  loadSurface,
  MAXIMAL_DISCLOSURE_CONTEXT,
  parseAgentCard,
  parseProposedCommands,
  PAYLOAD_ROOT,
  REPOSITORY_ROOT,
  resolveDisclosure,
  ROUTING_DECISION_SCHEMA_PATH,
  routeEvolutionRequest,
  SPEC_PATH,
  SURFACE_PATH,
  surfaceReceipt,
} from "./surface.mjs";
