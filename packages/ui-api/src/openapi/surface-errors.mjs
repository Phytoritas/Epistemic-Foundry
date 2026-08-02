// Typed refusals for the OpenAPI-derived server surface.
//
// Every refusal carries a machine code and a bounded context object.  The
// reason text for each code is stated once here, so a caller that logs the
// code can always recover why the surface refuses instead of guessing from a
// message that was written at the throw site.

/**
 * Machine codes this component refuses with.  Each reason is a complete
 * sentence long enough to be read as a finding on its own.
 */
export const FINDING_CODES = Object.freeze({
  DOCUMENT_SOURCE_MISSING:
    "The canonical OpenAPI document could not be read from its declared repository path, so no route surface can be derived and the server must refuse to start rather than serve an undeclared surface.",
  DOCUMENT_MALFORMED:
    "The canonical OpenAPI document parsed but does not have the object shape an OpenAPI 3.1 document requires, so its paths cannot be projected into a route table without inventing structure the document never declared.",
  YAML_CONSTRUCT_UNSUPPORTED:
    "The canonical OpenAPI document uses a YAML construct outside the strict subset this reader implements, and a partial or guessed parse of the declaring source would silently produce a route surface that the document does not describe.",
  OPERATION_ID_MISSING:
    "A declared path and method pair carries no operationId, so the operation cannot be named, cannot be bound to a handler, and cannot appear in a generated client without the generator inventing an identifier.",
  OPERATION_ID_DUPLICATED:
    "Two declared operations share one operationId, so a handler map or generated client keyed by operationId would silently bind one route and drop the other with no visible loss of coverage.",
  RESPONSE_SCHEMA_MISSING:
    "A declared response neither references a component response nor declares a schema for its content, so the response body is undescribed and no client or contract test can check what the operation actually returns.",
  HTTP_METHOD_UNDECLARED:
    "A path item declares a key that is neither a documented OpenAPI path-item field nor an HTTP method this surface accepts, so the document would expose a verb the transport contract never declared.",
  ROUTE_UNDECLARED:
    "A server registration names an operation the canonical OpenAPI document does not declare, so the running surface would answer a route that no contract, client, or reviewer can see.",
  HANDLER_INVALID:
    "A server registration supplied a handler entry that is not a callable function, so binding it would defer a type failure to the first request instead of refusing at composition time.",
  REFERENCE_UNRESOLVABLE:
    "An internal document reference points at a component the document does not define, so the referenced request or response contract cannot be projected and the route table would carry a dangling pointer.",
});

/** A refusal raised by the OpenAPI surface. */
export class OpenApiSurfaceError extends Error {
  /**
   * @param {keyof typeof FINDING_CODES} code
   * @param {string} detail
   * @param {Record<string, unknown>} [context]
   */
  constructor(code, detail, context = {}) {
    if (!Object.hasOwn(FINDING_CODES, code)) {
      throw new TypeError(`unknown OpenAPI surface finding code: ${String(code)}`);
    }
    super(`${code}: ${detail}`);
    this.name = "OpenApiSurfaceError";
    this.code = code;
    this.detail = detail;
    this.reason = FINDING_CODES[code];
    this.context = Object.freeze({ ...context });
    Object.freeze(this);
  }
}

/**
 * Raise one typed refusal.
 *
 * @param {keyof typeof FINDING_CODES} code
 * @param {string} detail
 * @param {Record<string, unknown>} [context]
 * @returns {never}
 */
export const refuse = (code, detail, context = {}) => {
  throw new OpenApiSurfaceError(code, detail, context);
};
