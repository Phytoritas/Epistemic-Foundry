# Architecture Diagrams

## 1. Product loop

```mermaid
flowchart TD
    U[Human Researcher] --> I[InsightCard]
    I --> V{Schema + falsifier valid?}
    V -- no --> INBOX[Inbox / reformulation]
    V -- yes --> COV[Coverage Cube]
    COV --> RET[Multi-lane retrieval]
    RET --> EP[Evidence Pack]
    EP --> AEP[Asymmetric Evidence Parliament]
    AEP --> G{Deterministic gates}
    G -- block --> GAP[Underdetermined / rejected / method veto]
    G -- pass --> AT[Independent attestation]
    AT --> HP[Hypothesis Passport]
    HP --> ELIG{Registered validation target eligible?}
    ELIG -- no --> EXP[Measurement or experiment ticket]
    ELIG -- yes --> PLAN[Preregistered validation plan]
    PLAN --> EXEC[Typed validation execution]
    EXEC --> REC[Reconciliation]
    EXP --> REC
    REC --> E[New Evidence revision]
    E --> COV
```

## 2. Four-Graph

```mermaid
flowchart LR
    subgraph EG[E-Graph — Evidence]
      P[PaperVersion] --> S[SourceSpan]
      S --> C[Claim]
      C --> EV[Evidence]
      EV --> M[Method/Experiment]
    end

    subgraph RG[R-Graph — Reasoning]
      H[Hypothesis] --> PR[Prediction]
      H --> F[Falsifier]
      H --> ALT[Alternative]
      H --> MECH[Mechanism]
    end

    subgraph DG[D-Graph — Deliberation]
      B[Blind Brief] --> O[Objection]
      O --> MR[Minority Report]
      MR --> ADJ[Adjudication]
    end

    subgraph XG[X-Graph — Validation and Execution]
      XT[Experiment Ticket] --> VP[Validation Plan]
      VT[Validation Target Manifest] --> VP
      VP --> RUN[Run]
      RUN --> RES[Typed Result]
    end

    EV --> H
    H --> B
    ADJ --> XT
    RES --> EV
```

## 3. Ingest and extraction

```mermaid
flowchart TD
    PDF[PDF/Supplement] --> HASH[Hash + registry]
    HASH --> G[GROBID]
    HASH --> D[Docling]
    G --> R[Reconcile structure/layout]
    D --> R
    R --> SPAN[Immutable SourceSpans]
    SPAN --> UNIT[Results + linked caption/table units]
    UNIT --> CAND[High-recall candidates]
    CAND --> ATOM[Atomicizer + ScopeVector]
    ATOM --> MM[Method/measurement mapping]
    MM --> GR[Grounding verifier]
    GR --> DEP[Dataset/publication dependency cluster]
    DEP --> GATE{Extraction release gate}
```

## 4. Evidence retrieval lanes

```mermaid
flowchart LR
    H[Insight revision] --> PLAN[Retrieval Plan]
    PLAN --> L1[Lexical]
    PLAN --> L2[Semantic]
    PLAN --> L3[Citation]
    PLAN --> L4[Entity/Variable]
    PLAN --> L5[Mechanism]
    PLAN --> L6[Counter]
    PLAN --> L7[Null]
    PLAN --> L8[Boundary]
    PLAN --> L9[Method]
    PLAN --> L10[Temporal]
    PLAN --> L11[External novelty]
    L1 & L2 & L3 & L4 & L5 & L6 & L7 & L8 & L9 & L10 & L11 --> REDUCE[Deterministic normalize/dedupe/cluster]
    REDUCE --> PACK[Evidence Pack + unsearched scopes]
```

## 5. Parliament

```mermaid
flowchart TD
    EP[Evidence Pack] --> ACL[Role-specific evidence ACL]
    ACL --> DEF[Defender]
    ACL --> PRO[Prosecutor]
    ACL --> MET[Method Auditor]
    ACL --> SCP[Scope Auditor]
    ACL --> IND[Inductivist]
    ACL --> DED[Deductivist]
    ACL --> CAU[Causal Auditor]
    ACL --> NOV[Novelty Examiner]
    DEF & PRO & MET & SCP & IND & DED & CAU --> X[Cross-examination]
    X --> ABD[Abductive moderator]
    ABD --> MR[Minority Reporter]
    NOV --> DG[Deterministic gates]
    MR --> DG
    MET -->|veto| DG
    DG --> J[Judge]
    J --> AT[Independent attestor]
    AT --> HP[Hypothesis Passport]
```

## 6. Development graph

```mermaid
flowchart TD
    SPEC[Specification freeze] --> READY[Ready-node calculation]
    READY --> M1[Maker WP-A]
    READY --> M2[Maker WP-B]
    READY --> M3[Maker WP-C]
    M1 --> R1[Independent review]
    M2 --> R2[Independent review]
    M3 --> R3[Independent review]
    R1 & R2 & R3 --> IG[Integration gate]
    IG --> CP[Approved checkpoint]
    CP --> READY2[Next dependency layer]
```

## 7. Update and reassessment

```mermaid
flowchart LR
    U[Source / policy / schema update] --> IR[UpdateImpactReport]
    IR --> ST[Mark downstream stale]
    ST --> RP[Reassessment plan]
    RP --> ING[Targeted ingest]
    ING --> CL[Targeted Claim Forge]
    CL --> RET[Targeted retrieval]
    RET --> PAR[New Parliament run]
    PAR --> DELTA[Decision delta]
    DELTA --> SUP[Supersession events]
    SUP --> N[Notifications]
```

## 8. Release assurance

```mermaid
flowchart TD
    SNAP[Frozen evaluation snapshot] --> S[Schema/workflow validation]
    SNAP --> A[144-lens audit]
    SNAP --> G[Gold/adversarial/temporal tests]
    SNAP --> C[Calibration/ablation]
    SNAP --> R[Recovery/scale/security]
    S & A & G & C & R --> B[Release evidence bundle]
    B --> AT[Independent release attestation]
    AT --> M[Final-byte PackageManifest]
    M --> Z[Deterministic ZIP + SHA-256 + CRC verification]
```
