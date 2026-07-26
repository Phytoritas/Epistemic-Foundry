# Retrieval, Ranking, and Evidence-Pack Contract

## 1. Goal

Retrieval optimizes **decision coverage**, not generic semantic similarity. It must find support, refutation, nulls, boundaries, methods, and prior art.

## 2. Query compilation

From InsightCard generate:
- canonical proposition
- synonyms/ontology terms
- relation direction
- reversed/negated relation
- null/no-effect language
- scope ranges and neighboring scopes
- methods and measurement constructs
- mechanism chain edges
- citation seeds
- date/version/correction queries

Queries and hashes are retained in the retrieval manifest.

## 3. Lanes

Required lanes are configured in `config/retrieval_policy.example.yaml`. Each lane returns:
- candidate ID
- lane
- lexical/semantic/graph score
- matched terms/edges
- scope estimate
- retrieval explanation
- source snapshot/version

## 4. Fusion

Candidate generation may use Reciprocal Rank Fusion:

```text
RRF(d) = Σ_l 1 / (k + rank_l(d))
```

Then compute transparent features:
- scope overlap
- relation-direction match
- directness/evidence layer
- method compatibility
- dependency cluster novelty
- publication/version status
- extraction/grounding confidence

Search priority may be a configured linear or learned reranker, but the final scientific verdict never uses this scalar as evidence strength.

## 5. Dependency-adjusted diversity

Selection objective favors new independent clusters:

```text
marginal_value(d) =
  relevance(d)
  + λ_scope · scope_match(d)
  + λ_role · missing_role_gain(d)
  + λ_cluster · new_cluster(d)
  - λ_dup · redundancy(d, selected)
```

A second paper from the same experiment can add detail but not an independent replication count.

## 6. Scope overlap

Per dimension classify:
- exact
- overlapping
- adjacent/extrapolated
- disjoint
- unknown

Overall scope match is a vector and a policy-derived category, not only a cosine score. Unknown does not equal match.

## 7. Quotas

Evidence Pack is stratified:
- direct support 2–4
- counter 2–4
- null 1–3
- boundary 2–3
- method 1–2
- alternatives/prior art as needed

Quotas are targets, not permission to invent. Empty lane must be `searched-none-found` or `unsearched`, with search record.

## 8. Full-text activation

Tier-0 metadata can identify candidates. Before evidence promotion:
- inspect exact full-text source span
- run grounding verification
- normalize scope/method
- resolve version/dependency

Abstract-only evidence is labeled accordingly and cannot masquerade as direct measurement.

## 9. External novelty

Order:
1. local corpus
2. authoritative bibliographic indexes
3. preprint indexes
4. broader discovery tools

Output:
- `PRIOR_ART_FOUND`
- `NOT_FOUND_WITHIN_SEARCH_SCOPE`
- `NOT_ASSESSED`

Never output absolute “novel” based on a bounded search.

## 10. Evaluation

Per lane and fused:
- Recall@k
- nDCG
- role recall
- cluster diversity
- scope precision
- null/counter recall
- evidence-pack completeness
- cost/latency

Reranking is accepted only if it improves the registered decision metrics, not merely semantic benchmark scores.
