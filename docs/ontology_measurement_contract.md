# Ontology and Measurement-Compatibility Contract

## 1. Separate entities

- `Concept`: a domain concept
- `LatentConstruct`: an intended but not directly observed state
- `Variable`: a named quantity or category
- `OperationalMeasure`: what was actually recorded or calculated
- `Method`: instrument, protocol, survey, assay, algorithm, or analysis
- `Unit`: original and canonical representation
- `ProxyRelation`: operational measure used as a proxy for a construct
- `Scope`: population, entity, setting, intervention, and time boundaries
- `DomainPack`: versioned specialist semantics layered on the neutral core

Do not merge terms only because their strings are similar.

## 2. Mapping key

A mapping is conditioned on:
```text
raw term + sentence context + method + unit + population/entity + section + DomainPack
```

For example, “engagement” may mean attendance, click activity, dwell time,
task completion, self-report, or a latent construct inferred by a model.

## 3. MeasurementConstruct record

```yaml
construct_id:
latent_construct:
operational_variable:
method_id:
unit_original:
unit_canonical:
temporal_support:
spatial_or_population_support:
calibration_or_validation:
stabilization_or_protocol:
proxy_status:
known_limitations:
source_spans:
domain_pack_id:
```

## 4. Compatibility classes

- `DIRECT`: same construct with compatible method and support
- `COMPATIBLE`: comparable after a declared normalization or bridge
- `PROXY`: association allowed, with a mechanism or causal ceiling
- `NOT_COMPARABLE`: must not be pooled
- `UNKNOWN`: insufficient method information

Compatibility is claim-edge-specific. A method may be valid for one claim and
invalid for a broader claim.

## 5. Promotion ceilings

Examples:
- a one-time self-report supports reported state at that time, not sustained behavior
- a benchmark score supports performance on that benchmark, not deployment robustness
- an administrative proxy supports a proxy-defined outcome, not necessarily the latent construct
- an analysis-pipeline state is computed, not directly observed
- a formal proof establishes entailment under its premises, not empirical truth of those premises
- a simulation result supports model compatibility, not empirical confirmation

The Method Auditor records the highest permitted promotion level.

## 6. Unit and representation normalization

Store:
- exact reported value or label
- parsed value
- original representation
- canonical value or category
- transformation and version
- uncertainty transformation
- lossiness warning

Never discard the original representation. Dimensional or construct incompatibility
is a hard error when quantitative pooling is attempted.

## 7. Scope overlap

Core dimensions:
- domain
- population and entity
- unit of analysis
- setting, geography, jurisdiction, and language
- lifecycle stage
- intervention or exposure
- comparator
- spatial and temporal scale
- measurement time
- method and construct
- pinned domain-extension keys

A true contradiction needs enough overlap in all material dimensions. Missing fields
lower confidence; they do not prove identity.

## 8. DomainPack boundary

The core ScopeVector is intentionally stable. A DomainPack may add:
- ontology mappings
- controlled vocabularies
- unit registries
- method catalogs
- coverage axes
- retrieval lexicons
- validation-adapter references

A DomainPack must not change core runtime authority, evidence status, gate semantics,
or provenance requirements.

## 9. Human approval

High-frequency or high-impact mappings enter a review queue. Human approval is
versioned and propagates through dependency analysis; it does not rewrite historical
run manifests.
