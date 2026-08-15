import { lstat, readFile, readdir } from "node:fs/promises";
import { dirname, extname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const workspaceRoot = resolve(repoRoot, "packages");
const policy = JSON.parse(await readFile(resolve(workspaceRoot, "boundary-policy.json"), "utf8"));
const failures = [];
const fail = (message) => failures.push(message);
const filesystemKey = process.platform === "win32" ? (value) => value.toLowerCase() : (value) => value;
const sourceExtensions = new Set([".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"]);
const dependencyFields = ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"];
const componentByName = new Map();
const componentManifestByName = new Map();
const componentExportsByName = new Map();
const componentByDirectory = new Map(
  policy.components.map((component) => [filesystemKey(component.directory), component]),
);
const edges = new Map(policy.components.map((component) => [component.packageName, new Set()]));
const recordInternalPackageEdge = (source, target) => {
  const sourcePackageName = source.packageName;
  const targetPackageName = target.packageName;
  const dependencies = edges.get(sourcePackageName);
  if (dependencies.has(targetPackageName)) return;
  dependencies.add(targetPackageName);
  const sourceLayer = policy.layers[source.layer];
  const targetLayer = policy.layers[target.layer];
  if (source.layer !== "tooling" && target.layer === "tooling") {
    fail(`${sourcePackageName}: product component may not depend on tooling ${targetPackageName}`);
  }
  if (source.layer !== "tooling" && targetLayer > sourceLayer) {
    fail(`${sourcePackageName}: outward dependency on ${targetPackageName} violates layer direction`);
  }
};
const EXPORT_PUBLIC = "PUBLIC";
const EXPORT_BLOCKED = "BLOCKED";
const EXPORT_NO_MATCH = "NO_MATCH";
const EXPORTS_TARGET_BASE = new URL("file:///__ef_boundary_package__/package.json");
const EXPORTS_TARGET_ROOT = new URL(".", EXPORTS_TARGET_BASE).pathname;
const isArrayIndexKey = (value) => {
  const number = Number(value);
  return `${number}` === value && number >= 0 && number < 0xFFFF_FFFF;
};
const hasForbiddenPatternSegment = (value) => value
  .split(/[\\/]/u)
  .some((segment) =>
    segment === "." ||
    segment === ".." ||
    segment.toLowerCase() === "node_modules");
const validExportsTargetString = (target) => {
  if (!target.startsWith("./")) return false;
  let resolvedTarget;
  try {
    resolvedTarget = new URL(target, EXPORTS_TARGET_BASE);
  } catch {
    return false;
  }
  if (
    resolvedTarget.protocol !== "file:" ||
    !resolvedTarget.pathname.startsWith(EXPORTS_TARGET_ROOT)
  ) return false;
  const targetPath = target.replace(/[\t\r\n]/gu, "").split(/[?#]/u, 1)[0];
  for (const rawSegment of targetPath.slice(2).split(/[\\/]/u)) {
    if (rawSegment.length === 0) continue;
    let segment;
    try {
      segment = decodeURIComponent(rawSegment);
    } catch {
      return false;
    }
    if (
      segment.includes("/") ||
      segment.includes("\\") ||
      segment === "." ||
      segment === ".." ||
      segment.toLowerCase() === "node_modules"
    ) return false;
  }
  return true;
};

const exportTargetStatus = (target, manifestName, location) => {
  if (target === null) return EXPORT_BLOCKED;
  if (typeof target === "string") {
    return validExportsTargetString(target) ? EXPORT_PUBLIC : EXPORT_NO_MATCH;
  }
  if (Array.isArray(target)) {
    if (target.length === 0) return EXPORT_BLOCKED;
    let publicTarget = false;
    let blockedTarget = false;
    for (let index = 0; index < target.length; index += 1) {
      const candidate = exportTargetStatus(target[index], manifestName, `${location}[${index}]`);
      if (candidate === EXPORT_PUBLIC) publicTarget = true;
      else if (candidate === EXPORT_BLOCKED) blockedTarget = true;
    }
    if (publicTarget) return EXPORT_PUBLIC;
    return blockedTarget ? EXPORT_BLOCKED : EXPORT_NO_MATCH;
  }
  if (typeof target === "object" && target !== null) {
    const conditions = Object.entries(target);
    const statuses = [];
    for (const [condition, conditionalTarget] of conditions) {
      if (isArrayIndexKey(condition)) {
        fail(`${manifestName}: ${location} contains a numeric exports condition ${condition}`);
        statuses.push(EXPORT_NO_MATCH);
      } else {
        statuses.push(exportTargetStatus(
          conditionalTarget,
          manifestName,
          `${location}.${condition}`,
        ));
      }
    }
    for (let index = 0; index < conditions.length; index += 1) {
      const [condition] = conditions[index];
      const status = statuses[index];
      if (condition === "default") {
        if (status !== EXPORT_NO_MATCH) return status;
      } else if (status === EXPORT_PUBLIC) {
        return EXPORT_PUBLIC;
      }
    }
    return EXPORT_NO_MATCH;
  }
  return EXPORT_NO_MATCH;
};

const buildExportsSurface = (manifestName, exportsField) => {
  const exact = new Map();
  const patterns = [];
  let rootPublic = false;

  if (
    typeof exportsField === "string" ||
    Array.isArray(exportsField)
  ) {
    rootPublic = exportTargetStatus(exportsField, manifestName, "exports") === EXPORT_PUBLIC;
  } else if (typeof exportsField === "object" && exportsField !== null) {
    const keys = Object.keys(exportsField);
    const subpathMap = keys.some((key) => key.startsWith("."));
    if (subpathMap && keys.some((key) => !key.startsWith("."))) {
      fail(`${manifestName}: exports may not mix subpath keys and condition keys`);
    } else if (!subpathMap) {
      rootPublic = exportTargetStatus(exportsField, manifestName, "exports") === EXPORT_PUBLIC;
    } else {
      for (const [key, target] of Object.entries(exportsField)) {
        if (key !== "." && !key.startsWith("./")) {
          fail(`${manifestName}: invalid exports subpath key ${key}`);
          continue;
        }
        const starCount = [...key].filter((character) => character === "*").length;
        if (starCount > 1) {
          fail(`${manifestName}: exports subpath key has more than one wildcard: ${key}`);
          continue;
        }
        const publicTarget =
          exportTargetStatus(target, manifestName, `exports[${key}]`) === EXPORT_PUBLIC;
        if (starCount === 0) {
          exact.set(key, publicTarget);
          continue;
        }
        const star = key.indexOf("*");
        patterns.push({
          key,
          prefix: key.slice(0, star),
          publicTarget,
          suffix: key.slice(star + 1),
        });
      }
    }
  } else {
    fail(`${manifestName}: public-package-api-only requires an explicit exports boundary`);
  }

  patterns.sort((left, right) =>
    right.prefix.length - left.prefix.length ||
    right.key.length - left.key.length ||
    (left.key < right.key ? -1 : left.key > right.key ? 1 : 0));

  return Object.freeze({
    permits(exportKey) {
      if (!exportKey.endsWith("/") && exact.has(exportKey)) return exact.get(exportKey);
      for (const pattern of patterns) {
        if (
          exportKey.startsWith(pattern.prefix) &&
          exportKey.endsWith(pattern.suffix) &&
          exportKey.length >= pattern.key.length
        ) {
          const captureEnd = exportKey.length - pattern.suffix.length;
          const capture = exportKey.slice(pattern.prefix.length, captureEnd);
          if (hasForbiddenPatternSegment(capture)) return false;
          return pattern.publicTarget;
        }
      }
      return exportKey === "." && rootPublic;
    },
  });
};

const internalPackageExport = (specifierPath) => {
  if (!filesystemKey(specifierPath).startsWith(filesystemKey("@epistemic-foundry/"))) {
    return null;
  }
  const segments = specifierPath.split("/");
  if (segments.length < 2) return null;
  const packageName = segments.slice(0, 2).join("/");
  const binding = componentExportsByName.get(filesystemKey(packageName));
  if (!binding) return null;
  return {
    exportKey: segments.length === 2 ? "." : `./${segments.slice(2).join("/")}`,
    packageName: binding.packageName,
    surface: binding.surface,
  };
};

const walk = async (root) => {
  const output = [];
  if ((await lstat(root)).isSymbolicLink()) {
    fail(`${relative(repoRoot, root)}: boundary-scanned root may not be a symbolic link`);
    return output;
  }
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const path = resolve(root, entry.name);
    if (entry.isSymbolicLink()) {
      fail(`${relative(repoRoot, path)}: symbolic links are not allowed in boundary-scanned roots`);
    } else if (["node_modules", "dist", "build", "coverage"].includes(entry.name)) continue;
    else if (entry.isDirectory()) output.push(...await walk(path));
    else if (entry.isFile()) output.push(path);
  }
  return output;
};

const pathEntryExists = async (path) => {
  try {
    await lstat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
};

const identifierStart = /^(?:[$_]|\p{ID_Start})$/u;
const identifierPart = /^(?:[$\u200C\u200D]|\p{ID_Continue})$/u;
const controlParenKeywords = new Set(["catch", "for", "if", "switch", "while", "with"]);
const declarationPrefixKeywords = new Set(["abstract", "async", "declare", "default", "export"]);
const statementBodyKeywords = new Set(["catch", "do", "else", "finally", "try"]);
const declarationBodyKeywords = new Set(["class", "enum", "interface", "module", "namespace"]);
const regexPrefixKeywords = new Set([
  "await",
  "break",
  "case",
  "continue",
  "default",
  "delete",
  "debugger",
  "do",
  "else",
  "extends",
  "in",
  "instanceof",
  "new",
  "of",
  "return",
  "throw",
  "typeof",
  "void",
  "yield",
]);
const expressionPrefixPunctuators = new Set([
  "(",
  "[",
  "{",
  ",",
  ";",
  ":",
  "=",
  "==",
  "===",
  "!",
  "!=",
  "!==",
  "?",
  "??",
  "=>",
  "...",
  "+=",
  "-=",
  "*=",
  "**=",
  "/=",
  "%=",
  "<<=",
  ">>=",
  ">>>=",
  "&=",
  "|=",
  "^=",
  "&&=",
  "||=",
  "??=",
  "+",
  "-",
  "*",
  "**",
  "%",
  "&",
  "&&",
  "|",
  "||",
  "^",
  "~",
  "<",
  "<=",
  ">",
  ">=",
]);
const multiCharacterPunctuators = [
  "...",
  ">>>=",
  "===",
  "!==",
  ">>>",
  "**=",
  "&&=",
  "||=",
  "??=",
  "<<=",
  ">>=",
  "=>",
  "==",
  "!=",
  "<=",
  ">=",
  "++",
  "--",
  "&&",
  "||",
  "??",
  "**",
  "?.",
  "<<",
  ">>",
  "+=",
  "-=",
  "*=",
  "/=",
  "%=",
  "&=",
  "|=",
  "^=",
];

const readIdentifierEscape = (text, start) => {
  if (text[start] !== "\\" || text[start + 1] !== "u") return null;
  if (text[start + 2] === "{") {
    const close = text.indexOf("}", start + 3);
    if (close === -1) return null;
    const digits = text.slice(start + 3, close);
    if (!/^[0-9A-Fa-f]{1,6}$/u.test(digits)) return null;
    const codePoint = Number.parseInt(digits, 16);
    if (codePoint > 0x10FFFF || (codePoint >= 0xD800 && codePoint <= 0xDFFF)) return null;
    return { end: close + 1, value: String.fromCodePoint(codePoint) };
  }
  const digits = text.slice(start + 2, start + 6);
  if (!/^[0-9A-Fa-f]{4}$/u.test(digits)) return null;
  const codePoint = Number.parseInt(digits, 16);
  if (codePoint >= 0xD800 && codePoint <= 0xDFFF) return null;
  return { end: start + 6, value: String.fromCodePoint(codePoint) };
};

const readIdentifierToken = (text, start) => {
  let cursor = start;
  let escaped = false;
  let value = "";
  let first = true;
  while (cursor < text.length) {
    const escape = readIdentifierEscape(text, cursor);
    const character = escape?.value ?? String.fromCodePoint(text.codePointAt(cursor));
    const accepted = first ? identifierStart.test(character) : identifierPart.test(character);
    if (!accepted) break;
    if (escape) {
      escaped = true;
      cursor = escape.end;
    } else {
      cursor += character.length;
    }
    value += character;
    first = false;
  }
  if (first) return null;
  return { end: cursor, escaped, start, type: "identifier", value };
};

const readQuotedToken = (text, start) => {
  const quote = text[start];
  let escaped = false;
  let index = start + 1;
  while (index < text.length) {
    const character = text[index];
    if (character === quote) {
      return {
        end: index + 1,
        escaped,
        start,
        terminated: true,
        type: "string",
        value: text.slice(start + 1, index),
      };
    }
    if (character === "\\") {
      escaped = true;
      index += 1;
      if (text[index] === "\r" && text[index + 1] === "\n") index += 2;
      else if (index < text.length) index += 1;
      continue;
    }
    if (
      character === "\r" ||
      character === "\n" ||
      character === "\u2028" ||
      character === "\u2029"
    ) {
      return {
        end: index,
        escaped,
        start,
        terminated: false,
        type: "string",
        value: text.slice(start + 1, index),
      };
    }
    index += 1;
  }
  return {
    end: text.length,
    escaped,
    start,
    terminated: false,
    type: "string",
    value: text.slice(start + 1),
  };
};

const javascriptTokens = (text, {
  jsx = false,
  moduleGoal = true,
  stopAfterTopLevelArrow = false,
  typescript = false,
  tsxGenericArrowLookahead = true,
} = {}) => {
  const tokens = [];

  const scanRange = (
    start,
    stopAtClosingBrace = false,
    expressionContext = false,
    inheritedFunctionContext = null,
    allowTopLevelArrowStop = false,
  ) => {
    const braceContexts = [];
    const bracketContexts = [];
    const parenContexts = [];
    const pendingConstructs = [];
    let bracketDepth = 0;
    let canStartRegex = true;
    let lineTerminatorSinceLastToken = false;
    let statementStart = !expressionContext;
    const ternaryContexts = [];
    let typeAngleDepth = 0;
    let typeContext = false;
    let pendingControlKeyword = null;
    let staticImportContext = null;
    let staticExportContext = null;
    let moduleAttributeKeyword = false;
    let pendingModuleAttributes = false;
    let declarationStatement = null;
    const classFieldContexts = [];
    let decoratorContext = null;
    const expressionArrowContexts = [];
    const recentTokens = [];
    let pendingAsyncArrow = null;
    let pendingAsyncHead = null;
    let pendingMethodBody = null;
    let pendingMethodHead = null;
    let typeAliasStatement = null;
    let previousToken = null;
    let lastToken = null;
    let index = start;
    if (start === 0) {
      if (text[index] === "\uFEFF") index += 1;
      if (text.startsWith("#!", index)) {
        index += 2;
        while (
          index < text.length &&
          !["\r", "\n", "\u2028", "\u2029"].includes(text[index])
        ) index += 1;
      }
    }

    const segmentBoundary = (edge) => {
      tokens.push({ end: -1, start: -1, type: "segment", value: `<segment-${edge}>` });
    };

    const rememberToken = (token) => {
      previousToken = lastToken;
      lastToken = token;
      recentTokens.push(token);
      if (recentTokens.length > 8) recentTokens.shift();
    };

    const currentFunctionContext = () => {
      const activeArrow = expressionArrowContexts.at(-1) ?? null;
      let bodyContext = null;
      let bodyDepth = -1;
      for (let offset = braceContexts.length - 1; offset >= 0; offset -= 1) {
        const context = braceContexts[offset];
        if (
          !context.type.startsWith("function-") &&
          context.type !== "arrow-expression" &&
          context.type !== "class-static-block"
        ) continue;
        bodyContext = context;
        bodyDepth = offset + 1;
        break;
      }
      const expressionContext = activeArrow && activeArrow.braceDepth >= bodyDepth
        ? activeArrow
        : bodyContext;
      let parameterFrame = null;
      for (let offset = parenContexts.length - 1; offset >= 0; offset -= 1) {
        if (!parenContexts[offset].functionContext) continue;
        parameterFrame = { ...parenContexts[offset], parenDepth: offset + 1 };
        break;
      }
      const classFieldFrame = classFieldContexts.at(-1) ?? null;
      let boundaryFrame = classFieldFrame;
      if (
        parameterFrame &&
        (
          !boundaryFrame ||
          parameterFrame.braceDepth > boundaryFrame.braceDepth ||
          (
            parameterFrame.braceDepth === boundaryFrame.braceDepth &&
            parameterFrame.parenDepth > boundaryFrame.parenDepth
          )
        )
      ) boundaryFrame = parameterFrame;
      if (boundaryFrame) {
        const bodyNestedInBoundary = bodyDepth > boundaryFrame.braceDepth;
        const arrowNestedInBoundary = activeArrow && (
          activeArrow.braceDepth > boundaryFrame.braceDepth ||
          activeArrow.parenDepth >= boundaryFrame.parenDepth
        );
        if (!bodyNestedInBoundary && !arrowNestedInBoundary) {
          return boundaryFrame.functionContext;
        }
      }
      return expressionContext ?? inheritedFunctionContext;
    };

    const queuePropertyMethodHead = (propertyToken) => {
      const methodContainer = braceContexts.at(-1)?.type === "object" ||
        braceContexts.at(-1)?.type.startsWith("class-");
      const propertyNamePosition = methodContainer && (
        statementStart ||
        ["#", "*", ",", ";", "{", "}"].includes(lastToken?.value) ||
        (
          lastToken?.type === "identifier" &&
          [
            "abstract",
            "accessor",
            "async",
            "declare",
            "get",
            "override",
            "private",
            "protected",
            "public",
            "readonly",
            "set",
            "static",
          ].includes(lastToken.value)
        )
      );
      if (propertyNamePosition && !(pendingMethodHead?.typeAngleDepth > 0)) {
        let prefix = recentTokens.length - 1;
        if (recentTokens[prefix]?.value === "#") prefix -= 1;
        const generator = recentTokens[prefix]?.value === "*";
        if (generator) prefix -= 1;
        const async = recentTokens[prefix]?.type === "identifier" &&
          recentTokens[prefix].value === "async" &&
          !(recentTokens[prefix + 1] ?? propertyToken).lineTerminatorBefore;
        pendingMethodHead = { async, generator, typeAngleDepth: 0 };
      }
      return propertyNamePosition;
    };

    const classFieldAtBase = (field = classFieldContexts.at(-1)) => Boolean(
      field &&
      field.braceDepth === braceContexts.length &&
      field.bracketDepth === bracketDepth &&
      field.parenDepth === parenContexts.length
    );

    const decoratorAtBase = () => Boolean(
      decoratorContext &&
      decoratorContext.braceDepth === braceContexts.length &&
      decoratorContext.bracketDepth === bracketDepth &&
      decoratorContext.parenDepth === parenContexts.length
    );

    const prepareDecoratorToken = (token) => {
      if (!decoratorAtBase()) return;
      if (!decoratorContext.expressionStarted) {
        decoratorContext.expressionStarted = true;
        return;
      }
      const continuesDecorator = typeAngleDepth > 0 ||
        [".", "?.", "(", "<", "!"].includes(token.value) ||
        (
          token.type === "identifier" &&
          (
            [".", "?.", "as", "satisfies"].includes(lastToken?.value) ||
            ["as", "satisfies"].includes(token.value)
          )
        );
      if (continuesDecorator) return;
      decoratorContext = null;
      canStartRegex = true;
      statementStart = true;
    };

    const markClassFieldAsiCandidate = () => {
      const field = classFieldContexts.at(-1);
      if (classFieldAtBase(field) && !canStartRegex) field.asiCandidate = true;
    };

    const finishClassFieldBefore = (characterIndex) => {
      const field = classFieldContexts.at(-1);
      if (!field?.asiCandidate || !classFieldAtBase(field)) return;
      const nextIdentifier = readIdentifierToken(text, characterIndex);
      const beginsNextElement = Boolean(
        nextIdentifier && !["as", "in", "instanceof", "satisfies"].includes(nextIdentifier.value)
      ) ||
        ["\"", "'", "#", "@", "}"].includes(text[characterIndex]) ||
        /[0-9]/u.test(text[characterIndex]);
      field.asiCandidate = false;
      if (!beginsNextElement) return;
      classFieldContexts.pop();
      canStartRegex = true;
      statementStart = true;
    };

    const typeAliasAtBase = () => Boolean(
      typeAliasStatement &&
      typeAliasStatement.braceDepth === braceContexts.length &&
      typeAliasStatement.bracketDepth === bracketDepth &&
      typeAliasStatement.parenDepth === parenContexts.length
    );

    const markTypeAliasLineBoundary = () => {
      if (typeAliasAtBase() && typeAliasStatement.stage === "body" && !canStartRegex) {
        typeAliasStatement.lineBreakAtBase = true;
      }
    };

    const finishTypeAliasBefore = (characterIndex) => {
      if (!typeAliasStatement?.lineBreakAtBase || !typeAliasAtBase()) return;
      typeAliasStatement.lineBreakAtBase = false;
      if (!["/", "!"].includes(text[characterIndex])) return;
      typeAliasStatement = null;
      canStartRegex = true;
      statementStart = true;
    };

    const pushToken = (token, transition = {}) => {
      if (token.lineTerminatorBefore === undefined) {
        token.lineTerminatorBefore = lineTerminatorSinceLastToken;
      }
      lineTerminatorSinceLastToken = false;
      tokens.push(token);
      if (token.type === "identifier") {
        if (token.memberName) {
          canStartRegex = false;
          statementStart = false;
        } else {
          const functionContext = currentFunctionContext();
          const keywordAllowsRegex = token.value === "await"
            ? functionContext ? functionContext.async === true : moduleGoal
            : token.value === "yield"
              ? functionContext?.generator === true
              : regexPrefixKeywords.has(token.value);
          canStartRegex = token.value === "of"
            ? token.contextualOperator === true
            : keywordAllowsRegex;
          if (statementBodyKeywords.has(token.value)) statementStart = true;
          else if (!(statementStart && declarationPrefixKeywords.has(token.value))) statementStart = false;
        }
      } else if (["literal", "string", "template"].includes(token.type)) {
        canStartRegex = false;
        statementStart = false;
      } else if (token.value === ")") {
        canStartRegex = Boolean(transition.closedParen?.control);
        statementStart = Boolean(transition.closedParen?.control);
      } else if (token.value === "]" || token.value === "++" || token.value === "--") {
        canStartRegex = false;
        statementStart = false;
      } else if (token.value === "!" && transition.postfixNonNull) {
        canStartRegex = false;
        statementStart = false;
      } else if (transition.typeAngleClose) {
        canStartRegex = false;
        statementStart = false;
      } else if (token.value === "}") {
        const expressionValued = transition.closedBrace?.expressionValued !== false;
        canStartRegex = !expressionValued;
        statementStart = !expressionValued;
      } else if (token.value === ";") {
        canStartRegex = true;
        statementStart = true;
      } else if (token.value === ":") {
        canStartRegex = true;
        statementStart = transition.statementColon === true;
      } else if (token.value === "{") {
        canStartRegex = true;
        statementStart = transition.openBrace?.statementBody === true;
      } else if (token.value === "." || token.value === "?.") {
        canStartRegex = false;
        statementStart = false;
      } else {
        canStartRegex = expressionPrefixPunctuators.has(token.value) || token.value === "/";
        statementStart = false;
      }
      if (token.value === ")" && transition.closedParen) token.closedParen = transition.closedParen;
      if (token.value === "]" && transition.closedBracket) token.closedBracket = transition.closedBracket;
      rememberToken(token);
    };

    const scanRawTemplateExpression = (start, limit) => {
      let cursor = start;
      let braceDepth = 1;
      while (cursor < limit) {
        if (text.startsWith("//", cursor)) {
          cursor += 2;
          while (cursor < limit && !["\r", "\n", "\u2028", "\u2029"].includes(text[cursor])) {
            cursor += 1;
          }
          continue;
        }
        if (text.startsWith("/*", cursor)) {
          const close = text.indexOf("*/", cursor + 2);
          if (close === -1 || close + 2 > limit) return null;
          cursor = close + 2;
          continue;
        }
        if (text[cursor] === "\"" || text[cursor] === "'") {
          const literal = readQuotedToken(text, cursor);
          if (!literal.terminated || literal.end > limit) return null;
          cursor = literal.end;
          continue;
        }
        if (text[cursor] === "`") {
          const templateEnd = scanRawTemplateLiteral(cursor, limit);
          if (templateEnd === null) return null;
          cursor = templateEnd;
          continue;
        }
        if (text[cursor] === "{") braceDepth += 1;
        else if (text[cursor] === "}") {
          braceDepth -= 1;
          if (braceDepth === 0) return cursor + 1;
        }
        cursor += 1;
      }
      return null;
    };

    const scanRawTemplateLiteral = (start, limit = text.length) => {
      if (text[start] !== "`") return null;
      let cursor = start + 1;
      while (cursor < limit) {
        if (text[cursor] === "\\") {
          cursor += Math.min(2, limit - cursor);
          continue;
        }
        if (text[cursor] === "`") return cursor + 1;
        if (text.startsWith("${", cursor)) {
          const expressionEnd = scanRawTemplateExpression(cursor + 2, limit);
          if (expressionEnd === null) return null;
          cursor = expressionEnd;
          continue;
        }
        cursor += 1;
      }
      return null;
    };

    const scanRawTypeArguments = (typeStart) => {
      if (!typescript || text[typeStart] !== "<") return null;
      const delimiters = ["<"];
      const matching = new Map([[">", "<"], [")", "("], ["]", "["], ["}", "{"]]);
      let cursor = typeStart + 1;
      while (cursor < text.length && delimiters.length > 0) {
        if (text.startsWith("//", cursor)) {
          cursor += 2;
          while (cursor < text.length && !["\r", "\n", "\u2028", "\u2029"].includes(text[cursor])) {
            cursor += 1;
          }
          continue;
        }
        if (text.startsWith("/*", cursor)) {
          const close = text.indexOf("*/", cursor + 2);
          if (close === -1) return null;
          cursor = close + 2;
          continue;
        }
        if (text[cursor] === "\"" || text[cursor] === "'") {
          const literal = readQuotedToken(text, cursor);
          if (!literal.terminated) return null;
          cursor = literal.end;
          continue;
        }
        if (text[cursor] === "`") {
          const templateEnd = scanRawTemplateLiteral(cursor);
          if (templateEnd === null) return null;
          cursor = templateEnd;
          continue;
        }
        if (text.startsWith("=>", cursor)) {
          cursor += 2;
          continue;
        }
        if (["<", "(", "[", "{"].includes(text[cursor])) {
          delimiters.push(text[cursor]);
          cursor += 1;
          continue;
        }
        if (matching.has(text[cursor])) {
          if (delimiters.at(-1) !== matching.get(text[cursor])) return null;
          delimiters.pop();
          cursor += 1;
          continue;
        }
        cursor += 1;
      }
      return delimiters.length === 0 ? cursor : null;
    };

    const followsInstantiationTypeArguments = (typeEnd) => {
      if (typeEnd === null) return false;
      let cursor = typeEnd;
      while (cursor < text.length) {
        if (/\s/u.test(text[cursor])) {
          cursor += 1;
          continue;
        }
        if (text.startsWith("//", cursor)) {
          cursor += 2;
          while (cursor < text.length && !["\r", "\n", "\u2028", "\u2029"].includes(text[cursor])) {
            cursor += 1;
          }
          continue;
        }
        if (text.startsWith("/*", cursor)) {
          const close = text.indexOf("*/", cursor + 2);
          if (close === -1) return false;
          cursor = close + 2;
          continue;
        }
        break;
      }
      if (cursor === text.length) return true;
      return ["!", "(", ")", ",", ".", "/", ";", "?", "[", "]", "`", "}"].includes(text[cursor]);
    };

    const tsxTypeParameterHeadIsDisambiguated = (typeStart, typeEnd) => {
      const delimiters = [];
      const matching = new Map([[">", "<"], [")", "("], ["]", "["], ["}", "{"]]);
      let cursor = typeStart + 1;
      while (cursor < typeEnd - 1) {
        if (text.startsWith("//", cursor)) {
          cursor += 2;
          while (cursor < typeEnd && !["\r", "\n", "\u2028", "\u2029"].includes(text[cursor])) {
            cursor += 1;
          }
          continue;
        }
        if (text.startsWith("/*", cursor)) {
          const close = text.indexOf("*/", cursor + 2);
          if (close === -1 || close + 2 > typeEnd) return false;
          cursor = close + 2;
          continue;
        }
        if (text[cursor] === "\"" || text[cursor] === "'") {
          const literal = readQuotedToken(text, cursor);
          if (!literal.terminated || literal.end > typeEnd) return false;
          cursor = literal.end;
          continue;
        }
        if (text[cursor] === "`") {
          const templateEnd = scanRawTemplateLiteral(cursor, typeEnd);
          if (templateEnd === null) return false;
          cursor = templateEnd;
          continue;
        }
        const identifier = readIdentifierToken(text, cursor);
        if (identifier) {
          if (delimiters.length === 0 && identifier.value === "extends") return true;
          cursor = identifier.end;
          continue;
        }
        if (delimiters.length === 0 && [",", "="].includes(text[cursor])) return true;
        if (["<", "(", "[", "{"].includes(text[cursor])) delimiters.push(text[cursor]);
        else if (matching.has(text[cursor])) {
          if (delimiters.at(-1) !== matching.get(text[cursor])) return false;
          delimiters.pop();
        }
        cursor += 1;
      }
      return false;
    };

    const tsxGenericArrowAt = (typeStart) => {
      if (!jsx || !typescript) return false;
      const typeEnd = scanRawTypeArguments(typeStart);
      if (
        typeEnd === null ||
        !tsxTypeParameterHeadIsDisambiguated(typeStart, typeEnd)
      ) return false;
      const tailTokens = javascriptTokens(text.slice(typeEnd), {
        jsx,
        moduleGoal,
        stopAfterTopLevelArrow: true,
        typescript,
        tsxGenericArrowLookahead: false,
      });
      if (tailTokens[0]?.value !== "(") return false;
      let cursor = 0;
      let parenDepth = 0;
      for (; cursor < tailTokens.length; cursor += 1) {
        const token = tailTokens[cursor];
        if (token.type !== "punctuator") continue;
        if (token.value === "(") parenDepth += 1;
        else if (token.value === ")") {
          parenDepth -= 1;
          if (parenDepth === 0) {
            cursor += 1;
            break;
          }
        }
      }
      if (parenDepth !== 0) return false;
      if (tailTokens[cursor]?.value === "=>") return true;
      if (tailTokens[cursor]?.value !== ":") return false;
      const delimiters = [];
      const matching = new Map([[">", "<"], [")", "("], ["]", "["], ["}", "{"]]);
      for (cursor += 1; cursor < tailTokens.length; cursor += 1) {
        const token = tailTokens[cursor];
        if (token.type === "segment") continue;
        if (token.type !== "punctuator") continue;
        if (token.value === "=>" && delimiters.length === 0) return true;
        if (["<", "(", "[", "{"].includes(token.value)) delimiters.push(token.value);
        else if ([">", ">>", ">>>"].includes(token.value)) {
          for (let count = 0; count < token.value.length; count += 1) {
            if (delimiters.at(-1) !== "<") return false;
            delimiters.pop();
          }
        }
        else if (matching.has(token.value)) {
          if (delimiters.at(-1) !== matching.get(token.value)) return false;
          delimiters.pop();
        }
      }
      return false;
    };

    const scanTemplate = (templateStart) => {
      const tokenIndex = tokens.length;
      tokens.push({ end: templateStart, start: templateStart, type: "template-pending", value: null });
      let escaped = false;
      let hasExpressions = false;
      let cursor = templateStart + 1;
      while (cursor < text.length) {
        const character = text[cursor];
        if (character === "\\") {
          escaped = true;
          cursor += 1;
          if (text[cursor] === "\r" && text[cursor + 1] === "\n") cursor += 2;
          else if (cursor < text.length) cursor += 1;
          continue;
        }
        if (character === "`") {
          const template = {
            end: cursor + 1,
            escaped,
            hasExpressions,
            lineTerminatorBefore: lineTerminatorSinceLastToken,
            start: templateStart,
            terminated: true,
            type: "template",
            value: hasExpressions ? null : text.slice(templateStart + 1, cursor),
          };
          tokens[tokenIndex] = template;
          return template;
        }
        if (character === "$" && text[cursor + 1] === "{") {
          hasExpressions = true;
          segmentBoundary("start");
          cursor = scanRange(cursor + 2, true, true, currentFunctionContext());
          segmentBoundary("end");
          continue;
        }
        cursor += 1;
      }
      const template = {
        end: text.length,
        escaped,
        hasExpressions,
        lineTerminatorBefore: lineTerminatorSinceLastToken,
        start: templateStart,
        terminated: false,
        type: "template",
        value: hasExpressions ? null : text.slice(templateStart + 1),
      };
      tokens[tokenIndex] = template;
      return template;
    };

    const scanJsxElement = (elementStart) => {
      const tokenCheckpoint = tokens.length;

      const readTagName = (nameStart) => {
        let cursor = nameStart;
        if (cursor >= text.length) return null;
        const first = String.fromCodePoint(text.codePointAt(cursor));
        if (!identifierStart.test(first)) return null;
        cursor += first.length;
        while (cursor < text.length) {
          const character = String.fromCodePoint(text.codePointAt(cursor));
          if (!identifierPart.test(character) && !["-", ".", ":"].includes(character)) break;
          cursor += character.length;
        }
        return { end: cursor, value: text.slice(nameStart, cursor) };
      };

      const readJsxQuoted = (quoteStart) => {
        const quote = text[quoteStart];
        const close = text.indexOf(quote, quoteStart + 1);
        return close === -1 ? null : close + 1;
      };

      const scanBalancedTypeArguments = (typeStart) => {
        if (!typescript || text[typeStart] !== "<") return null;
        const delimiters = ["<"];
        const matching = new Map([[">", "<"], [")", "("], ["]", "["], ["}", "{"]]);
        let cursor = typeStart + 1;
        while (cursor < text.length && delimiters.length > 0) {
          if (text.startsWith("//", cursor)) {
            cursor += 2;
            while (cursor < text.length && !["\r", "\n", "\u2028", "\u2029"].includes(text[cursor])) {
              cursor += 1;
            }
            continue;
          }
          if (text.startsWith("/*", cursor)) {
            const close = text.indexOf("*/", cursor + 2);
            if (close === -1) return null;
            cursor = close + 2;
            continue;
          }
          if (text[cursor] === "\"" || text[cursor] === "'") {
            const literal = readQuotedToken(text, cursor);
            if (!literal.terminated) return null;
            cursor = literal.end;
            continue;
          }
          if (text[cursor] === "`") {
            const templateEnd = scanRawTemplateLiteral(cursor);
            if (templateEnd === null) return null;
            cursor = templateEnd;
            continue;
          }
          if (text.startsWith("=>", cursor)) {
            cursor += 2;
            continue;
          }
          if (["<", "(", "[", "{"].includes(text[cursor])) {
            delimiters.push(text[cursor]);
            cursor += 1;
            continue;
          }
          if (matching.has(text[cursor])) {
            if (delimiters.at(-1) !== matching.get(text[cursor])) return null;
            delimiters.pop();
            cursor += 1;
            continue;
          }
          cursor += 1;
        }
        return delimiters.length === 0 ? cursor : null;
      };

      const parseElement = (openingStart) => {
        if (text[openingStart] !== "<" || text[openingStart + 1] === "/") return null;
        let cursor = openingStart + 1;
        let name = null;
        if (text[cursor] === ">") {
          cursor += 1;
        } else {
          const tag = readTagName(cursor);
          if (!tag) return null;
          name = tag.value;
          cursor = tag.end;
          if (text[cursor] === "<") {
            const typeStart = cursor;
            const afterTypeArguments = scanBalancedTypeArguments(cursor);
            if (afterTypeArguments === null) return null;
            const innerOffset = typeStart + 1;
            const innerText = text.slice(innerOffset, afterTypeArguments - 1);
            segmentBoundary("start");
            for (const token of javascriptTokens(innerText, { typescript: true })) {
              tokens.push(token.start < 0 ? token : {
                ...token,
                end: token.end + innerOffset,
                start: token.start + innerOffset,
              });
            }
            segmentBoundary("end");
            cursor = afterTypeArguments;
          }
          let openingClosed = false;
          while (cursor < text.length) {
            if (/\s/u.test(text[cursor])) {
              cursor += 1;
              continue;
            }
            if (text.startsWith("/>", cursor)) return cursor + 2;
            if (text[cursor] === ">") {
              cursor += 1;
              openingClosed = true;
              break;
            }
            if (text[cursor] === "\"" || text[cursor] === "'") {
              const attributeEnd = readJsxQuoted(cursor);
              if (attributeEnd === null) return null;
              cursor = attributeEnd;
              continue;
            }
            if (text[cursor] === "{") {
              segmentBoundary("start");
              cursor = scanRange(cursor + 1, true, true, currentFunctionContext());
              segmentBoundary("end");
              continue;
            }
            if (text[cursor] === "<") return null;
            cursor += 1;
          }
          if (!openingClosed) return null;
        }

        while (cursor < text.length) {
          if (text[cursor] === "{") {
            segmentBoundary("start");
            cursor = scanRange(cursor + 1, true, true, currentFunctionContext());
            segmentBoundary("end");
            continue;
          }
          if (text.startsWith("</", cursor)) {
            let closing = cursor + 2;
            if (name === null) {
              if (text[closing] !== ">") return null;
              return closing + 1;
            }
            const closingTag = readTagName(closing);
            if (!closingTag || closingTag.value !== name) return null;
            closing = closingTag.end;
            while (closing < text.length && /\s/u.test(text[closing])) closing += 1;
            return text[closing] === ">" ? closing + 1 : null;
          }
          if (text[cursor] === "<") {
            const nested = parseElement(cursor);
            if (nested === null) return null;
            cursor = nested;
            continue;
          }
          cursor += 1;
        }
        return null;
      };

      const end = parseElement(elementStart);
      if (end === null) tokens.length = tokenCheckpoint;
      return end;
    };

    const linePrefixIsWhitespace = (position) => {
      for (let cursor = position - 1; cursor >= 0; cursor -= 1) {
        if (["\r", "\n", "\u2028", "\u2029"].includes(text[cursor])) return true;
        if (!/\s/u.test(text[cursor])) return false;
      }
      return true;
    };

    while (index < text.length) {
      const character = text[index];
      if (
        !moduleGoal &&
        (
          text.startsWith("<!--", index) ||
          (text.startsWith("-->", index) && linePrefixIsWhitespace(index))
        )
      ) {
        while (
          index < text.length &&
          !["\r", "\n", "\u2028", "\u2029"].includes(text[index])
        ) index += 1;
        continue;
      }
      if (/\s/u.test(character)) {
        let sawLineTerminator = false;
        while (index < text.length && /\s/u.test(text[index])) {
          if (["\r", "\n", "\u2028", "\u2029"].includes(text[index])) sawLineTerminator = true;
          index += 1;
        }
        if (sawLineTerminator && lastToken?.completesModuleDeclaration) {
          canStartRegex = true;
          statementStart = true;
        }
        if (
          sawLineTerminator &&
          declarationStatement?.bindingSeen &&
          !declarationStatement.hasInitializer &&
          declarationStatement.braceDepth === braceContexts.length &&
          declarationStatement.bracketDepth === bracketDepth &&
          declarationStatement.parenDepth === parenContexts.length &&
          !canStartRegex
        ) {
          canStartRegex = true;
          declarationStatement = null;
          statementStart = true;
        }
        if (sawLineTerminator) lineTerminatorSinceLastToken = true;
        if (sawLineTerminator) pendingAsyncHead = null;
        if (sawLineTerminator) markClassFieldAsiCandidate();
        if (sawLineTerminator) markTypeAliasLineBoundary();
        continue;
      }
      if (character === "/" && text[index + 1] === "/") {
        index += 2;
        while (
          index < text.length &&
          text[index] !== "\r" &&
          text[index] !== "\n" &&
          text[index] !== "\u2028" &&
          text[index] !== "\u2029"
        ) index += 1;
        continue;
      }
      if (character === "/" && text[index + 1] === "*") {
        const end = text.indexOf("*/", index + 2);
        const commentEnd = end === -1 ? text.length : end + 2;
        if (
          lastToken?.completesModuleDeclaration &&
          /[\r\n\u2028\u2029]/u.test(text.slice(index, commentEnd))
        ) {
          canStartRegex = true;
          statementStart = true;
        }
        if (/[\r\n\u2028\u2029]/u.test(text.slice(index, commentEnd))) {
          lineTerminatorSinceLastToken = true;
          pendingAsyncHead = null;
          markClassFieldAsiCandidate();
          markTypeAliasLineBoundary();
        }
        index = commentEnd;
        continue;
      }
      finishClassFieldBefore(index);
      finishTypeAliasBefore(index);
      if (character === "\"" || character === "'") {
        const token = readQuotedToken(text, index);
        token.lineTerminatorBefore = lineTerminatorSinceLastToken;
        prepareDecoratorToken(token);
        queuePropertyMethodHead(token);
        if (pendingAsyncHead?.typeAngleDepth === 0) pendingAsyncHead = null;
        if (pendingAsyncArrow && !pendingAsyncArrow.inReturnType) pendingAsyncArrow = null;
        if (pendingMethodBody && !pendingMethodBody.inReturnType) pendingMethodBody = null;
        const completesImport = (
          staticImportContext &&
          staticImportContext.braceDepth === braceContexts.length &&
          staticImportContext.bracketDepth === bracketDepth &&
          staticImportContext.parenDepth === parenContexts.length
        );
        const completesExport = (
          staticExportContext?.seenFrom === true &&
          staticExportContext.braceDepth === braceContexts.length &&
          staticExportContext.bracketDepth === bracketDepth &&
          staticExportContext.parenDepth === parenContexts.length
        );
        if (completesImport || completesExport) {
          token.completesModuleDeclaration = true;
          pendingModuleAttributes = true;
          staticImportContext = null;
          staticExportContext = null;
        }
        pushToken(token);
        index = token.end > index ? token.end : index + 1;
        continue;
      }
      if (character === "`") {
        const template = scanTemplate(index);
        index = template.end;
        canStartRegex = false;
        lineTerminatorSinceLastToken = false;
        statementStart = false;
        rememberToken(template);
        continue;
      }
      const identifier = readIdentifierToken(text, index);
      if (identifier) {
        identifier.lineTerminatorBefore = lineTerminatorSinceLastToken;
        const identifierAtStatementStart = statementStart;
        const memberName = ["#", ".", "?."].includes(lastToken?.value);
        identifier.memberName = memberName;
        prepareDecoratorToken(identifier);
        const propertyNamePosition = queuePropertyMethodHead(identifier);
        if (
          typescript &&
          !memberName &&
          !propertyNamePosition &&
          identifierAtStatementStart &&
          identifier.value === "type"
        ) {
          typeAliasStatement = {
            braceDepth: braceContexts.length,
            bracketDepth,
            lineBreakAtBase: false,
            parenDepth: parenContexts.length,
            stage: "name",
          };
        } else if (
          !memberName &&
          typeAliasAtBase() &&
          typeAliasStatement.stage === "name"
        ) typeAliasStatement.stage = "after-name";
        if (!memberName && identifier.value === "async") {
          pendingAsyncHead = { typeAngleDepth: 0 };
        } else if (pendingAsyncHead?.typeAngleDepth === 0 && identifier.value !== "function") {
          pendingAsyncHead = null;
        }
        if (pendingAsyncArrow && !pendingAsyncArrow.inReturnType) pendingAsyncArrow = null;
        if (pendingMethodBody && !pendingMethodBody.inReturnType) pendingMethodBody = null;
        if (
          !memberName &&
          statementStart &&
          ["const", "let", "using", "var"].includes(identifier.value)
        ) {
          declarationStatement = {
            bindingSeen: false,
            braceDepth: braceContexts.length,
            bracketDepth,
            hasInitializer: false,
            parenDepth: parenContexts.length,
          };
        } else if (
          declarationStatement &&
          declarationStatement.braceDepth === braceContexts.length &&
          declarationStatement.bracketDepth === bracketDepth &&
          declarationStatement.parenDepth === parenContexts.length
        ) declarationStatement.bindingSeen = true;
        if (!memberName && identifier.value === "import") {
          staticImportContext = {
            braceDepth: braceContexts.length,
            bracketDepth,
            parenDepth: parenContexts.length,
          };
        }
        if (!memberName && identifier.value === "export") {
          staticExportContext = {
            braceDepth: braceContexts.length,
            bracketDepth,
            parenDepth: parenContexts.length,
            seenFrom: false,
            stage: "start",
          };
        } else if (
          staticExportContext &&
          staticExportContext.braceDepth === braceContexts.length &&
          staticExportContext.bracketDepth === bracketDepth &&
          staticExportContext.parenDepth === parenContexts.length
        ) {
          if (staticExportContext.stage === "start" && identifier.value === "type") {
            staticExportContext.stage = "type";
          } else if (staticExportContext.stage === "reexport" && identifier.value === "from") {
            staticExportContext.seenFrom = true;
          } else if (staticExportContext.stage !== "reexport") {
            staticExportContext = null;
          }
        }
        moduleAttributeKeyword = !memberName &&
          pendingModuleAttributes &&
          ["assert", "with"].includes(identifier.value);
        if (pendingModuleAttributes && !moduleAttributeKeyword) pendingModuleAttributes = false;
        const forContext = parenContexts.at(-1)?.control === "for" ? parenContexts.at(-1) : null;
        if (forContext && !memberName && !forContext.classic) {
          if (["const", "let", "using", "var"].includes(identifier.value) && !forContext.bindingDeclaration) {
            forContext.bindingDeclaration = true;
          } else if (identifier.value === "of") {
            if (forContext.bindingDeclaration && !forContext.bindingNameSeen) {
              forContext.bindingNameSeen = true;
              identifier.contextualOperator = false;
            } else {
              identifier.contextualOperator = !forContext.ofSeen && !canStartRegex;
              if (identifier.contextualOperator) forContext.ofSeen = true;
            }
          } else if (forContext.bindingDeclaration && !forContext.bindingNameSeen) {
            forContext.bindingNameSeen = true;
          }
        }
        if (typescript && !memberName && ["as", "satisfies"].includes(identifier.value)) {
          typeContext = true;
        }
        if (!memberName && controlParenKeywords.has(identifier.value)) {
          pendingControlKeyword = identifier.value;
        } else if (!(pendingControlKeyword === "for" && identifier.value === "await")) {
          pendingControlKeyword = null;
        }
        if (!memberName && !propertyNamePosition && identifier.value === "function") {
          pendingConstructs.push({
            async: lastToken?.type === "identifier" &&
              !lastToken.memberName &&
              lastToken.value === "async" &&
              !identifier.lineTerminatorBefore,
            braceDepth: braceContexts.length,
            bracketDepth,
            expressionValued: !statementStart,
            generator: false,
            parenDepth: parenContexts.length,
            stage: "head",
            type: "function",
          });
        } else if (
          !memberName &&
          !propertyNamePosition &&
          declarationBodyKeywords.has(identifier.value) &&
          (identifier.value === "class" || statementStart)
        ) {
          pendingConstructs.push({
            braceDepth: braceContexts.length,
            bracketDepth,
            expressionValued: identifier.value === "class" ? !statementStart : false,
            parenDepth: parenContexts.length,
            stage: "body",
            type: identifier.value,
          });
        }
        pushToken(identifier);
        index = identifier.end;
        continue;
      }
      if (/[0-9]/u.test(character)) {
        let end = index + 1;
        while (end < text.length && /[0-9A-Za-z_.]/u.test(text[end])) end += 1;
        const token = {
          end,
          lineTerminatorBefore: lineTerminatorSinceLastToken,
          start: index,
          type: "literal",
          value: text.slice(index, end),
        };
        prepareDecoratorToken(token);
        queuePropertyMethodHead(token);
        if (pendingAsyncHead?.typeAngleDepth === 0) pendingAsyncHead = null;
        if (pendingAsyncArrow && !pendingAsyncArrow.inReturnType) pendingAsyncArrow = null;
        if (pendingMethodBody && !pendingMethodBody.inReturnType) pendingMethodBody = null;
        pushToken(token);
        index = end;
        continue;
      }
      if (
        jsx &&
        character === "<" &&
        canStartRegex &&
        (!tsxGenericArrowLookahead || !tsxGenericArrowAt(index)) &&
        (text[index + 1] === ">" || readIdentifierToken(text, index + 1))
      ) {
        const jsxStart = index;
        const jsxEnd = scanJsxElement(index);
        if (jsxEnd !== null) {
          index = jsxEnd;
          canStartRegex = false;
          lineTerminatorSinceLastToken = false;
          statementStart = false;
          rememberToken({ end: jsxEnd, start: jsxStart, type: "literal", value: "<jsx>" });
          continue;
        }
      }
      if (character === "/" && canStartRegex) {
        moduleAttributeKeyword = false;
        pendingModuleAttributes = false;
        const regexStart = index;
        let cursor = index + 1;
        let closingSlash = -1;
        let inClass = false;
        while (cursor < text.length) {
          if (text[cursor] === "\\") {
            cursor += 2;
            continue;
          }
          if (text[cursor] === "[") inClass = true;
          else if (text[cursor] === "]") inClass = false;
          else if (text[cursor] === "/" && !inClass) {
            closingSlash = cursor;
            cursor += 1;
            while (cursor < text.length && identifierPart.test(text[cursor])) cursor += 1;
            break;
          } else if (
            text[cursor] === "\r" ||
            text[cursor] === "\n" ||
            text[cursor] === "\u2028" ||
            text[cursor] === "\u2029"
          ) {
            break;
          }
          cursor += 1;
        }
        let validRegex = false;
        if (closingSlash !== -1) {
          const pattern = text.slice(regexStart + 1, closingSlash);
          const flags = text.slice(closingSlash + 1, cursor);
          try {
            new RegExp(pattern, flags);
            validRegex = true;
          } catch {
            // A slash misclassified by contextual keyword tracking is division
            // in valid source. Re-enter the punctuator path at the same byte.
          }
        }
        if (!validRegex) {
          canStartRegex = false;
          continue;
        }
        index = cursor;
        canStartRegex = false;
        lineTerminatorSinceLastToken = false;
        rememberToken({ end: cursor, start: regexStart, type: "literal", value: "<regex>" });
        continue;
      }
      if (character === "}") {
        if (stopAtClosingBrace && braceContexts.length === 0) return index + 1;
      }
      const punctuator = multiCharacterPunctuators.find((candidate) =>
        text.startsWith(candidate, index),
      ) ?? character;
      const stopsAtThisArrow = allowTopLevelArrowStop &&
        punctuator === "=>" &&
        braceContexts.length === 0 &&
        bracketDepth === 0 &&
        parenContexts.length === 0 &&
        typeAngleDepth === 0;
      const decoratorContainer = braceContexts.at(-1);
      const startsDecorator = punctuator === "@" &&
        (
          statementStart ||
          decoratorAtBase() ||
          (
            decoratorContainer?.type.startsWith("class-") &&
            decoratorContainer.bracketDepth === bracketDepth &&
            decoratorContainer.parenDepth === parenContexts.length
          )
        );
      if (startsDecorator) {
        decoratorContext = {
          braceDepth: braceContexts.length,
          bracketDepth,
          expressionStarted: false,
          parenDepth: parenContexts.length,
        };
      } else {
        prepareDecoratorToken({ type: "punctuator", value: punctuator });
      }
      let transition = {
        postfixNonNull: typescript && punctuator === "!" && !canStartRegex,
      };
      if (pendingModuleAttributes && !(punctuator === "{" && moduleAttributeKeyword)) {
        moduleAttributeKeyword = false;
        pendingModuleAttributes = false;
      }
      if (
        staticExportContext &&
        staticExportContext.braceDepth === braceContexts.length &&
        staticExportContext.bracketDepth === bracketDepth &&
        staticExportContext.parenDepth === parenContexts.length &&
        ["start", "type"].includes(staticExportContext.stage)
      ) {
        if (["*", "{"].includes(punctuator)) staticExportContext.stage = "reexport";
        else staticExportContext = null;
      }
      if (pendingAsyncHead) {
        if (punctuator === "<") pendingAsyncHead.typeAngleDepth += 1;
        else if (pendingAsyncHead.typeAngleDepth > 0 && [">", ">>", ">>>"].includes(punctuator)) {
          pendingAsyncHead.typeAngleDepth = Math.max(
            0,
            pendingAsyncHead.typeAngleDepth - punctuator.length,
          );
        } else if (pendingAsyncHead.typeAngleDepth === 0 && punctuator !== "(") {
          pendingAsyncHead = null;
        }
      }
      if (pendingMethodHead) {
        if (punctuator === "<") pendingMethodHead.typeAngleDepth += 1;
        else if (pendingMethodHead.typeAngleDepth > 0 && [">", ">>", ">>>"].includes(punctuator)) {
          pendingMethodHead.typeAngleDepth = Math.max(
            0,
            pendingMethodHead.typeAngleDepth - punctuator.length,
          );
        } else if (
          pendingMethodHead.typeAngleDepth === 0 &&
          ["=", ":", ",", ";"].includes(punctuator)
        ) pendingMethodHead = null;
      }
      if (pendingAsyncArrow) {
        const atAsyncArrowBase = pendingAsyncArrow.braceDepth === braceContexts.length &&
          pendingAsyncArrow.bracketDepth === bracketDepth &&
          pendingAsyncArrow.parenDepth === parenContexts.length;
        if (atAsyncArrowBase && punctuator === ":") pendingAsyncArrow.inReturnType = true;
        else if (
          atAsyncArrowBase &&
          !pendingAsyncArrow.inReturnType &&
          punctuator !== "=>"
        ) pendingAsyncArrow = null;
        else if (
          atAsyncArrowBase &&
          pendingAsyncArrow.inReturnType &&
          [";", "=", ","].includes(punctuator)
        ) pendingAsyncArrow = null;
      }
      if (pendingMethodBody) {
        const atMethodBodyBase = pendingMethodBody.braceDepth === braceContexts.length &&
          pendingMethodBody.bracketDepth === bracketDepth &&
          pendingMethodBody.parenDepth === parenContexts.length;
        if (atMethodBodyBase && punctuator === ":") pendingMethodBody.inReturnType = true;
        else if (
          atMethodBodyBase &&
          !pendingMethodBody.inReturnType &&
          punctuator !== "{"
        ) pendingMethodBody = null;
        else if (
          atMethodBodyBase &&
          pendingMethodBody.inReturnType &&
          [";", "=", ","].includes(punctuator)
        ) pendingMethodBody = null;
      }
      const activeArrow = expressionArrowContexts.at(-1);
      const matchingTernary = ternaryContexts.at(-1);
      const closesMatchingTernary = punctuator === ":" &&
        matchingTernary?.braceDepth === braceContexts.length &&
        matchingTernary.bracketDepth === bracketDepth &&
        matchingTernary.parenDepth === parenContexts.length;
      if (activeArrow && (
        ([";", ","].includes(punctuator) &&
          activeArrow.braceDepth === braceContexts.length &&
          activeArrow.bracketDepth === bracketDepth &&
          activeArrow.parenDepth === parenContexts.length &&
          activeArrow.typeAngleDepth === typeAngleDepth) ||
        (punctuator === ")" && parenContexts.length <= activeArrow.parenDepth) ||
        (punctuator === "]" && bracketDepth <= activeArrow.bracketDepth) ||
        (punctuator === "}" && braceContexts.length <= activeArrow.braceDepth) ||
        (closesMatchingTernary && activeArrow.ternaryDepth === ternaryContexts.length)
      )) expressionArrowContexts.pop();
      if (punctuator === "=>") {
        const parenthesizedAsync = (
          lastToken?.value === ")" && lastToken.closedParen?.asyncArrow === true
        ) || pendingAsyncArrow?.inReturnType === true;
        const singleParameterAsync = lastToken?.type === "identifier" &&
          previousToken?.type === "identifier" &&
          !previousToken.memberName &&
          previousToken.value === "async" &&
          !lastToken.lineTerminatorBefore;
        expressionArrowContexts.push({
          async: parenthesizedAsync || singleParameterAsync,
          braceDepth: braceContexts.length,
          bracketDepth,
          generator: false,
          parenDepth: parenContexts.length,
          ternaryDepth: ternaryContexts.length,
          typeAngleDepth,
          type: "arrow-expression",
        });
        pendingAsyncArrow = null;
      }
      const activeForContext = parenContexts.at(-1)?.control === "for" ? parenContexts.at(-1) : null;
      if (
        activeForContext?.bindingDeclaration &&
        !activeForContext.bindingNameSeen &&
        ["[", "{"].includes(punctuator)
      ) activeForContext.bindingNameSeen = true;
      const atDeclarationBase = declarationStatement &&
        declarationStatement.braceDepth === braceContexts.length &&
        declarationStatement.bracketDepth === bracketDepth &&
        declarationStatement.parenDepth === parenContexts.length;
      if (atDeclarationBase && punctuator === "=") declarationStatement.hasInitializer = true;
      else if (atDeclarationBase && punctuator === ",") {
        declarationStatement.bindingSeen = false;
        declarationStatement.hasInitializer = false;
      } else if (atDeclarationBase && ["[", "{"].includes(punctuator)) {
        declarationStatement.bindingSeen = true;
      }
      if (typeAliasAtBase()) {
        if (punctuator === "=" && typeAliasStatement.stage === "after-name") {
          typeAliasStatement.stage = "body";
        } else if (
          punctuator === ";" ||
          punctuator === "}" ||
          (punctuator === "=" && typeAliasStatement.stage === "name")
        ) typeAliasStatement = null;
      }
      const classContainer = braceContexts.at(-1);
      const atClassElementBase = classContainer?.type.startsWith("class-") &&
        classContainer.bracketDepth === bracketDepth &&
        classContainer.parenDepth === parenContexts.length;
      const activeClassField = classFieldContexts.at(-1);
      if (
        classFieldAtBase(activeClassField) &&
        (
          punctuator === ";" ||
          (punctuator === "}" && atClassElementBase)
        )
      ) classFieldContexts.pop();
      if (
        punctuator === "=" &&
        atClassElementBase &&
        typeAngleDepth === 0 &&
        !(pendingMethodHead?.typeAngleDepth > 0) &&
        classFieldContexts.at(-1)?.braceDepth !== braceContexts.length
      ) {
        classFieldContexts.push({
          asiCandidate: false,
          braceDepth: braceContexts.length,
          bracketDepth,
          functionContext: {
            async: false,
            generator: false,
            type: "class-field-initializer",
          },
          parenDepth: parenContexts.length,
        });
      }
      if (
        staticImportContext &&
        ["(", "."].includes(punctuator) &&
        lastToken?.type === "identifier" &&
        lastToken.value === "import"
      ) staticImportContext = null;
      const instantiationTypeArguments = typescript &&
        punctuator === "<" &&
        !canStartRegex &&
        followsInstantiationTypeArguments(scanRawTypeArguments(index));
      if (
        typescript &&
        punctuator === "<" &&
        (typeContext || typeAngleDepth > 0 || instantiationTypeArguments)
      ) {
        typeAngleDepth += 1;
      } else if (typescript && typeAngleDepth > 0 && [">", ">>", ">>>"].includes(punctuator)) {
        typeAngleDepth = Math.max(0, typeAngleDepth - punctuator.length);
        if (typeAngleDepth === 0) {
          typeContext = false;
          transition.typeAngleClose = true;
        }
      } else if (
        typeAngleDepth === 0 &&
        [";", ",", "=", ")", "]", "}", "/", "+", "-", "*", "%", "&&", "||", "??"].includes(punctuator)
      ) typeContext = false;
      if (
        punctuator === "*" &&
        pendingConstructs.at(-1)?.type === "function" &&
        pendingConstructs.at(-1).stage === "head"
      ) {
        pendingConstructs.at(-1).generator = true;
        pendingControlKeyword = null;
      } else if (punctuator === "(") {
        const immediateControl = (
          lastToken?.type === "identifier" &&
          !lastToken.memberName &&
          controlParenKeywords.has(lastToken.value)
        );
        const control = pendingControlKeyword ?? (immediateControl ? lastToken.value : null);
        const container = braceContexts.at(-1);
        const methodContainer = container?.type === "object" || container?.type.startsWith("class-");
        const computedMethod = lastToken?.value === "]" ? lastToken.closedBracket : null;
        let methodPrefix = recentTokens.length - 2;
        if (recentTokens[methodPrefix]?.value === "#") methodPrefix -= 1;
        const privateOrNamedGenerator = recentTokens[methodPrefix]?.value === "*";
        if (privateOrNamedGenerator) methodPrefix -= 1;
        const privateOrNamedAsync = recentTokens[methodPrefix]?.type === "identifier" &&
          recentTokens[methodPrefix].value === "async" &&
          !recentTokens[methodPrefix + 1]?.lineTerminatorBefore;
        const queuedMethod = pendingMethodHead?.typeAngleDepth === 0 ? pendingMethodHead : null;
        const methodLike = methodContainer && Boolean(
          queuedMethod || computedMethod?.computedMethod === true,
        );
        const methodGenerator = methodLike && (
          queuedMethod?.generator === true ||
          computedMethod?.computedGenerator === true ||
          privateOrNamedGenerator
        );
        const methodAsync = methodLike && (
          queuedMethod?.async === true || computedMethod?.computedAsync === true || privateOrNamedAsync
        );
        const pendingFunction = pendingConstructs.at(-1);
        const functionParameters = pendingFunction?.type === "function" &&
          pendingFunction.stage === "head" &&
          pendingFunction.braceDepth === braceContexts.length &&
          pendingFunction.bracketDepth === bracketDepth &&
          pendingFunction.parenDepth === parenContexts.length;
        pendingControlKeyword = null;
        const asyncArrowHead = (
          lastToken?.type === "identifier" &&
          !lastToken.memberName &&
          lastToken.value === "async" &&
          !lineTerminatorSinceLastToken
        ) || pendingAsyncHead?.typeAngleDepth === 0;
        parenContexts.push({
          asyncArrow: asyncArrowHead,
          bindingDeclaration: false,
          bindingNameSeen: false,
          braceDepth: braceContexts.length,
          classic: false,
          control,
          functionContext: methodLike
            ? { async: methodAsync, generator: methodGenerator, type: "method-parameters" }
            : functionParameters
              ? {
                async: pendingFunction.async === true,
                generator: pendingFunction.generator === true,
                type: "function-parameters",
              }
              : null,
          methodAsync,
          methodGenerator,
          methodLike,
          ofSeen: false,
        });
        pendingAsyncHead = null;
        pendingMethodHead = null;
        if (functionParameters) {
          pendingFunction.stage = "parameters";
          pendingFunction.parameterDepth = parenContexts.length;
        }
      } else if (punctuator === ")") {
        const closedParen = parenContexts.pop() ?? { control: false };
        transition = { closedParen };
        if (closedParen.asyncArrow) {
          pendingAsyncArrow = {
            braceDepth: braceContexts.length,
            bracketDepth,
            inReturnType: false,
            parenDepth: parenContexts.length,
          };
        }
        if (closedParen.methodLike) {
          pendingMethodBody = {
            async: closedParen.methodAsync === true,
            braceDepth: braceContexts.length,
            bracketDepth,
            generator: closedParen.methodGenerator === true,
            inReturnType: false,
            parenDepth: parenContexts.length,
          };
        }
        const pending = pendingConstructs.at(-1);
        if (
          pending?.type === "function" &&
          pending.stage === "parameters" &&
          pending.parameterDepth === parenContexts.length + 1
        ) {
          pending.stage = "body";
          pending.parenDepth = parenContexts.length;
        }
      } else if (punctuator === "[") {
        pendingControlKeyword = null;
        const container = braceContexts.at(-1);
        const computedMethod = container?.type === "object" || container?.type.startsWith("class-");
        const computedGenerator = computedMethod && lastToken?.value === "*";
        const computedAsync = computedMethod && (
          (lastToken?.type === "identifier" &&
            lastToken.value === "async" &&
            !lineTerminatorSinceLastToken) ||
          (computedGenerator &&
            previousToken?.type === "identifier" &&
            previousToken.value === "async" &&
            !lastToken.lineTerminatorBefore)
        );
        bracketContexts.push({ computedAsync, computedGenerator, computedMethod });
        bracketDepth += 1;
      } else if (punctuator === "]") {
        pendingControlKeyword = null;
        const closedBracket = bracketContexts.pop() ?? null;
        transition = { ...transition, closedBracket };
        if (closedBracket?.computedMethod) {
          pendingMethodHead = {
            async: closedBracket.computedAsync === true,
            generator: closedBracket.computedGenerator === true,
            typeAngleDepth: 0,
          };
        }
        bracketDepth = Math.max(0, bracketDepth - 1);
      } else if (punctuator === "{") {
        pendingControlKeyword = null;
        const pending = pendingConstructs.at(-1);
        let kind;
        if (moduleAttributeKeyword && pendingModuleAttributes) {
          kind = {
            expressionValued: false,
            moduleAttributes: true,
            statementBody: false,
            type: "module-attributes",
          };
          moduleAttributeKeyword = false;
          pendingModuleAttributes = false;
        } else if (
          pendingMethodBody &&
          pendingMethodBody.braceDepth === braceContexts.length &&
          pendingMethodBody.bracketDepth === bracketDepth &&
          pendingMethodBody.parenDepth === parenContexts.length
        ) {
          kind = {
            async: pendingMethodBody.async === true,
            expressionValued: false,
            generator: pendingMethodBody.generator === true,
            statementBody: true,
            type: "function-method",
          };
          pendingMethodBody = null;
        } else if (
          pending?.stage === "body" &&
          pending.braceDepth === braceContexts.length &&
          pending.bracketDepth === bracketDepth &&
          pending.parenDepth === parenContexts.length
        ) {
          pendingConstructs.pop();
          kind = {
            async: pending.async === true,
            expressionValued: pending.expressionValued,
            generator: pending.generator === true,
            statementBody: true,
            type: `${pending.type}-${pending.expressionValued ? "expression" : "declaration"}`,
          };
        } else if (lastToken?.value === "=>") {
          const arrow = expressionArrowContexts.pop() ?? { async: false, generator: false };
          kind = {
            async: arrow.async === true,
            expressionValued: true,
            generator: false,
            statementBody: true,
            type: "arrow-expression",
          };
        } else if (lastToken?.value === ")" && lastToken.closedParen?.methodLike) {
          kind = {
            async: lastToken.closedParen.methodAsync === true,
            expressionValued: false,
            generator: lastToken.closedParen.methodGenerator === true,
            statementBody: true,
            type: "function-method",
          };
        } else if (
          braceContexts.at(-1)?.type.startsWith("class-") &&
          braceContexts.at(-1).bracketDepth === bracketDepth &&
          braceContexts.at(-1).parenDepth === parenContexts.length &&
          lastToken?.type === "identifier" &&
          lastToken.value === "static"
        ) {
          kind = {
            async: false,
            expressionValued: false,
            generator: false,
            statementBody: true,
            type: "class-static-block",
          };
        } else if (lastToken?.value === "default") {
          kind = { expressionValued: true, statementBody: false, type: "object" };
        } else if (
          statementStart ||
          lastToken?.value === ")" ||
          (braceContexts.at(-1)?.type.startsWith("class-") && lastToken?.value === "static")
        ) {
          kind = { expressionValued: false, statementBody: true, type: "block" };
        } else {
          kind = { expressionValued: true, statementBody: false, type: "object" };
        }
        kind.bracketDepth = bracketDepth;
        kind.parenDepth = parenContexts.length;
        braceContexts.push(kind);
        transition = { openBrace: kind };
      } else if (punctuator === "}") {
        pendingControlKeyword = null;
        transition = {
          closedBrace: braceContexts.pop() ?? {
            expressionValued: true,
            statementBody: false,
            type: "unmatched",
          },
        };
      } else if (punctuator === ".") {
        pendingControlKeyword = null;
        const pending = pendingConstructs.at(-1);
        if (
          pending &&
          pending.type === "module" &&
          pending.stage === "body" &&
          pending.braceDepth === braceContexts.length &&
          lastToken?.type === "identifier" &&
          lastToken.value === "module"
        ) {
          pendingConstructs.pop();
        }
      } else if (punctuator === ";") {
        pendingControlKeyword = null;
        declarationStatement = null;
        staticImportContext = null;
        staticExportContext = null;
        moduleAttributeKeyword = false;
        pendingModuleAttributes = false;
        const forContext = parenContexts.at(-1);
        if (forContext?.control === "for" && forContext.braceDepth === braceContexts.length) {
          forContext.classic = true;
        }
        while (
          pendingConstructs.length > 0 &&
          pendingConstructs.at(-1).braceDepth === braceContexts.length &&
          pendingConstructs.at(-1).parenDepth === parenContexts.length
        ) pendingConstructs.pop();
      } else {
        pendingControlKeyword = null;
        if (punctuator === "?") {
          ternaryContexts.push({
            braceDepth: braceContexts.length,
            bracketDepth,
            parenDepth: parenContexts.length,
          });
        } else if (punctuator === ":") {
          const ternary = ternaryContexts.at(-1);
          const closesTernary = ternary?.braceDepth === braceContexts.length &&
            ternary.bracketDepth === bracketDepth &&
            ternary.parenDepth === parenContexts.length;
          const statementColon = !closesTernary && (
            braceContexts.length === 0 || braceContexts.at(-1)?.statementBody === true
          );
          if (closesTernary) ternaryContexts.pop();
          transition = { ...transition, statementColon };
        }
      }
      pushToken({
        completesModuleDeclaration: transition.closedBrace?.moduleAttributes === true,
        end: index + punctuator.length,
        start: index,
        type: "punctuator",
        value: punctuator,
      }, transition);
      index += punctuator.length;
      if (stopsAtThisArrow) return index;
    }
    return index;
  };

  scanRange(0, false, false, null, stopAfterTopLevelArrow);
  return tokens;
};

const moduleSpecifierTokens = (text, options) => {
  const tokens = javascriptTokens(text, options);
  const typescript = options?.typescript === true;
  const specifiers = [];
  const seen = new Set();
  const add = (token) => {
    if (["string", "template"].includes(token?.type) && !seen.has(token.start)) {
      seen.add(token.start);
      specifiers.push(token);
    }
  };
  const isMemberName = (index) =>
    ["#", ".", "?."].includes(tokens[index - 1]?.value);
  const afterTransparentType = (start) => {
    const delimiters = [];
    const matching = new Map([[">", "<"], [")", "("], ["]", "["], ["}", "{"]]);
    let segmentDepth = 0;
    for (let cursor = start; cursor < tokens.length; cursor += 1) {
      const token = tokens[cursor];
      if (token.type === "segment") {
        if (token.value === "<segment-start>") segmentDepth += 1;
        else if (token.value === "<segment-end>") segmentDepth = Math.max(0, segmentDepth - 1);
        continue;
      }
      if (segmentDepth > 0) continue;
      if (token.type === "punctuator" && delimiters.length === 0 && [")", ","].includes(token.value)) {
        return cursor;
      }
      if (token.type !== "punctuator") continue;
      if (["<", "(", "[", "{"].includes(token.value)) {
        delimiters.push(token.value);
        continue;
      }
      if ([">>", ">>>"].includes(token.value)) {
        for (let count = 0; count < token.value.length; count += 1) {
          if (delimiters.at(-1) !== "<") return null;
          delimiters.pop();
        }
        continue;
      }
      if (matching.has(token.value)) {
        if (delimiters.at(-1) !== matching.get(token.value)) return null;
        delimiters.pop();
      }
    }
    return null;
  };
  const literalCallArgument = (openIndex) => {
    if (tokens[openIndex]?.value !== "(") return null;
    let cursor = openIndex + 1;
    let wrappers = 0;
    while (true) {
      while (tokens[cursor]?.value === "(") {
        wrappers += 1;
        cursor += 1;
      }
      if (typescript && tokens[cursor]?.value === "<") {
        const afterTypes = afterTypeArguments(cursor);
        if (afterTypes === null) return null;
        cursor = afterTypes;
        continue;
      }
      break;
    }
    const literal = tokens[cursor];
    if (!["string", "template"].includes(literal?.type)) return null;
    cursor += 1;
    if (literal.type === "template" && literal.hasExpressions) {
      while (tokens[cursor]?.value === "<segment-start>") {
        let segmentDepth = 0;
        do {
          if (tokens[cursor]?.value === "<segment-start>") segmentDepth += 1;
          else if (tokens[cursor]?.value === "<segment-end>") segmentDepth -= 1;
          cursor += 1;
        } while (cursor < tokens.length && segmentDepth > 0);
        if (segmentDepth !== 0) return null;
      }
    }
    while (true) {
      if (typescript && tokens[cursor]?.value === "!") {
        cursor += 1;
        continue;
      }
      if (
        typescript &&
        tokens[cursor]?.type === "identifier" &&
        ["as", "satisfies"].includes(tokens[cursor].value)
      ) {
        const afterType = afterTransparentType(cursor + 1);
        if (afterType === null) return null;
        cursor = afterType;
        continue;
      }
      if (wrappers > 0 && tokens[cursor]?.value === ")") {
        wrappers -= 1;
        cursor += 1;
        continue;
      }
      break;
    }
    if (wrappers !== 0 || ![")", ","].includes(tokens[cursor]?.value)) return null;
    return literal;
  };
  const afterTypeArguments = (start) => {
    if (!typescript || tokens[start]?.value !== "<") return null;
    const delimiters = [];
    const matching = new Map([[")", "("], ["]", "["], ["}", "{"]]);
    let segmentDepth = 0;
    for (let cursor = start; cursor < tokens.length; cursor += 1) {
      const token = tokens[cursor];
      if (token.type === "segment") {
        if (token.value === "<segment-start>") segmentDepth += 1;
        else if (token.value === "<segment-end>") segmentDepth = Math.max(0, segmentDepth - 1);
        continue;
      }
      if (segmentDepth > 0) continue;
      if (token.type !== "punctuator") continue;
      if (["<", "(", "[", "{"].includes(token.value)) {
        delimiters.push(token.value);
        continue;
      }
      if ([">", ">>", ">>>"].includes(token.value)) {
        for (let count = 0; count < token.value.length; count += 1) {
          if (delimiters.at(-1) !== "<") return null;
          delimiters.pop();
          if (delimiters.length === 0) {
            return count === token.value.length - 1 ? cursor + 1 : null;
          }
        }
        continue;
      }
      if (matching.has(token.value)) {
        if (delimiters.at(-1) !== matching.get(token.value)) return null;
        delimiters.pop();
        continue;
      }
      if (token.value === ";" && delimiters.length === 1) return null;
    }
    return null;
  };
  const callOpenIndex = (start) => {
    let cursor = start;
    while (typescript && tokens[cursor]?.value === "!") cursor += 1;
    let optionalCall = false;
    if (tokens[cursor]?.value === "?.") {
      optionalCall = true;
      cursor += 1;
    }
    if (typescript && tokens[cursor]?.value === "<") {
      const afterTypes = afterTypeArguments(cursor);
      if (afterTypes === null) return null;
      cursor = afterTypes;
    }
    while (typescript && tokens[cursor]?.value === "!") cursor += 1;
    if (!optionalCall && tokens[cursor]?.value === "?.") {
      optionalCall = true;
      cursor += 1;
      if (typescript && tokens[cursor]?.value === "<") {
        const afterTypes = afterTypeArguments(cursor);
        if (afterTypes === null) return null;
        cursor = afterTypes;
      }
      while (typescript && tokens[cursor]?.value === "!") cursor += 1;
    }
    return tokens[cursor]?.value === "(" ? cursor : null;
  };
  const wrappedRequireCallOpenIndex = (requireIndex) => {
    const prefixAssertionOpen = (expressionStart) => {
      if (!typescript || ![">", ">>", ">>>"].includes(tokens[expressionStart - 1]?.value)) {
        return null;
      }
      for (let openIndex = expressionStart - 2; openIndex >= 0; openIndex -= 1) {
        if (tokens[openIndex]?.value !== "(" || tokens[openIndex + 1]?.value !== "<") continue;
        let cursor = openIndex + 1;
        while (cursor < expressionStart && tokens[cursor]?.value === "<") {
          const afterTypes = afterTypeArguments(cursor);
          if (afterTypes === null || afterTypes <= cursor) break;
          cursor = afterTypes;
        }
        if (cursor === expressionStart) return openIndex;
      }
      return null;
    };
    const wrapperOpenBlocked = (openIndex) => {
      const preceding = tokens[openIndex - 1];
      return Boolean(
        preceding &&
        (
          ["literal", "string", "template"].includes(preceding.type) ||
          ["#", ".", "?.", ")", "]", "}"].includes(preceding.value) ||
          (preceding.type === "identifier" && !regexPrefixKeywords.has(preceding.value))
        )
      );
    };
    const transparentPostfixEnd = (start) => {
      let cursor = start;
      while (true) {
        if (typescript && tokens[cursor]?.value === "!") {
          cursor += 1;
          continue;
        }
        if (typescript && tokens[cursor]?.value === "<") {
          const afterTypes = afterTypeArguments(cursor);
          if (afterTypes === null) return null;
          cursor = afterTypes;
          continue;
        }
        if (
          typescript &&
          tokens[cursor]?.type === "identifier" &&
          ["as", "satisfies"].includes(tokens[cursor].value)
        ) {
          const afterType = afterTransparentType(cursor + 1);
          if (afterType === null) return null;
          cursor = afterType;
          continue;
        }
        break;
      }
      return cursor;
    };

    let expressionStart = requireIndex;
    let expressionEnd = requireIndex + 1;
    let wrapped = false;
    while (true) {
      const openIndex = tokens[expressionStart - 1]?.value === "("
        ? expressionStart - 1
        : prefixAssertionOpen(expressionStart);
      if (openIndex === null || wrapperOpenBlocked(openIndex)) break;
      const closeIndex = transparentPostfixEnd(expressionEnd);
      if (
        tokens[closeIndex]?.value !== ")" ||
        tokens[closeIndex].closedParen?.control
      ) break;
      expressionStart = openIndex;
      expressionEnd = closeIndex + 1;
      wrapped = true;
    }
    return wrapped ? callOpenIndex(expressionEnd) : null;
  };
  const findFrom = (start) => {
    let depth = 0;
    for (let index = start; index < tokens.length; index += 1) {
      const token = tokens[index];
      if (token.type === "segment") return;
      if (token.type === "punctuator" && ["(", "[", "{"].includes(token.value)) depth += 1;
      else if (token.type === "punctuator" && [")", "]", "}"].includes(token.value)) {
        depth = Math.max(0, depth - 1);
      }
      if (depth === 0 && token.type === "identifier" && token.value === "from") {
        if (tokens[index + 1]?.type === "string") {
          add(tokens[index + 1]);
          return;
        }
        continue;
      }
      if (
        depth === 0 &&
        (token.value === ";" ||
          (index > start && token.type === "identifier" && ["import", "export"].includes(token.value)))
      ) return;
    }
  };
  const addExportFrom = (start) => {
    let cursor = start;
    if (
      tokens[cursor]?.type === "identifier" &&
      tokens[cursor].value === "type" &&
      ["*", "{"].includes(tokens[cursor + 1]?.value)
    ) cursor += 1;
    if (tokens[cursor]?.value === "*") {
      cursor += 1;
      if (tokens[cursor]?.type === "identifier" && tokens[cursor].value === "as") cursor += 2;
      if (
        tokens[cursor]?.type === "identifier" &&
        tokens[cursor].value === "from" &&
        tokens[cursor + 1]?.type === "string"
      ) add(tokens[cursor + 1]);
      return;
    }
    if (tokens[cursor]?.value !== "{") return;
    let depth = 1;
    cursor += 1;
    while (cursor < tokens.length && depth > 0) {
      if (tokens[cursor].type === "segment") return;
      if (tokens[cursor].type === "punctuator" && tokens[cursor].value === "{") depth += 1;
      else if (tokens[cursor].type === "punctuator" && tokens[cursor].value === "}") depth -= 1;
      cursor += 1;
    }
    if (
      depth === 0 &&
      tokens[cursor]?.type === "identifier" &&
      tokens[cursor].value === "from" &&
      tokens[cursor + 1]?.type === "string"
    ) add(tokens[cursor + 1]);
  };

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token.type !== "identifier" || isMemberName(index)) continue;
    if (token.value === "import") {
      const next = tokens[index + 1];
      if (next?.type === "segment") continue;
      if (next?.value === ".") continue;
      if (next?.type === "string") add(next);
      else {
        const openIndex = callOpenIndex(index + 1);
        if (openIndex !== null) add(literalCallArgument(openIndex));
        else findFrom(index + 1);
      }
      continue;
    }
    if (token.value === "export") {
      addExportFrom(index + 1);
      continue;
    }
    if (token.value === "require") {
      let cursor = index + 1;
      if (tokens[cursor]?.type === "segment") continue;
      const openIndex = callOpenIndex(cursor) ?? wrappedRequireCallOpenIndex(index);
      if (openIndex !== null) add(literalCallArgument(openIndex));
    }
  }
  return specifiers;
};

if (policy.sourceImportPolicy !== "public-package-api-only") {
  fail(`unrecognized sourceImportPolicy: ${String(policy.sourceImportPolicy)}`);
}

for (const component of policy.components) {
  const componentRoot = resolve(workspaceRoot, component.directory);
  const manifest = JSON.parse(await readFile(resolve(componentRoot, "package.json"), "utf8"));
  const explicitExports = manifest.exports;
  if (
    policy.sourceImportPolicy === "public-package-api-only" &&
    (
      !Object.hasOwn(manifest, "exports") ||
      !(
        typeof explicitExports === "string" ||
        Array.isArray(explicitExports) ||
        (typeof explicitExports === "object" && explicitExports !== null)
      )
    )
  ) fail(`${manifest.name}: public-package-api-only requires an explicit exports boundary`);
  component.version = manifest.version;
  componentByName.set(component.packageName, component);
  componentManifestByName.set(component.packageName, manifest);
  componentExportsByName.set(
    filesystemKey(component.packageName),
    {
      packageName: component.packageName,
      surface: buildExportsSurface(manifest.name, explicitExports),
    },
  );
}

for (const component of policy.components) {
  const componentRoot = resolve(workspaceRoot, component.directory);
  const manifest = componentManifestByName.get(component.packageName);
  for (const field of dependencyFields) {
    for (const [dependency, version] of Object.entries(manifest[field] ?? {})) {
      if (!componentByName.has(dependency)) continue;
      const target = componentByName.get(dependency);
      if (version !== target.version) {
        fail(`${manifest.name}: internal dependency ${dependency} must exactly match ${target.version}`);
      }
      recordInternalPackageEdge(component, target);
    }
  }

  for (const path of await walk(componentRoot)) {
    if (!sourceExtensions.has(extname(path))) continue;
    const text = await readFile(path, "utf8");
    for (const token of moduleSpecifierTokens(text, {
      jsx: [".jsx", ".tsx"].includes(extname(path)),
      moduleGoal: ![".cjs", ".cts"].includes(extname(path)),
      typescript: [".cts", ".mts", ".ts", ".tsx"].includes(extname(path)),
    })) {
      if (!token.terminated) {
        fail(`${relative(repoRoot, path)}: unterminated module specifier cannot be boundary-checked`);
        continue;
      }
      if (token.escaped) {
        fail(`${relative(repoRoot, path)}: escaped module specifier cannot be boundary-checked`);
        continue;
      }
      const specifier = token.value;
      if (typeof specifier !== "string") {
        fail(`${relative(repoRoot, path)}: dynamic template specifier cannot be boundary-checked`);
        continue;
      }
      if (specifier.includes("%")) {
        fail(`${relative(repoRoot, path)}: percent-encoded module specifier cannot be boundary-checked`);
        continue;
      }
      const specifierPath = specifier.split(/[?#]/u, 1)[0];
      if (
        /^file:/iu.test(specifierPath) ||
        (
          /^[A-Za-z][A-Za-z0-9+.-]*:/u.test(specifierPath) &&
          !/^node:/iu.test(specifierPath)
        ) ||
        isAbsolute(specifierPath) ||
        /^[A-Za-z]:[\\/]/u.test(specifierPath) ||
        /^(?:\\\\|\/\/)/u.test(specifierPath)
      ) {
        fail(`${relative(repoRoot, path)}: absolute module specifier is not allowed: ${specifier}`);
        continue;
      }
      const comparisonSpecifierPath = filesystemKey(specifierPath);
      if (/^@epistemic-foundry\/[^/]+\/src(?:\/|$)/.test(comparisonSpecifierPath)) {
        fail(`${relative(repoRoot, path)}: private source import ${specifier}`);
        continue;
      }
      const internalExport = internalPackageExport(specifierPath);
      if (internalExport) {
        if (!internalExport.surface.permits(internalExport.exportKey)) {
          fail(
            `${relative(repoRoot, path)}: ${specifier} is not exported by ` +
            internalExport.packageName,
          );
          continue;
        }
        if (internalExport.packageName !== component.packageName) {
          recordInternalPackageEdge(
            component,
            componentByName.get(internalExport.packageName),
          );
        }
        continue;
      }
      if (!specifierPath.startsWith(".")) continue;
      const resolved = resolve(dirname(path), specifierPath);
      const rel = relative(workspaceRoot, resolved).split(sep).map(filesystemKey);
      const target = componentByDirectory.get(rel[0]);
      if (
        target &&
        filesystemKey(target.directory) !== filesystemKey(component.directory)
      ) {
        fail(
          `${relative(repoRoot, path)}: relative import crosses into ${target.directory}; ` +
          "use its exported package API",
        );
      }
    }
  }
}

const visiting = new Set();
const visited = new Set();
const visit = (name, stack = []) => {
  if (visiting.has(name)) {
    fail(`workspace dependency cycle: ${[...stack, name].join(" -> ")}`);
    return;
  }
  if (visited.has(name)) return;
  visiting.add(name);
  for (const dependency of edges.get(name) ?? []) visit(dependency, [...stack, name]);
  visiting.delete(name);
  visited.add(name);
};
for (const name of edges.keys()) visit(name);

const pythonModuleIdentity = (modulePath) => {
  const withoutExtension = modulePath.slice(0, -".py".length);
  if (withoutExtension === "__init__") return "";
  return withoutExtension.endsWith("/__init__")
    ? withoutExtension.slice(0, -"/__init__".length)
    : withoutExtension;
};

const pythonPolicy = policy.python;
if (pythonPolicy?.duplicateImplementationPolicy !== "forbidden") {
  fail(
    `unrecognized duplicateImplementationPolicy: ${String(pythonPolicy?.duplicateImplementationPolicy)}`,
  );
} else {
  const pythonRoots = [pythonPolicy.runtimeRoot, pythonPolicy.componentRoot];
  const modulesByRoot = [];
  for (const root of pythonRoots) {
    const absolute = resolve(repoRoot, root);
    const modules = new Map();
    if (await pathEntryExists(absolute)) {
      for (const path of await walk(absolute)) {
        if (extname(path) !== ".py") continue;
        const modulePath = relative(absolute, path).split(sep).join("/");
        modules.set(
          pythonModuleIdentity(modulePath),
          relative(repoRoot, path).split(sep).join("/"),
        );
        const text = await readFile(path, "utf8");
        if (/sys\.path\.(?:append|insert)\s*\(/.test(text)) {
          fail(`${relative(repoRoot, path)}: sys.path mutation can bypass component boundaries`);
        }
        if (/['"](?:\.\.\/)+(?:packages|python|src)\//.test(text)) {
          fail(`${relative(repoRoot, path)}: filesystem source import bypass detected`);
        }
      }
    }
    modulesByRoot.push(modules);
  }
  const duplicates = [...modulesByRoot[0].keys()]
    .filter((moduleIdentity) => modulesByRoot[1].has(moduleIdentity))
    .sort((left, right) => left < right ? -1 : left > right ? 1 : 0);
  for (const moduleIdentity of duplicates) {
    fail(
      `python duplicate implementation ${moduleIdentity || "<root package>"} exists at ` +
      `${modulesByRoot[0].get(moduleIdentity)} and ${modulesByRoot[1].get(moduleIdentity)}`,
    );
  }
}

if (failures.length) {
  console.error(JSON.stringify({ check: "forbidden_source_import_check", status: "FAIL", failures }, null, 2));
  process.exit(1);
}

const edgeCount = [...edges.values()].reduce((count, dependencies) => count + dependencies.size, 0);
console.log(JSON.stringify({
  check: "forbidden_source_import_check",
  status: "PASS",
  components: policy.components.length,
  internalPackageEdges: edgeCount,
  policy: policy.sourceImportPolicy,
}, null, 2));
