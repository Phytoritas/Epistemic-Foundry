#!/usr/bin/env python3
"""Generate the ``web/src/generated/ui-client`` TypeScript/ESM client.

The canonical OpenAPI document is the declaring source.  This generator reads
it, re-derives the same structural invariants the Node loader in
``packages/ui-api/src/openapi`` enforces, and emits one exported function per
``operationId`` with its HTTP method and path template baked in.  Nothing in
the generated tree is hand-written, and nothing here restates a route: a route
that is not in the document cannot appear in the output.

The generator is deliberately a second, independent implementation of the same
projection.  ``packages/ui-api/src/openapi/openapi-schema.test.mjs`` and
``openapi-contract.test.mjs`` compare the two projections field for field, so a
parser or projection defect in either implementation shows up as a test
failure rather than as a client that silently disagrees with the server.

Usage::

    python generate_client.py            # write the committed tree
    python generate_client.py --check    # refuse on any byte-level drift
    python generate_client.py --out-dir DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[5]
SOURCE_DOCUMENT = "openapi/epistemic-foundry-v1.openapi.yaml"
OUTPUT_DIRECTORY = "web/src/generated/ui-client"
GENERATOR_PATH = "artifacts/work_packages/U01/attempts/0001/generate_client.py"
GENERATOR_VERSION = "1.0.0"

HTTP_METHODS = (
    "delete",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
    "trace",
)
PATH_ITEM_FIELDS = ("$ref", "description", "parameters", "servers", "summary")
BODILESS_STATUS_CODES = ("204", "205", "301", "302", "303", "304", "307", "308")
PATH_PARAMETER_PATTERN = re.compile(r"\{([A-Za-z0-9_]+)\}")
SUCCESS_STATUS_PATTERN = re.compile(r"^[23][0-9]{2}$")
OPERATION_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


class GeneratorRefusal(RuntimeError):
    """A typed refusal that mirrors the Node surface finding codes."""

    def __init__(self, code: str, detail: str, **context: object) -> None:
        self.code = code
        self.detail = detail
        self.context = dict(context)
        super().__init__(f"{code}: {detail}")


def canonical_json(value: object) -> str:
    """Canonical JSON: sorted keys, no insignificant whitespace."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bytes_sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _resolve_local_reference(document: dict[str, Any], pointer: str, where: str) -> Any:
    if not pointer.startswith("#/"):
        raise GeneratorRefusal(
            "REFERENCE_UNRESOLVABLE",
            f"{where} uses non-local reference {pointer}",
            pointer=pointer,
        )
    node: Any = document
    for raw_segment in pointer[2:].split("/"):
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or segment not in node:
            raise GeneratorRefusal(
                "REFERENCE_UNRESOLVABLE",
                f"{where} references missing component {pointer}",
                pointer=pointer,
            )
        node = node[segment]
    return node


def _dereference(
    document: dict[str, Any], node: Any, where: str
) -> tuple[str | None, Any]:
    if isinstance(node, dict) and isinstance(node.get("$ref"), str):
        return node["$ref"], _resolve_local_reference(document, node["$ref"], where)
    return None, node


def _read_content_schema(content: Any, where: str) -> dict[str, Any]:
    if content is None:
        return {"kind": "none", "mediaType": None, "ref": None}
    if not isinstance(content, dict):
        raise GeneratorRefusal(
            "DOCUMENT_MALFORMED", f"{where} content is not a media-type object"
        )
    media_types = list(content)
    if not media_types:
        raise GeneratorRefusal(
            "RESPONSE_SCHEMA_MISSING", f"{where} declares content with no media type"
        )
    for media_type in media_types:
        entry = content[media_type]
        if not isinstance(entry, dict) or not isinstance(entry.get("schema"), dict):
            raise GeneratorRefusal(
                "RESPONSE_SCHEMA_MISSING",
                f"{where} media type {media_type} declares no schema",
                mediaType=media_type,
            )
    primary = media_types[0]
    schema = content[primary]["schema"]
    ref = schema.get("$ref")
    return {
        "kind": "ref" if isinstance(ref, str) else "inline",
        "mediaType": primary,
        "ref": ref if isinstance(ref, str) else None,
    }


