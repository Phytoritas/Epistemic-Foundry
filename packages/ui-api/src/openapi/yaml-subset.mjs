// A strict, bounded YAML reader for the canonical OpenAPI document.
//
// The declaring source is YAML and this workspace ships no YAML dependency, so
// the surface has to read it itself.  Rather than approximate a full YAML
// implementation, this reader implements exactly the subset the canonical
// document uses and REFUSES anything else with `YAML_CONSTRUCT_UNSUPPORTED`.
// A guessed parse is worse than no parse: it would silently produce a route
// table the declaring document does not describe.
//
// Supported subset:
//   * block mappings (`key: value`, `key:` + indented block)
//   * block sequences (`- scalar`, `- key: value` with indented continuation)
//   * flow sequences and flow mappings of scalars and nested flow nodes
//   * folded and literal block scalars (`>`, `>-`, `|`, `|-`)
//   * single-quoted, double-quoted and plain scalars, with `null`/`~`,
//     `true`/`false` and JSON-shaped numbers resolved to native values
//   * `#` comments outside quotes
//
// Refused: anchors, aliases, explicit tags, multiple documents, directives,
// explicit-key (`? `) mappings, tab indentation, and `+` chomping.

import { refuse } from "./surface-errors.mjs";

const INTEGER_PATTERN = /^[-+]?(?:0|[1-9][0-9]*)$/u;
const FLOAT_PATTERN = /^[-+]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?$/u;
const BLOCK_SCALAR_PATTERN = /^([|>])([-]?)$/u;

/** Strip an unquoted `#` comment and any trailing whitespace. */
const stripComment = (text) => {
  let quote = null;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quote === "'") {
      if (character === "'") quote = text[index + 1] === "'" ? (index += 1, "'") : null;
      continue;
    }
    if (quote === '"') {
      if (character === "\\") index += 1;
      else if (character === '"') quote = null;
      continue;
    }
    if (character === "'" || character === '"') {
      quote = character;
      continue;
    }
    if (character === "#" && (index === 0 || text[index - 1] === " ")) {
      return text.slice(0, index).trimEnd();
    }
  }
  return text.trimEnd();
};

const scanLines = (source) => {
  const scanned = [];
  const rawLines = source.split("\n");
  for (let offset = 0; offset < rawLines.length; offset += 1) {
    const raw = rawLines[offset];
    const lineNumber = offset + 1;
    if (raw.includes("\t")) {
      refuse("YAML_CONSTRUCT_UNSUPPORTED", "tab characters are not accepted indentation", {
        line: lineNumber,
      });
    }
    const indent = raw.length - raw.trimStart().length;
    const content = stripComment(raw.slice(indent));
    if (content === "") continue;
    if (content === "---" || content === "..." || content.startsWith("%")) {
      refuse(
        "YAML_CONSTRUCT_UNSUPPORTED",
        "document markers and directives are outside the accepted subset",
        { line: lineNumber, text: content },
      );
    }
    if (content.startsWith("? ")) {
      refuse("YAML_CONSTRUCT_UNSUPPORTED", "explicit mapping keys are not accepted", {
        line: lineNumber,
      });
    }
    scanned.push({ indent, lineNumber, raw, text: content });
  }
  return scanned;
};

const readQuotedScalar = (text, lineNumber) => {
  const quote = text[0];
  let value = "";
  let index = 1;
  while (index < text.length) {
    const character = text[index];
    if (quote === "'") {
      if (character === "'") {
        if (text[index + 1] === "'") {
          value += "'";
          index += 2;
          continue;
        }
        return { rest: text.slice(index + 1), value };
      }
      value += character;
      index += 1;
      continue;
    }
    if (character === "\\") {
      const escape = text[index + 1];
      const simple = { "\\": "\\", '"': '"', "/": "/", n: "\n", t: "\t", r: "\r", b: "\b", f: "\f", 0: "\0" };
      if (Object.hasOwn(simple, escape)) {
        value += simple[escape];
        index += 2;
        continue;
      }
      if (escape === "u") {
        const code = text.slice(index + 2, index + 6);
        if (!/^[0-9a-fA-F]{4}$/u.test(code)) {
          refuse("YAML_CONSTRUCT_UNSUPPORTED", "malformed \\u escape in a double-quoted scalar", {
            line: lineNumber,
          });
        }
        value += String.fromCharCode(Number.parseInt(code, 16));
        index += 6;
        continue;
      }
      refuse("YAML_CONSTRUCT_UNSUPPORTED", `unsupported escape \\${String(escape)}`, {
        line: lineNumber,
      });
    }
    if (character === '"') return { rest: text.slice(index + 1), value };
    value += character;
    index += 1;
  }
  refuse("YAML_CONSTRUCT_UNSUPPORTED", "an opened quoted scalar is never closed on its line", {
    line: lineNumber,
  });
  return { rest: "", value: "" };
};

