import assert from "node:assert/strict";
import test from "node:test";

import {
  EVALUATED_AT,
  byteDirective,
  makeRequest,
  memoryFixture,
  runRecallEvaluation,
  searchedIds,
  selectedIds,
} from "./recall-eval-support.mjs";


test("recall_precision_test: the exact needed fact outranks a partial distractor", () => {
  const needed = memoryFixture({
    memoryId: "MEM-L04-NEEDED",
    searchText: "strawberry irrigation pressure threshold",
    sourceContent: "The approved strawberry irrigation pressure threshold is 22 kPa.",
  });
  const partial = memoryFixture({
    memoryId: "MEM-L04-PARTIAL",
    searchText: "irrigation lunch preference",
    sourceContent: "A private lunch preference was mentioned after irrigation training.",
  });
  const evaluation = runRecallEvaluation({
    fixtures: [partial, needed],
    request: makeRequest({ query: "strawberry irrigation pressure threshold", limit: 1 }),
  });
  assert.deepEqual(searchedIds(evaluation), ["MEM-L04-NEEDED"]);
  assert.deepEqual(selectedIds(evaluation), ["MEM-L04-NEEDED"]);
  assert.equal(evaluation.searchExecution.uncapped_match_count, 2);
});

test("recall_precision_test: all required facts fit the bounded top-k without unrelated context", () => {
  const fixtures = [
    memoryFixture({
      memoryId: "MEM-L04-FACT-A",
      searchText: "strawberry irrigation threshold decision",
      sourceContent: "Decision A fixed the strawberry irrigation threshold at 22 kPa.",
    }),
    memoryFixture({
      memoryId: "MEM-L04-FACT-B",
      searchText: "strawberry irrigation threshold decision boundary",
      sourceContent: "Decision B applies the threshold only during the fruiting boundary.",
    }),
    memoryFixture({
      memoryId: "MEM-L04-DISTRACTOR",
      searchText: "irrigation personal calendar",
      sourceContent: "A private calendar note is unrelated to the research decision.",
    }),
  ];
  const evaluation = runRecallEvaluation({
    fixtures,
    request: makeRequest({ query: "strawberry irrigation threshold decision", limit: 2 }),
  });
  assert.deepEqual(selectedIds(evaluation), ["MEM-L04-FACT-A", "MEM-L04-FACT-B"]);
  assert.equal(evaluation.searchExecution.uncapped_match_count, 3);
  assert.ok(!selectedIds(evaluation).includes("MEM-L04-DISTRACTOR"));
});

test("recall_precision_test: duplicate source memories yield one representative", () => {
  const shared = "The sealed strawberry irrigation threshold is 22 kPa.";
  const fixtures = [
    memoryFixture({
      memoryId: "MEM-L04-DUP-Z",
      searchText: "strawberry irrigation threshold",
      sourceContent: shared,
    }),
    memoryFixture({
      memoryId: "MEM-L04-DUP-A",
      searchText: "strawberry irrigation threshold",
      sourceContent: shared,
    }),
  ];
  const evaluation = runRecallEvaluation({
    fixtures,
    request: makeRequest({ query: "strawberry irrigation threshold", limit: 2 }),
  });
  assert.deepEqual(searchedIds(evaluation), ["MEM-L04-DUP-A", "MEM-L04-DUP-Z"]);
  assert.deepEqual(selectedIds(evaluation), ["MEM-L04-DUP-A"]);
  assert.deepEqual(evaluation.selection.duplicate_exclusions, [
    {
      duplicate_memory_id: "MEM-L04-DUP-Z",
      representative_memory_id: "MEM-L04-DUP-A",
      reason: "DUPLICATE_SOURCE_HASH",
      source_hash: fixtures[0].source_hash,
    },
  ]);
});

test("recall_precision_test: explicit redaction preserves the needed identity without private bytes", () => {
  const fixture = memoryFixture({
    memoryId: "MEM-L04-REDACTED",
    searchText: "strawberry irrigation threshold owner",
    sourceContent: "Threshold 22 kPa; private owner email owner@example.test.",
  });
  const directive = byteDirective({
    directiveId: "RED-L04-EMAIL",
    fixture,
    secret: "owner@example.test",
  });
  const evaluation = runRecallEvaluation({
    fixtures: [fixture],
    request: makeRequest({ query: "strawberry irrigation threshold owner", limit: 1 }),
    directives: [directive],
  });
  assert.deepEqual(selectedIds(evaluation), ["MEM-L04-REDACTED"]);
  assert.equal(evaluation.selection.selected_hits[0].redacted, true);
  assert.equal(
    evaluation.selection.redacted_artifacts[0].content,
    "Threshold 22 kPa; private owner email [REDACTED].",
  );
  assert.ok(!JSON.stringify(evaluation).includes("owner@example.test"));
  assert.equal(evaluation.receipt.redaction_count, 1);
});

