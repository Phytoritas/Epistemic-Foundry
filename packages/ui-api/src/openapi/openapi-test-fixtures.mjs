// Minimal in-memory OpenAPI fixtures for the ui-api surface tests.
//
// These are deliberately tiny hand-written documents rather than edits of the
// canonical one: an adversarial case has to break exactly one invariant, and
// mutating a 1190-line document tends to break several at once and prove less
// than it looks like it proves.  No fixture here is ever read as a contract;
// they exist only to make each refusal reachable.

/** A well-formed two-operation document. */
export const VALID_DOCUMENT = `openapi: 3.1.0
info:
  title: Fixture
  version: 9.9.9
servers:
  - url: /fixture/v9
paths:
  /things:
    post:
      tags: [Things]
      operationId: createThing
      summary: Create one thing
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Thing'
      responses:
        '201':
          description: Created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Thing'
        default:
          $ref: '#/components/responses/Problem'
  /things/{thing_id}:
    parameters:
      - name: thing_id
        in: path
        required: true
        schema: {type: string}
    get:
      tags: [Things]
      operationId: getThing
      summary: Read one thing
      responses:
        '200':
          description: One thing
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Thing'
        default:
          $ref: '#/components/responses/Problem'
components:
  responses:
    Problem:
      description: Problem
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
  schemas:
    Thing:
      type: object
    Problem:
      type: object
`;

/** Replace one line of a fixture, refusing a substitution that matched nothing. */
export const withLine = (document, find, replace) => {
  if (!document.includes(find)) {
    throw new Error(`fixture substitution target not present: ${find}`);
  }
  return document.replace(find, replace);
};

/** `get` on `/things/{thing_id}` with its operationId removed. */
export const MISSING_OPERATION_ID = withLine(
  VALID_DOCUMENT,
  "      operationId: getThing\n",
  "",
);

/** Both operations claiming the same operationId. */
export const DUPLICATED_OPERATION_ID = withLine(
  VALID_DOCUMENT,
  "      operationId: getThing",
  "      operationId: createThing",
);

/** A 200 response whose media type declares no schema. */
export const RESPONSE_WITHOUT_SCHEMA = withLine(
  VALID_DOCUMENT,
  `          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Thing'
        default:
          $ref: '#/components/responses/Problem'
  /things/{thing_id}:`,
  `          content:
            application/json:
              example: {}
        default:
          $ref: '#/components/responses/Problem'
  /things/{thing_id}:`,
);

/** A 200 response that declares neither `$ref` nor `content`. */
export const RESPONSE_WITHOUT_BODY = withLine(
  VALID_DOCUMENT,
  `        '200':
          description: One thing
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Thing'`,
  `        '200':
          description: One thing`,
);

/** An operation with no `responses` key at all. */
export const OPERATION_WITHOUT_RESPONSES = withLine(
  VALID_DOCUMENT,
  `      responses:
        '200':
          description: One thing
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Thing'
        default:
          $ref: '#/components/responses/Problem'`,
  "      description: An operation that declares nothing it can return",
);

/** A path item carrying a verb the transport contract never declared. */
export const UNDECLARED_HTTP_VERB = withLine(
  VALID_DOCUMENT,
  "  /things/{thing_id}:\n",
  `  /things/{thing_id}:
    purge:
      operationId: purgeThing
      responses:
        '204':
          description: Purged
`,
);

/** A response `$ref` pointing at a component the document never defines. */
export const DANGLING_REFERENCE = withLine(
  VALID_DOCUMENT,
  "          $ref: '#/components/responses/Problem'\n  /things/{thing_id}:",
  "          $ref: '#/components/responses/NotDefined'\n  /things/{thing_id}:",
);

/** A document whose root node is a sequence rather than a mapping. */
export const NON_OBJECT_DOCUMENT = "- openapi: 3.1.0\n";

/** A document with no `paths` object. */
export const NO_PATHS_DOCUMENT = `openapi: 3.1.0
info:
  title: Fixture
  version: 9.9.9
`;

/** YAML constructs this reader refuses rather than guesses at. */
export const UNSUPPORTED_YAML = Object.freeze({
  anchor: "root:\n  first: &anchor value\n",
  alias: "root:\n  first: *anchor\n",
  directive: "%YAML 1.2\nroot: value\n",
  documentMarker: "---\nroot: value\n",
  duplicateKey: "root:\n  first: one\n  first: two\n",
  explicitKey: "? complex\n: value\n",
  indentedRoot: "  root: value\n",
  tab: "root:\n\tfirst: value\n",
  unterminatedQuote: "root: 'never closed\n",
});
