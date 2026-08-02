/**
 * M03 deterministic query personalization.
 *
 * Query relevance is a bounded lexical projection over validated M01 entity
 * fields. It never imports, emits, or derives baseline centrality, risk, or
 * blast-radius values. Semantic scoring is explicitly null until a separately
 * qualified semantic scorer contributes a distinct artifact.
 */

import {
  validateWorkspaceEdgeExtraction,
  validateWorkspaceInventory,
} from "../../inventory/index.mjs";
import {
  SHA256_PATTERN,
  assertUniqueStrings,
  canonicalClone,
  canonicalizeQueryRankingJson,
  compareUtf8,
  fail,
  readDataProperty,
  requirePlainDataObject,
  requireText,
  roundedScore,
  sha256CanonicalJson,
} from "./query-ranking-common.mjs";

export const QUERY_PERSONALIZATION_VERSION = "4.0.0-m03.1";
export const QUERY_PERSONALIZATION_ALGORITHM =
  "DETERMINISTIC_FIELD_WEIGHTED_TOKEN_OVERLAP";

export const QUERY_FIELD_WEIGHTS = Object.freeze({
  label: 4,
  aliases: 4,
  path: 3,
  locator: 2,
  owner: 2,
  kind: 1,
});

const INPUT_FIELDS = Object.freeze(["inventory", "extraction", "query"]);
const OUTPUT_FIELDS = Object.freeze([
  "ranking_id",
  "ranking_version",
  "inventory_id",
  "inventory_hash",
  "extraction_id",
  "extraction_hash",
  "query",
  "query_hash",
  "personalization",
  "algorithm",
  "algorithm_inputs",
  "results",
  "ranking_order",
  "ranking_hash",
]);

const normalizeSearchText = (value) =>
  value
    .toLowerCase()
    .replace(/[^\p{L}\p{N}_]+/gu, " ")
    .trim()
    .replace(/\s+/gu, " ");

const tokenize = (value) => {
  const matches = normalizeSearchText(value).match(/[\p{L}\p{N}_]+/gu) ?? [];
  const unique = [...new Set(matches)].sort(compareUtf8);
  return unique;
};

const normalizeQuery = (value) => {
  if (value === null) {
    return canonicalClone({
      query: null,
      query_hash: null,
      normalized_phrase: null,
      tokens: [],
    });
  }
  const query = requireText(value, "query", {
    minLength: 1,
    maxLength: 4096,
    code: "INVALID_QUERY",
  });
  if (query.trim().length === 0) fail("INVALID_QUERY", "query cannot be blank");
  const normalizedPhrase = normalizeSearchText(query);
  const tokens = tokenize(query);
  if (tokens.length === 0) {
    fail("QUERY_HAS_NO_INDEXABLE_TOKENS", "non-null query requires an indexable token");
  }
  assertUniqueStrings(tokens, "query tokens", "DUPLICATE_QUERY_TOKEN");
  return canonicalClone({
    query,
    query_hash: sha256CanonicalJson({ query }),
    normalized_phrase: normalizedPhrase,
    tokens,
  });
};

const searchableFields = (entity) => [
  { field: "label", values: [entity.label] },
  { field: "aliases", values: entity.aliases.map((alias) => alias.value) },
  { field: "path", values: entity.path === null ? [] : [entity.path] },
  { field: "locator", values: entity.locator === null ? [] : [entity.locator] },
  { field: "owner", values: [entity.owner] },
  { field: "kind", values: [entity.kind] },
];

const scoreEntity = (entity, normalizedQuery) => {
  if (normalizedQuery.query === null) {
    return canonicalClone({
      node_id: entity.entity_id,
      query_relevance: 0,
      lexical_score: 0,
      exact_phrase_match: false,
      matched_tokens: [],
      semantic_score: null,
      semantic_status: "NOT_COMPUTED",
    });
  }
  const fields = searchableFields(entity).map((entry) => ({
    field: entry.field,
    normalized_values: entry.values.map(normalizeSearchText),
    token_sets: entry.values.map((value) => new Set(tokenize(value))),
  }));
  const matchedTokens = [];
  let matchedWeight = 0;
  for (const token of normalizedQuery.tokens) {
    let bestWeight = 0;
    for (const field of fields) {
      if (field.token_sets.some((tokens) => tokens.has(token))) {
        bestWeight = Math.max(bestWeight, QUERY_FIELD_WEIGHTS[field.field]);
      }
    }
    if (bestWeight > 0) {
      matchedTokens.push(token);
      matchedWeight += bestWeight;
    }
  }
  const maximumWeight = normalizedQuery.tokens.length * QUERY_FIELD_WEIGHTS.label;
  const lexicalScore = roundedScore(matchedWeight / maximumWeight);
  const exactPhraseMatch = fields.some((field) =>
    field.normalized_values.some(
      (candidate) =>
        candidate.length > 0 && candidate.includes(normalizedQuery.normalized_phrase),
    ),
  );
  const relevance = roundedScore(
    Math.min(1, lexicalScore * 0.9 + (exactPhraseMatch ? 0.1 : 0)),
  );
  return canonicalClone({
    node_id: entity.entity_id,
    query_relevance: relevance,
    lexical_score: lexicalScore,
    exact_phrase_match: exactPhraseMatch,
    matched_tokens: matchedTokens,
    semantic_score: null,
    semantic_status: "NOT_COMPUTED",
  });
};