const resolvePlainScalar = (text) => {
  if (text === "" || text === "~" || text === "null" || text === "Null" || text === "NULL") {
    return null;
  }
  if (text === "true" || text === "True" || text === "TRUE") return true;
  if (text === "false" || text === "False" || text === "FALSE") return false;
  if (INTEGER_PATTERN.test(text)) return Number.parseInt(text, 10);
  if (FLOAT_PATTERN.test(text) && /[.eE]/u.test(text)) return Number.parseFloat(text);
  return text;
};

/** Parse a flow node (`[...]` / `{...}`) or a scalar, refusing trailing junk. */
const parseFlowOrScalar = (text, lineNumber) => {
  if (text.startsWith("[") || text.startsWith("{")) {
    const { rest, value } = parseFlowNode(text, lineNumber);
    if (rest.trim() !== "") {
      refuse("YAML_CONSTRUCT_UNSUPPORTED", "trailing content after a flow collection", {
        line: lineNumber,
        text,
      });
    }
    return value;
  }
  if (text.startsWith("'") || text.startsWith('"')) {
    const { rest, value } = readQuotedScalar(text, lineNumber);
    if (rest.trim() !== "") {
      refuse("YAML_CONSTRUCT_UNSUPPORTED", "trailing content after a quoted scalar", {
        line: lineNumber,
        text,
      });
    }
    return value;
  }
  if (text.startsWith("&") || text.startsWith("*") || text.startsWith("!")) {
    refuse("YAML_CONSTRUCT_UNSUPPORTED", "anchors, aliases and tags are not accepted", {
      line: lineNumber,
      text,
    });
  }
  return resolvePlainScalar(text);
};

const parseFlowNode = (text, lineNumber) => {
  if (text.startsWith("[")) return parseFlowSequence(text, lineNumber);
  if (text.startsWith("{")) return parseFlowMapping(text, lineNumber);
  return parseFlowScalar(text, lineNumber);
};

/** Read one scalar inside a flow collection, stopping at `,`, `]`, `}` or `:`. */
const parseFlowScalar = (text, lineNumber) => {
  if (text.startsWith("'") || text.startsWith('"')) {
    return readQuotedScalar(text, lineNumber);
  }
  let index = 0;
  while (index < text.length && !",]}".includes(text[index])) {
    if (text[index] === ":" && text[index + 1] === " ") break;
    index += 1;
  }
  return { rest: text.slice(index), value: resolvePlainScalar(text.slice(0, index).trim()) };
};

const parseFlowSequence = (text, lineNumber) => {
  const items = [];
  let rest = text.slice(1).trimStart();
  if (rest.startsWith("]")) return { rest: rest.slice(1), value: items };
  for (;;) {
    const parsed = parseFlowNode(rest, lineNumber);
    items.push(parsed.value);
    rest = parsed.rest.trimStart();
    if (rest.startsWith(",")) {
      rest = rest.slice(1).trimStart();
      continue;
    }
    if (rest.startsWith("]")) return { rest: rest.slice(1), value: items };
    refuse("YAML_CONSTRUCT_UNSUPPORTED", "malformed flow sequence", { line: lineNumber, text });
  }
};