def _project_responses(
    document: dict[str, Any], responses: Any, where: str
) -> list[dict[str, Any]]:
    if not isinstance(responses, dict) or not responses:
        raise GeneratorRefusal(
            "RESPONSE_SCHEMA_MISSING", f"{where} declares no responses"
        )
    rows: list[dict[str, Any]] = []
    for status in responses:
        label = f"{where} response {status}"
        ref, value = _dereference(document, responses[status], label)
        if not isinstance(value, dict):
            raise GeneratorRefusal(
                "DOCUMENT_MALFORMED", f"{label} is not a response object"
            )
        has_content = "content" in value
        if not has_content and ref is None and status not in BODILESS_STATUS_CODES:
            raise GeneratorRefusal(
                "RESPONSE_SCHEMA_MISSING",
                f"{label} declares neither $ref nor content",
                status=status,
            )
        schema = (
            _read_content_schema(value.get("content"), label)
            if has_content
            else {"kind": "none", "mediaType": None, "ref": None}
        )
        rows.append(
            {
                "mediaType": schema["mediaType"],
                "responseRef": ref,
                "schemaKind": schema["kind"],
                "schemaRef": schema["ref"],
                "status": status,
            }
        )
    return rows


def _project_request_body(
    document: dict[str, Any], operation: dict[str, Any], where: str
) -> dict[str, Any]:
    if "requestBody" not in operation:
        return {
            "mediaType": None,
            "required": False,
            "schemaKind": "none",
            "schemaRef": None,
        }
    label = f"{where} requestBody"
    _ref, value = _dereference(document, operation["requestBody"], label)
    if not isinstance(value, dict):
        raise GeneratorRefusal(
            "DOCUMENT_MALFORMED", f"{label} is not a request body object"
        )
    schema = _read_content_schema(value.get("content"), label)
    if schema["kind"] == "none":
        raise GeneratorRefusal("DOCUMENT_MALFORMED", f"{label} declares no content")
    return {
        "mediaType": schema["mediaType"],
        "required": value.get("required") is True,
        "schemaKind": schema["kind"],
        "schemaRef": schema["ref"],
    }