const algorithmDescriptor = () =>
  canonicalClone({
    name: QUERY_PERSONALIZATION_ALGORITHM,
    implementation_version: QUERY_PERSONALIZATION_VERSION,
    query_normalization: "NFC_UNICODE_LOWERCASE_TOKENIZATION",
    tokenizer: "UNICODE_LETTER_NUMBER_UNDERSCORE",
    field_weights: QUERY_FIELD_WEIGHTS,
    lexical_formula: "0.9 * MAX_FIELD_WEIGHT_TOKEN_COVERAGE",
    exact_phrase_bonus: 0.1,
    semantic_score_policy: "EXPLICIT_NULL_NOT_COMPUTED",
    result_order: "UTF8_NODE_ID",
    ranking_tie_breaker: "UTF8_NODE_ID",
  });

const personalizationPreimage = ({ inventory, extraction, normalizedQuery }) => {
  const results = inventory.entities.map((entity) => scoreEntity(entity, normalizedQuery));
  const rankingOrder = [...results]
    .sort(
      (left, right) =>
        right.query_relevance - left.query_relevance ||
        compareUtf8(left.node_id, right.node_id),
    )
    .map((row) => row.node_id);
  const unresolvedEdgeIds = extraction.unresolved_edges
    .map((edge) => edge.edge_id)
    .sort(compareUtf8);
  return canonicalClone({
    ranking_version: QUERY_PERSONALIZATION_VERSION,
    inventory_id: inventory.inventory_id,
    inventory_hash: inventory.inventory_hash,
    extraction_id: extraction.extraction_id,
    extraction_hash: extraction.extraction_hash,
    query: normalizedQuery.query,
    query_hash: normalizedQuery.query_hash,
    personalization:
      normalizedQuery.query === null ? null : QUERY_PERSONALIZATION_ALGORITHM,
    algorithm: algorithmDescriptor(),
    algorithm_inputs: {
      node_count: inventory.entities.length,
      query_tokens: normalizedQuery.tokens,
      query_token_count: normalizedQuery.tokens.length,
      searchable_fields: Object.keys(QUERY_FIELD_WEIGHTS),
      unresolved_edge_count: unresolvedEdgeIds.length,
      excluded_unresolved_edge_ids: unresolvedEdgeIds,
    },
    results,
    ranking_order: rankingOrder,
  });
};

export const computeQueryPersonalization = (candidate) => {
  const input = requirePlainDataObject(
    candidate,
    "QueryPersonalizationInput",
    INPUT_FIELDS,
    "INVALID_QUERY_PERSONALIZATION_INPUT",
  );
  const inventory = validateWorkspaceInventory(readDataProperty(input, "inventory"));
  const extraction = validateWorkspaceEdgeExtraction(
    readDataProperty(input, "extraction"),
    inventory,
  );
  const normalizedQuery = normalizeQuery(readDataProperty(input, "query"));
  const preimage = personalizationPreimage({ inventory, extraction, normalizedQuery });
  const rankingHash = sha256CanonicalJson(preimage);
  return canonicalClone({
    ranking_id: `WQUERY-${rankingHash.slice("sha256:".length)}`,
    ...preimage,
    ranking_hash: rankingHash,
  });
};

export const validateQueryPersonalization = (
  candidate,
  inventoryCandidate,
  extractionCandidate,
) => {
  const output = requirePlainDataObject(
    candidate,
    "QueryPersonalization",
    OUTPUT_FIELDS,
    "INVALID_QUERY_PERSONALIZATION",
  );
  const rebuilt = computeQueryPersonalization({
    inventory: inventoryCandidate,
    extraction: extractionCandidate,
    query: readDataProperty(output, "query"),
  });
  const observedHash = readDataProperty(output, "ranking_hash");
  if (typeof observedHash !== "string" || !SHA256_PATTERN.test(observedHash)) {
    fail(
      "INVALID_QUERY_PERSONALIZATION_HASH",
      "ranking_hash must be sha256:<64 lowercase hex>",
    );
  }
  if (observedHash !== rebuilt.ranking_hash) {
    fail("QUERY_PERSONALIZATION_HASH_MISMATCH", "ranking_hash does not bind the result", {
      expected: rebuilt.ranking_hash,
      observed: observedHash,
    });
  }
  if (readDataProperty(output, "ranking_id") !== rebuilt.ranking_id) {
    fail("QUERY_PERSONALIZATION_ID_MISMATCH", "ranking_id does not bind ranking_hash");
  }
  if (canonicalizeQueryRankingJson(output) !== canonicalizeQueryRankingJson(rebuilt)) {
    fail(
      "QUERY_PERSONALIZATION_REBUILD_MISMATCH",
      "query personalization differs from its canonical rebuild",
    );
  }
  return rebuilt;
};

export const computeQueryPersonalizationHash = (candidate, inventory, extraction) =>
  validateQueryPersonalization(candidate, inventory, extraction).ranking_hash;