const parseFlowMapping = (text, lineNumber) => {
  const entries = {};
  let rest = text.slice(1).trimStart();
  if (rest.startsWith("}")) return { rest: rest.slice(1), value: entries };
  for (;;) {
    const key = parseFlowScalar(rest, lineNumber);
    rest = key.rest.trimStart();
    if (!rest.startsWith(":")) {
      refuse("YAML_CONSTRUCT_UNSUPPORTED", "flow mapping entry has no value", {
        line: lineNumber,
        text,
      });
    }
    rest = rest.slice(1).trimStart();
    const parsed = parseFlowNode(rest, lineNumber);
    entries[String(key.value)] = parsed.value;
    rest = parsed.rest.trimStart();
    if (rest.startsWith(",")) {
      rest = rest.slice(1).trimStart();
      continue;
    }
    if (rest.startsWith("}")) return { rest: rest.slice(1), value: entries };
    refuse("YAML_CONSTRUCT_UNSUPPORTED", "malformed flow mapping", { line: lineNumber, text });
  }
};

/** Collect a `>`/`|` block scalar body and fold or keep its line breaks. */
const readBlockScalar = (lines, start, parentIndent, header, lineNumber) => {
  const match = BLOCK_SCALAR_PATTERN.exec(header);
  if (match === null) {
    refuse(
      "YAML_CONSTRUCT_UNSUPPORTED",
      `block scalar header ${header} is outside the accepted subset`,
      { line: lineNumber },
    );
  }
  const [, style, chomp] = match;
  const body = [];
  let index = start;
  let bodyIndent = null;
  while (index < lines.length && lines[index].indent > parentIndent) {
    if (bodyIndent === null) bodyIndent = lines[index].indent;
    body.push({ indent: lines[index].indent, text: lines[index].raw.slice(bodyIndent) });
    index += 1;
  }
  if (body.length === 0) return { next: index, value: chomp === "-" ? "" : "\n" };
  let text;
  if (style === "|") {
    text = `${body.map((entry) => entry.text).join("\n")}\n`;
  } else {
    let folded = "";
    for (let position = 0; position < body.length; position += 1) {
      const entry = body[position];
      if (position === 0) {
        folded = entry.text;
        continue;
      }
      const previous = body[position - 1];
      const moreIndented = entry.indent > bodyIndent || previous.indent > bodyIndent;
      folded += moreIndented ? `\n${entry.text}` : ` ${entry.text}`;
    }
    text = `${folded}\n`;
  }
  return { next: index, value: chomp === "-" ? text.replace(/\n+$/u, "") : text };
};

const isMappingEntry = (text) => {
  let quote = null;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quote !== null) {
      if (quote === '"' && character === "\\") index += 1;
      else if (character === quote) quote = null;
      continue;
    }
    if (character === "'" || character === '"') {
      quote = character;
      continue;
    }
    if (character === "[" || character === "{") return false;
    if (character === ":" && (index + 1 === text.length || text[index + 1] === " ")) return true;
  }
  return false;
};

const splitMappingEntry = (text, lineNumber) => {
  if (text.startsWith("'") || text.startsWith('"')) {
    const { rest, value } = readQuotedScalar(text, lineNumber);
    if (!rest.startsWith(":")) {
      refuse("YAML_CONSTRUCT_UNSUPPORTED", "quoted mapping key is not followed by ':'", {
        line: lineNumber,
        text,
      });
    }
    return { key: String(value), value: rest.slice(1).trim() };
  }
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] !== ":") continue;
    if (index + 1 === text.length) return { key: text.slice(0, index).trim(), value: "" };
    if (text[index + 1] === " ") {
      return { key: text.slice(0, index).trim(), value: text.slice(index + 1).trim() };
    }
  }
  refuse("YAML_CONSTRUCT_UNSUPPORTED", "block mapping entry has no ':' separator", {
    line: lineNumber,
    text,
  });
  return { key: "", value: "" };
};

const parseNode = (lines, index, indent) => {
  const line = lines[index];
  if (line.text === "-" || line.text.startsWith("- ")) return parseSequence(lines, index, indent);
  return parseMapping(lines, index, indent);
};