def project_route_table(
    document: Any, document_path: str, document_sha256: str
) -> dict[str, Any]:
    """Project the parsed document into the same shape the Node loader emits."""
    if not isinstance(document, dict):
        raise GeneratorRefusal(
            "DOCUMENT_MALFORMED", "the canonical OpenAPI document is not an object"
        )
    version = document.get("openapi")
    if not isinstance(version, str) or not version.startswith("3."):
        raise GeneratorRefusal(
            "DOCUMENT_MALFORMED", "the document declares no OpenAPI 3.x version"
        )
    paths = document.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise GeneratorRefusal(
            "DOCUMENT_MALFORMED", "the document declares no paths object"
        )

    operations: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for path in paths:
        if not path.startswith("/"):
            raise GeneratorRefusal(
                "DOCUMENT_MALFORMED", f"path key {path} does not start with '/'"
            )
        path_item = paths[path]
        if not isinstance(path_item, dict):
            raise GeneratorRefusal(
                "DOCUMENT_MALFORMED", f"path item {path} is not an object"
            )
        for key in path_item:
            if key.startswith("x-") or key in PATH_ITEM_FIELDS:
                continue
            if key not in HTTP_METHODS:
                raise GeneratorRefusal(
                    "HTTP_METHOD_UNDECLARED",
                    f"path {path} declares unknown path-item key {key}",
                    key=key,
                    path=path,
                )
            operation = path_item[key]
            where = f"{key.upper()} {path}"
            if not isinstance(operation, dict):
                raise GeneratorRefusal(
                    "DOCUMENT_MALFORMED", f"{where} is not an operation object"
                )
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id.strip():
                raise GeneratorRefusal(
                    "OPERATION_ID_MISSING",
                    f"{where} declares no operationId",
                    path=path,
                    method=key,
                )
            if operation_id in seen:
                raise GeneratorRefusal(
                    "OPERATION_ID_DUPLICATED",
                    f"operationId {operation_id} is declared by "
                    f"{seen[operation_id]} and {where}",
                    operationId=operation_id,
                )
            if not OPERATION_ID_PATTERN.match(operation_id):
                # The client exports one binding per operationId, so an
                # identifier that is not a bare ECMAScript name would have to be
                # renamed, and a renamed export no longer traces to the
                # document.
                raise GeneratorRefusal(
                    "OPERATION_ID_MISSING",
                    f"{where} operationId {operation_id} is not a bare identifier",
                    operationId=operation_id,
                )
            seen[operation_id] = where
            responses = _project_responses(document, operation.get("responses"), where)
            request = _project_request_body(document, operation, where)
            successes = sorted(
                row["status"]
                for row in responses
                if SUCCESS_STATUS_PATTERN.match(row["status"])
            )
            success_status = successes[0] if successes else None
            success = next(
                (row for row in responses if row["status"] == success_status), None
            )
            tags = operation.get("tags")
            summary = operation.get("summary")
            operations.append(
                {
                    "method": key.upper(),
                    "operationId": operation_id,
                    "path": path,
                    "pathParameters": PATH_PARAMETER_PATTERN.findall(path),
                    "requestMediaType": request["mediaType"],
                    "requestRequired": request["required"],
                    "requestSchemaKind": request["schemaKind"],
                    "requestSchemaRef": request["schemaRef"],
                    "responseMediaType": None
                    if success is None
                    else success["mediaType"],
                    "responseSchemaKind": "none"
                    if success is None
                    else success["schemaKind"],
                    "responseSchemaRef": None
                    if success is None
                    else success["schemaRef"],
                    "responses": responses,
                    "statusCodes": [row["status"] for row in responses],
                    "successStatus": success_status,
                    "summary": summary if isinstance(summary, str) else "",
                    "tags": list(tags) if isinstance(tags, list) else [],
                }
            )

    operations.sort(key=lambda row: row["operationId"])
    servers = document.get("servers")
    base_path = ""
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        url = servers[0].get("url")
        base_path = url if isinstance(url, str) else ""
    info = document.get("info")
    table = {
        "apiVersion": str(info.get("version", "")) if isinstance(info, dict) else "",
        "basePath": base_path,
        "documentPath": document_path,
        "documentSha256": document_sha256,
        "openapiVersion": version,
        "operationCount": len(operations),
        "operationIds": [row["operationId"] for row in operations],
        "operations": operations,
    }
    return {**table, "routeTableSha256": canonical_sha256(table)}