test("recall_precision_test: expired high-score memory is excluded before ranking", () => {
  const fixtures = [
    memoryFixture({
      memoryId: "MEM-L04-EXPIRED",
      searchText: "strawberry irrigation threshold decision",
      createdAt: "2024-01-01T00:00:00.000Z",
    }),
    memoryFixture({
      memoryId: "MEM-L04-CURRENT",
      searchText: "strawberry irrigation threshold decision",
      createdAt: "2026-07-01T00:00:00.000Z",
    }),
  ];
  const evaluation = runRecallEvaluation({
    fixtures,
    request: makeRequest({ query: "strawberry irrigation threshold decision", limit: 2 }),
  });
  assert.deepEqual(selectedIds(evaluation), ["MEM-L04-CURRENT"]);
  assert.deepEqual(evaluation.searchExecution.policy_excluded_memory_ids, ["MEM-L04-EXPIRED"]);
});

test("recall_precision_test: a completed zero-result search remains SEARCHED_NONE", () => {
  const evaluation = runRecallEvaluation({
    fixtures: [
      memoryFixture({ memoryId: "MEM-L04-NOMATCH", searchText: "unrelated context only" }),
    ],
    request: makeRequest({ query: "strawberry irrigation threshold", limit: 3 }),
  });
  assert.equal(evaluation.searchExecution.status, "SEARCHED_NONE");
  assert.deepEqual(selectedIds(evaluation), []);
  assert.deepEqual(evaluation.receipt.hits, []);
  assert.deepEqual(evaluation.receipt.searched_classes, ["WORKSPACE"]);
});

test("recall_precision_test: Unicode NFKC equivalents recover the same fact", () => {
  const evaluation = runRecallEvaluation({
    fixtures: [
      memoryFixture({
        memoryId: "MEM-L04-NFKC",
        searchText: "ＳＴＲＡＷＢＥＲＲＹ irrigation threshold",
      }),
    ],
    request: makeRequest({ query: "strawberry irrigation threshold", limit: 1 }),
  });
  assert.deepEqual(selectedIds(evaluation), ["MEM-L04-NFKC"]);
  assert.equal(evaluation.searchExecution.hits[0].score, 1);
});

test("recall_precision_test: input permutation leaves selection and receipt identities stable", () => {
  const fixtures = [
    memoryFixture({ memoryId: "MEM-L04-PERM-A", searchText: "prior scope decision" }),
    memoryFixture({ memoryId: "MEM-L04-PERM-B", searchText: "prior scope decision boundary" }),
    memoryFixture({ memoryId: "MEM-L04-PERM-C", searchText: "unrelated note" }),
  ];
  const request = makeRequest({ query: "prior scope decision", limit: 2 });
  const first = runRecallEvaluation({ fixtures, request });
  const second = runRecallEvaluation({ fixtures: [...fixtures].reverse(), request });
  assert.deepEqual(selectedIds(second), selectedIds(first));
  assert.equal(second.selection.selection_hash, first.selection.selection_hash);
  assert.equal(second.receipt.receipt_id, first.receipt.receipt_id);
  assert.equal(second.receipt.result_hash, first.receipt.result_hash);
});

test("recall_precision_test: receipt is bound to the selected post-L03 subset", () => {
  const fixtures = [
    memoryFixture({ memoryId: "MEM-L04-BOUND-A", searchText: "prior scope decision" }),
    memoryFixture({ memoryId: "MEM-L04-BOUND-B", searchText: "prior scope decision" }),
  ];
  const evaluation = runRecallEvaluation({
    fixtures,
    request: makeRequest({ query: "prior scope decision", limit: 1 }),
  });
  assert.deepEqual(evaluation.receipt.hits, evaluation.selection.selected_hits);
  assert.equal(evaluation.receipt.retrieved_at, EVALUATED_AT);
  assert.match(evaluation.receipt.receipt_id, /^MRR-[0-9a-f]{64}$/u);
  assert.match(evaluation.receipt.result_hash, /^sha256:[0-9a-f]{64}$/u);
});

test("recall_precision_test: selected output carries provenance but no raw search text", () => {
  const privateText = "strawberry irrigation threshold private diary detail";
  const evaluation = runRecallEvaluation({
    fixtures: [
      memoryFixture({
        memoryId: "MEM-L04-PROVENANCE",
        searchText: "strawberry irrigation threshold",
        sourceContent: privateText,
      }),
    ],
    request: makeRequest({ query: "strawberry irrigation threshold", limit: 1 }),
  });
  assert.deepEqual(Object.keys(evaluation.receipt.hits[0]), [
    "class",
    "memory_id",
    "redacted",
    "score",
    "source_hash",
  ]);
  assert.ok(!JSON.stringify(evaluation.receipt).includes(privateText));
  assert.match(evaluation.receipt.hits[0].source_hash, /^sha256:[0-9a-f]{64}$/u);
});