/** Parse the value that follows an empty `key:` or `-`. */
const parseIndentedValue = (lines, index, indent, lineNumber) => {
  if (index >= lines.length) return { next: index, value: null };
  const next = lines[index];
  if (next.indent > indent) return parseNode(lines, index, next.indent);
  if (next.indent === indent && (next.text === "-" || next.text.startsWith("- "))) {
    return parseSequence(lines, index, indent);
  }
  if (next.indent > indent) {
    refuse("YAML_CONSTRUCT_UNSUPPORTED", "inconsistent block indentation", { line: lineNumber });
  }
  return { next: index, value: null };
};

function parseMapping(lines, start, indent) {
  const entries = {};
  let index = start;
  while (index < lines.length && lines[index].indent === indent) {
    const line = lines[index];
    if (line.text === "-" || line.text.startsWith("- ")) break;
    const { key, value } = splitMappingEntry(line.text, line.lineNumber);
    if (Object.hasOwn(entries, key)) {
      refuse("YAML_CONSTRUCT_UNSUPPORTED", `duplicate mapping key ${key}`, {
        line: line.lineNumber,
      });
    }
    if (value === "") {
      const parsed = parseIndentedValue(lines, index + 1, indent, line.lineNumber);
      entries[key] = parsed.value;
      index = parsed.next;
      continue;
    }
    if (BLOCK_SCALAR_PATTERN.test(value) || /^[|>][+]$/u.test(value)) {
      const parsed = readBlockScalar(lines, index + 1, indent, value, line.lineNumber);
      entries[key] = parsed.value;
      index = parsed.next;
      continue;
    }
    entries[key] = parseFlowOrScalar(value, line.lineNumber);
    index += 1;
  }
  if (index < lines.length && lines[index].indent > indent) {
    refuse("YAML_CONSTRUCT_UNSUPPORTED", "unexpected deeper indentation after a mapping entry", {
      line: lines[index].lineNumber,
    });
  }
  return { next: index, value: entries };
}

function parseSequence(lines, start, indent) {
  const items = [];
  let index = start;
  while (index < lines.length && lines[index].indent === indent) {
    const line = lines[index];
    if (line.text !== "-" && !line.text.startsWith("- ")) break;
    if (line.text === "-") {
      const parsed = parseIndentedValue(lines, index + 1, indent, line.lineNumber);
      items.push(parsed.value);
      index = parsed.next;
      continue;
    }
    const dash = /^-(\s+)/u.exec(line.text);
    const offset = 1 + dash[1].length;
    const rest = line.text.slice(offset);
    if (isMappingEntry(rest)) {
      const virtual = lines.slice();
      virtual[index] = { ...line, indent: indent + offset, text: rest };
      const parsed = parseMapping(virtual, index, indent + offset);
      items.push(parsed.value);
      index = parsed.next;
      continue;
    }
    if (BLOCK_SCALAR_PATTERN.test(rest)) {
      const parsed = readBlockScalar(lines, index + 1, indent, rest, line.lineNumber);
      items.push(parsed.value);
      index = parsed.next;
      continue;
    }
    items.push(parseFlowOrScalar(rest, line.lineNumber));
    index += 1;
  }
  return { next: index, value: items };
}

/**
 * Parse one YAML document from the accepted subset.
 *
 * @param {string} source
 * @returns {unknown}
 */
export const parseYamlSubset = (source) => {
  if (typeof source !== "string") {
    refuse("YAML_CONSTRUCT_UNSUPPORTED", "YAML source must be a string");
  }
  const lines = scanLines(source);
  if (lines.length === 0) return null;
  if (lines[0].indent !== 0) {
    refuse("YAML_CONSTRUCT_UNSUPPORTED", "the document root is indented", {
      line: lines[0].lineNumber,
    });
  }
  const { next, value } = parseNode(lines, 0, 0);
  if (next !== lines.length) {
    refuse("YAML_CONSTRUCT_UNSUPPORTED", "content remains after the root node", {
      line: lines[next].lineNumber,
      text: lines[next].text,
    });
  }
  return value;
};