CLIENT_PRELUDE = """
/** Machine codes this client refuses with, each with its standing reason. */
export const UI_CLIENT_FINDING_CODES = Object.freeze({
  PATH_PARAMETER_MISSING:
    "A path parameter the operation's path template declares was not supplied, so the request URL could not be built without leaving an unresolved placeholder in the path.",
  PATH_PARAMETER_UNKNOWN:
    "A path parameter was supplied that the operation's path template does not declare, so it would be silently dropped and the caller would believe it was sent.",
  REQUEST_BODY_MISSING:
    "The operation declares a required request body and none was supplied, so the request would be rejected by the server after a needless round trip.",
  REQUEST_BODY_UNEXPECTED:
    "A request body was supplied for an operation the document declares as carrying no request body, so the payload has no declared schema to be checked against.",
  QUERY_PARAMETER_INVALID:
    "A query parameter value is neither a string, a finite number, nor a boolean, so it has no deterministic single-valued encoding in the request URL.",
  TRANSPORT_INVALID:
    "A transport argument was supplied that is not a function, so the request descriptor could not be handed to anything able to send it.",
});

/** A refusal raised while building a request from a declared operation. */
export class UiClientError extends Error {
  constructor(code, detail, context = {}) {
    super(`${code}: ${detail}`);
    this.name = "UiClientError";
    this.code = code;
    this.detail = detail;
    this.reason = UI_CLIENT_FINDING_CODES[code];
    this.context = Object.freeze({ ...context });
    Object.freeze(this);
  }
}

const deepFreeze = (value) => {
  if (value === null || typeof value !== "object") return value;
  for (const key of Object.keys(value)) deepFreeze(value[key]);
  return Object.freeze(value);
};

const encodeQueryValue = (name, value) => {
  const kind = typeof value;
  if (kind === "string") return encodeURIComponent(value);
  if (kind === "boolean") return String(value);
  if (kind === "number" && Number.isFinite(value)) return String(value);
  throw new UiClientError(
    "QUERY_PARAMETER_INVALID",
    `query parameter ${name} is a ${kind} with no deterministic encoding`,
    { name },
  );
};

/**
 * Build one immutable request descriptor from a declared operation.
 *
 * This client performs no I/O of its own and reads no clock or random source:
 * it returns a descriptor, and hands it to `transport` only when one is given.
 */
const buildRequest = (operation, input, transport) => {
  const pathValues = input.path ?? {};
  for (const name of operation.pathParameters) {
    if (!Object.hasOwn(pathValues, name) || pathValues[name] === undefined) {
      throw new UiClientError(
        "PATH_PARAMETER_MISSING",
        `${operation.operationId} requires path parameter ${name}`,
        { operationId: operation.operationId, parameter: name },
      );
    }
  }
  for (const name of Object.keys(pathValues)) {
    if (!operation.pathParameters.includes(name)) {
      throw new UiClientError(
        "PATH_PARAMETER_UNKNOWN",
        `${operation.operationId} declares no path parameter ${name}`,
        { operationId: operation.operationId, parameter: name },
      );
    }
  }
  const hasBody = Object.hasOwn(input, "body") && input.body !== undefined;
  if (hasBody && operation.requestMediaType === null) {
    throw new UiClientError(
      "REQUEST_BODY_UNEXPECTED",
      `${operation.operationId} declares no request body`,
      { operationId: operation.operationId },
    );
  }
  if (!hasBody && operation.requestRequired) {
    throw new UiClientError(
      "REQUEST_BODY_MISSING",
      `${operation.operationId} declares a required request body`,
      { operationId: operation.operationId },
    );
  }
  const path = operation.pathParameters.reduce(
    (accumulated, name) =>
      accumulated.replace(`{${name}}`, encodeURIComponent(String(pathValues[name]))),
    operation.path,
  );
  const query = input.query ?? {};
  const search = Object.keys(query)
    .filter((name) => query[name] !== undefined)
    .sort()
    .map((name) => `${encodeURIComponent(name)}=${encodeQueryValue(name, query[name])}`)
    .join("&");
  const headers = { ...(input.headers ?? {}) };
  if (hasBody && operation.requestMediaType !== null) {
    headers["content-type"] = operation.requestMediaType;
  }
  const descriptor = deepFreeze({
    body: hasBody ? input.body : null,
    headers,
    method: operation.method,
    operationId: operation.operationId,
    path,
    pathTemplate: operation.path,
    query: search,
    requestSchemaRef: operation.requestSchemaRef,
    responseSchemaRef: operation.responseSchemaRef,
    successStatus: operation.successStatus,
    url: `${BASE_PATH}${path}${search === "" ? "" : `?${search}`}`,
  });
  if (transport === undefined) return descriptor;
  if (typeof transport !== "function") {
    throw new UiClientError(
      "TRANSPORT_INVALID",
      `${operation.operationId} was given a ${typeof transport} as transport`,
      { operationId: operation.operationId },
    );
  }
  return transport(descriptor);
};
""".strip()


