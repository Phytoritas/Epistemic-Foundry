// Public surface of the ui-api OpenAPI binding.
//
// Everything reachable from here is derived from the canonical OpenAPI
// document at `openapi/epistemic-foundry-v1.openapi.yaml`.  No route, method,
// operation name or schema reference is declared in this package.

export { bytesSha256, canonicalJson, canonicalJsonSha256 } from "./canonical-hash.mjs";
export {
  CANONICAL_OPENAPI_PATH,
  PACKAGED_OPENAPI_PATH,
  REPOSITORY_ROOT,
  loadRouteTable,
  projectRouteTableFromText,
  readRepositoryDocument,
} from "./openapi-source.mjs";
export {
  BODILESS_STATUS_CODES,
  HTTP_METHODS,
  PATH_ITEM_FIELDS,
  projectRouteTable,
  routeFor,
} from "./route-table.mjs";
export {
  COVERAGE_STATES,
  bindServerSurface,
  deriveCoverageRecord,
  recomputeCoverageSha256,
} from "./server-surface.mjs";
export { FINDING_CODES, OpenApiSurfaceError } from "./surface-errors.mjs";
export { parseYamlSubset } from "./yaml-subset.mjs";