def render_client(table: dict[str, Any]) -> str:
    """Render ``index.mjs`` from the projected route table."""
    header = [
        "// GENERATED FILE - DO NOT EDIT.",
        "//",
        f"// generator: {GENERATOR_PATH}",
        f"// generator_version: {GENERATOR_VERSION}",
        f"// source_document: {table['documentPath']}",
        f"// source_document_sha256: {table['documentSha256']}",
        f"// route_table_sha256: {table['routeTableSha256']}",
        f"// operation_count: {table['operationCount']}",
        "//",
        "// Every exported binding below is one operationId from the canonical",
        "// OpenAPI document, with its HTTP method and path template baked in at",
        "// generation time.  No route, schema reference or status code in this",
        "// file was written by hand; regenerate with the generator above rather",
        "// than editing, or the client stops describing the declared surface.",
        "",
    ]
    operations_literal = json.dumps(
        {row["operationId"]: row for row in table["operations"]},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    body = [
        f"export const SOURCE_DOCUMENT = Object.freeze({{\n"
        f"  operationCount: {table['operationCount']},\n"
        f"  path: {json.dumps(table['documentPath'])},\n"
        f"  routeTableSha256: {json.dumps(table['routeTableSha256'])},\n"
        f"  sha256: {json.dumps(table['documentSha256'])},\n"
        f"}});",
        "",
        f"/** The single server base path the document declares. */\n"
        f"export const BASE_PATH = {json.dumps(table['basePath'])};",
        "",
        CLIENT_PRELUDE,
        "",
        "/** Every declared operation, exactly as projected from the document. */\n"
        f"export const OPERATIONS = deepFreeze({operations_literal});",
        "",
        "/** Every declared operationId, sorted. */\n"
        "export const OPERATION_IDS = Object.freeze(Object.keys(OPERATIONS));",
        "",
    ]
    for row in table["operations"]:
        summary = row["summary"] or "No summary is declared for this operation."
        body.append(
            f"/** `{row['method']} {row['path']}` - {summary} */\n"
            f"export const {row['operationId']} = (input = {{}}, transport) =>\n"
            f"  buildRequest(OPERATIONS.{row['operationId']}, input, transport);"
        )
        body.append("")
    return "\n".join([*header, *body]).rstrip("\n") + "\n"


def render_types(table: dict[str, Any]) -> str:
    """Render ``index.d.ts`` from the projected route table."""
    header = [
        "// GENERATED FILE - DO NOT EDIT.",
        "//",
        f"// generator: {GENERATOR_PATH}",
        f"// generator_version: {GENERATOR_VERSION}",
        f"// source_document: {table['documentPath']}",
        f"// source_document_sha256: {table['documentSha256']}",
        f"// route_table_sha256: {table['routeTableSha256']}",
        f"// operation_count: {table['operationCount']}",
        "",
        "export type UiClientFindingCode =",
        '  | "PATH_PARAMETER_MISSING"',
        '  | "PATH_PARAMETER_UNKNOWN"',
        '  | "QUERY_PARAMETER_INVALID"',
        '  | "REQUEST_BODY_MISSING"',
        '  | "REQUEST_BODY_UNEXPECTED"',
        '  | "TRANSPORT_INVALID";',
        "",
        "export declare const UI_CLIENT_FINDING_CODES: Readonly<",
        "  Record<UiClientFindingCode, string>",
        ">;",
        "",
        "export declare class UiClientError extends Error {",
        "  readonly code: UiClientFindingCode;",
        "  readonly detail: string;",
        "  readonly reason: string;",
        "  readonly context: Readonly<Record<string, unknown>>;",
        "}",
        "",
        "export interface UiRequestDescriptor {",
        "  readonly body: unknown;",
        "  readonly headers: Readonly<Record<string, string>>;",
        "  readonly method: string;",
        "  readonly operationId: OperationId;",
        "  readonly path: string;",
        "  readonly pathTemplate: string;",
        "  readonly query: string;",
        "  readonly requestSchemaRef: string | null;",
        "  readonly responseSchemaRef: string | null;",
        "  readonly successStatus: string | null;",
        "  readonly url: string;",
        "}",
        "",
        "export interface UiRequestInput {",
        "  readonly path?: Readonly<Record<string, string | number>>;",
        "  readonly query?: Readonly<Record<string, string | number | boolean | undefined>>;",
        "  readonly headers?: Readonly<Record<string, string>>;",
        "  readonly body?: unknown;",
        "}",
        "",
        "export type UiTransport<T> = (request: UiRequestDescriptor) => T;",
        "",
        "export interface UiOperation {",
        "  readonly method: string;",
        "  readonly operationId: OperationId;",
        "  readonly path: string;",
        "  readonly pathParameters: readonly string[];",
        "  readonly requestMediaType: string | null;",
        "  readonly requestRequired: boolean;",
        '  readonly requestSchemaKind: "ref" | "inline" | "none";',
        "  readonly requestSchemaRef: string | null;",
        "  readonly responseMediaType: string | null;",
        '  readonly responseSchemaKind: "ref" | "inline" | "none";',
        "  readonly responseSchemaRef: string | null;",
        "  readonly responses: readonly {",
        "    readonly mediaType: string | null;",
        "    readonly responseRef: string | null;",
        '    readonly schemaKind: "ref" | "inline" | "none";',
        "    readonly schemaRef: string | null;",
        "    readonly status: string;",
        "  }[];",
        "  readonly statusCodes: readonly string[];",
        "  readonly successStatus: string | null;",
        "  readonly summary: string;",
        "  readonly tags: readonly string[];",
        "}",
        "",
        "export declare const SOURCE_DOCUMENT: Readonly<{",
        "  operationCount: number;",
        "  path: string;",
        "  routeTableSha256: string;",
        "  sha256: string;",
        "}>;",
        "",
        "export declare const BASE_PATH: string;",
        "",
        "export type OperationId =",
    ]
    for index, operation_id in enumerate(table["operationIds"]):
        terminator = ";" if index == len(table["operationIds"]) - 1 else ""
        header.append(f'  | "{operation_id}"{terminator}')
    header.extend(
        [
            "",
            "export declare const OPERATIONS: Readonly<Record<OperationId, UiOperation>>;",
            "",
            "export declare const OPERATION_IDS: readonly OperationId[];",
            "",
        ]
    )
    for row in table["operations"]:
        summary = row["summary"] or "No summary is declared for this operation."
        header.append(f"/** `{row['method']} {row['path']}` - {summary} */")
        header.append(
            f"export declare function {row['operationId']}("
            "input?: UiRequestInput): UiRequestDescriptor;"
        )
        header.append(
            f"export declare function {row['operationId']}<T>("
            "input: UiRequestInput, transport: UiTransport<T>): T;"
        )
        header.append("")
    return "\n".join(header).rstrip("\n") + "\n"


def render_manifest(table: dict[str, Any]) -> str:
    """Render ``route-manifest.json``: the projection itself, as data."""
    manifest = {
        "generator": GENERATOR_PATH,
        "generatorVersion": GENERATOR_VERSION,
        "routeTable": table,
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_outputs() -> tuple[dict[str, Any], dict[str, str]]:
    document_path = ROOT / SOURCE_DOCUMENT
    if not document_path.is_file():
        raise GeneratorRefusal(
            "DOCUMENT_SOURCE_MISSING", f"cannot read {SOURCE_DOCUMENT}"
        )
    payload = document_path.read_bytes()
    document = yaml.safe_load(payload.decode("utf-8"))
    table = project_route_table(document, SOURCE_DOCUMENT, bytes_sha256(payload))
    return table, {
        "index.d.ts": render_types(table),
        "index.mjs": render_client(table),
        "route-manifest.json": render_manifest(table),
    }


def write_outputs(out_dir: Path, outputs: dict[str, str]) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(outputs.items()):
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
    return sorted(outputs)


def check_outputs(out_dir: Path, outputs: dict[str, str]) -> tuple[int, dict[str, Any]]:
    drift: list[dict[str, str]] = []
    for name, text in sorted(outputs.items()):
        target = out_dir / name
        expected = text.encode("utf-8")
        if not target.is_file():
            drift.append({"file": name, "reason": "MISSING"})
            continue
        actual = target.read_bytes()
        if actual != expected:
            drift.append(
                {
                    "actualSha256": bytes_sha256(actual),
                    "expectedSha256": bytes_sha256(expected),
                    "file": name,
                    "reason": "BYTES_DIFFER",
                }
            )
    return (1 if drift else 0), {
        "check": "client-generation-parity",
        "drift": drift,
        "files": sorted(outputs),
        "outputDirectory": OUTPUT_DIRECTORY,
        "status": "FAIL" if drift else "PASS",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="refuse if the committed tree differs from a fresh generation",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="write elsewhere than the committed generated tree",
    )
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / OUTPUT_DIRECTORY
    try:
        table, outputs = build_outputs()
    except GeneratorRefusal as refusal:
        print(
            json.dumps(
                {
                    "code": refusal.code,
                    "context": refusal.context,
                    "detail": refusal.detail,
                    "status": "FAIL",
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    if args.check:
        code, report = check_outputs(out_dir, outputs)
        stream = sys.stderr if code else sys.stdout
        print(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            file=stream,
        )
        return code
    written = write_outputs(out_dir, outputs)
    print(
        json.dumps(
            {
                "documentSha256": table["documentSha256"],
                "files": written,
                "operationCount": table["operationCount"],
                "outputDirectory": str(out_dir),
                "routeTableSha256": table["routeTableSha256"],
                "status": "PASS",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
