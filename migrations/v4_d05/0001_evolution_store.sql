-- D05 evolution transactional store: lineage, quality-diversity archive,
-- islands and atomic checkpoints.
--
-- The two invariants this store exists to enforce are enforced by the database
-- itself rather than by the code that calls it.
--
-- EF4-I61 (atomic evolution checkpoints): a safe resume point binds population,
-- archive, islands, bandit, budget, testing ledger and evaluator hash
-- atomically.  Every one of those seven bindings is NOT NULL on the checkpoint
-- row, so a partially bound checkpoint cannot be written at all, and the row is
-- immutable once committed.
--
-- EF4-I49 (protected negative memory): nulls, counterexamples, failed
-- replications, unsafe failures and minority lineages cannot be evicted merely
-- for low fitness.  Protection is a stored property of the archive entry, and
-- eviction runs through a single function that refuses a protected entry no
-- matter what fitness it carries.  There is no runtime DELETE privilege on any
-- table here, so eviction cannot route around that function.
--
-- EF4-I43 (immutable evaluator per run): a run references one content-addressed
-- evaluator bundle, and the checkpoint carries that hash.  Nothing in this
-- store can rewrite it.

BEGIN;

CREATE SCHEMA epistemic_foundry_evolution;
REVOKE ALL ON SCHEMA epistemic_foundry_evolution FROM PUBLIC;

CREATE TABLE epistemic_foundry_evolution.store_metadata (
    key text COLLATE pg_catalog."C" PRIMARY KEY,
    value text COLLATE pg_catalog."C" NOT NULL
);

INSERT INTO epistemic_foundry_evolution.store_metadata (key, value) VALUES
    ('schema_version', '1'),
    ('contract_id', 'epistemic-foundry-postgres-evolution-store/v1'),
    ('identity_collation', 'pg_catalog.C-deterministic'),
    ('sha256_form', 'sha256:<64 lowercase hex>'),
    ('checkpoint_atomicity', 'seven-binding-not-null-immutable'),
    ('protected_memory_policy', 'no-fitness-eviction-of-protected-entries'),
    ('evaluator_binding', 'one-content-addressed-bundle-per-run-immutable'),
    ('runtime_delete_path', 'none');

-- Every content address in this store has one shape.
CREATE DOMAIN epistemic_foundry_evolution.sha256 AS text
    COLLATE pg_catalog."C"
    CHECK (VALUE ~ '^sha256:[0-9a-f]{64}$');

CREATE DOMAIN epistemic_foundry_evolution.identifier AS text
    COLLATE pg_catalog."C"
    CHECK (VALUE <> '' AND length(VALUE) <= 256 AND VALUE !~ '[[:cntrl:]]');

-- ---------------------------------------------------------------------------
-- Runs and their immutable evaluator binding (EF4-I43).
-- ---------------------------------------------------------------------------

CREATE TABLE epistemic_foundry_evolution.evolution_runs (
    run_id epistemic_foundry_evolution.identifier PRIMARY KEY,
    evaluator_bundle_hash epistemic_foundry_evolution.sha256 NOT NULL,
    holdout_manifest_hash epistemic_foundry_evolution.sha256 NOT NULL,
    opened_at timestamp with time zone NOT NULL DEFAULT statement_timestamp()
);

-- ---------------------------------------------------------------------------
-- Lineage: append-only, acyclic by construction, parents must already exist.
-- ---------------------------------------------------------------------------

CREATE TABLE epistemic_foundry_evolution.candidate_lineage (
    candidate_id epistemic_foundry_evolution.identifier PRIMARY KEY,
    run_id epistemic_foundry_evolution.identifier NOT NULL
        REFERENCES epistemic_foundry_evolution.evolution_runs (run_id),
    parent_candidate_id epistemic_foundry_evolution.identifier
        REFERENCES epistemic_foundry_evolution.candidate_lineage (candidate_id),
    generation integer NOT NULL,
    genome_hash epistemic_foundry_evolution.sha256 NOT NULL,
    operator_id epistemic_foundry_evolution.identifier NOT NULL,
    recorded_at timestamp with time zone NOT NULL
        DEFAULT statement_timestamp(),
    CONSTRAINT candidate_lineage_generation_range
        CHECK (generation >= 0),
    CONSTRAINT candidate_lineage_not_its_own_parent
        CHECK (parent_candidate_id IS DISTINCT FROM candidate_id),
    CONSTRAINT candidate_lineage_root_is_generation_zero
        CHECK (
            (parent_candidate_id IS NULL AND generation = 0)
            OR (parent_candidate_id IS NOT NULL AND generation > 0)
        )
);

CREATE INDEX candidate_lineage_run_generation_idx
    ON epistemic_foundry_evolution.candidate_lineage (run_id, generation);

-- ---------------------------------------------------------------------------
-- Islands: a candidate joins at most one island per run (EF4-I50).
-- ---------------------------------------------------------------------------

CREATE TABLE epistemic_foundry_evolution.island_states (
    island_id epistemic_foundry_evolution.identifier PRIMARY KEY,
    run_id epistemic_foundry_evolution.identifier NOT NULL
        REFERENCES epistemic_foundry_evolution.evolution_runs (run_id),
    specialization epistemic_foundry_evolution.identifier NOT NULL,
    state_hash epistemic_foundry_evolution.sha256 NOT NULL,
    updated_at timestamp with time zone NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE epistemic_foundry_evolution.island_membership (
    island_id epistemic_foundry_evolution.identifier NOT NULL
        REFERENCES epistemic_foundry_evolution.island_states (island_id),
    candidate_id epistemic_foundry_evolution.identifier NOT NULL
        REFERENCES epistemic_foundry_evolution.candidate_lineage (candidate_id),
    joined_at timestamp with time zone NOT NULL
        DEFAULT statement_timestamp(),
    CONSTRAINT island_membership_pk PRIMARY KEY (island_id, candidate_id),
    CONSTRAINT island_membership_one_island_per_candidate
        UNIQUE (candidate_id)
);

-- ---------------------------------------------------------------------------
-- Quality-diversity archive with protected negative memory (EF4-I48, I49).
-- ---------------------------------------------------------------------------

CREATE TABLE epistemic_foundry_evolution.epistemic_niches (
    niche_id epistemic_foundry_evolution.identifier PRIMARY KEY,
    run_id epistemic_foundry_evolution.identifier NOT NULL
        REFERENCES epistemic_foundry_evolution.evolution_runs (run_id),
    descriptor_hash epistemic_foundry_evolution.sha256 NOT NULL
);

-- Why an entry may never be evicted for low fitness.  A protected entry
-- carries exactly one reason; an unprotected entry carries none.
CREATE TABLE epistemic_foundry_evolution.protection_reasons (
    reason text COLLATE pg_catalog."C" PRIMARY KEY
);

INSERT INTO epistemic_foundry_evolution.protection_reasons (reason) VALUES
    ('NULL_RESULT'),
    ('COUNTEREXAMPLE'),
    ('FAILED_REPLICATION'),
    ('UNSAFE_FAILURE'),
    ('MINORITY_LINEAGE');

CREATE TABLE epistemic_foundry_evolution.archive_entries (
    entry_id epistemic_foundry_evolution.identifier PRIMARY KEY,
    run_id epistemic_foundry_evolution.identifier NOT NULL
        REFERENCES epistemic_foundry_evolution.evolution_runs (run_id),
    candidate_id epistemic_foundry_evolution.identifier NOT NULL
        REFERENCES epistemic_foundry_evolution.candidate_lineage (candidate_id),
    niche_id epistemic_foundry_evolution.identifier NOT NULL
        REFERENCES epistemic_foundry_evolution.epistemic_niches (niche_id),
    fitness_vector_hash epistemic_foundry_evolution.sha256 NOT NULL,
    combined_score double precision NOT NULL,
    protection_reason text COLLATE pg_catalog."C"
        REFERENCES epistemic_foundry_evolution.protection_reasons (reason),
    evicted_at timestamp with time zone,
    eviction_reason text COLLATE pg_catalog."C",
    recorded_at timestamp with time zone NOT NULL
        DEFAULT statement_timestamp(),
    -- PostgreSQL defines NaN = NaN as true and sorts NaN above every finite
    -- value, so the IEEE self-comparison trick does not reject it here.  The
    -- inequality does: NaN <> NaN is false, which fails the check.
    CONSTRAINT archive_entries_score_is_finite
        CHECK (combined_score <> 'NaN'::double precision
               AND combined_score <> 'Infinity'::double precision
               AND combined_score <> '-Infinity'::double precision),
    -- A combined score orders search; it never promotes (EF4-I45).  Recording
    -- it is allowed; letting it decide protection is not.
    CONSTRAINT archive_entries_protected_never_evicted
        CHECK (protection_reason IS NULL OR evicted_at IS NULL),
    CONSTRAINT archive_entries_eviction_is_reasoned
        CHECK ((evicted_at IS NULL) = (eviction_reason IS NULL)),
    CONSTRAINT archive_entries_eviction_reason_nonempty
        CHECK (eviction_reason IS NULL OR eviction_reason <> '')
);

CREATE INDEX archive_entries_live_niche_idx
    ON epistemic_foundry_evolution.archive_entries (run_id, niche_id)
    WHERE evicted_at IS NULL;

CREATE INDEX archive_entries_protected_idx
    ON epistemic_foundry_evolution.archive_entries (run_id)
    WHERE protection_reason IS NOT NULL;

-- Eviction is a function, not an UPDATE.  It refuses a protected entry and
-- refuses to un-evict, so protected memory cannot be lost through this path
-- and an eviction cannot be quietly reversed.
CREATE FUNCTION epistemic_foundry_evolution.evict_archive_entry(
    requested_entry_id text,
    requested_reason text
) RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
    stored_protection text;
    stored_evicted timestamp with time zone;
BEGIN
    IF requested_reason IS NULL OR requested_reason = '' THEN
        RAISE EXCEPTION 'eviction requires a reason'
            USING ERRCODE = '23514';
    END IF;

    SELECT protection_reason, evicted_at
      INTO stored_protection, stored_evicted
      FROM epistemic_foundry_evolution.archive_entries
     WHERE entry_id = requested_entry_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'archive entry does not exist'
            USING ERRCODE = '23503';
    END IF;

    IF stored_protection IS NOT NULL THEN
        RAISE EXCEPTION
            'protected archive entry cannot be evicted: %', stored_protection
            USING ERRCODE = '23514';
    END IF;

    IF stored_evicted IS NOT NULL THEN
        RAISE EXCEPTION 'archive entry is already evicted'
            USING ERRCODE = '23505';
    END IF;

    UPDATE epistemic_foundry_evolution.archive_entries
       SET evicted_at = statement_timestamp(),
           eviction_reason = requested_reason
     WHERE entry_id = requested_entry_id;

    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION
    epistemic_foundry_evolution.evict_archive_entry(text, text)
    FROM PUBLIC;

-- An entry's identity, placement and protection are immutable once written.
-- Only the eviction columns may change, and only through the function above.
CREATE FUNCTION epistemic_foundry_evolution.archive_entries_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'archive entries are append-only'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.entry_id IS DISTINCT FROM OLD.entry_id
       OR NEW.run_id IS DISTINCT FROM OLD.run_id
       OR NEW.candidate_id IS DISTINCT FROM OLD.candidate_id
       OR NEW.niche_id IS DISTINCT FROM OLD.niche_id
       OR NEW.fitness_vector_hash IS DISTINCT FROM OLD.fitness_vector_hash
       OR NEW.combined_score IS DISTINCT FROM OLD.combined_score
       OR NEW.protection_reason IS DISTINCT FROM OLD.protection_reason
       OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at THEN
        RAISE EXCEPTION 'archive entry identity and protection are immutable'
            USING ERRCODE = '23514';
    END IF;

    IF OLD.evicted_at IS NOT NULL AND NEW.evicted_at IS NULL THEN
        RAISE EXCEPTION 'an eviction cannot be reversed'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END
$function$;

CREATE TRIGGER archive_entries_guard_trigger
    BEFORE UPDATE OR DELETE ON epistemic_foundry_evolution.archive_entries
    FOR EACH ROW
    EXECUTE FUNCTION epistemic_foundry_evolution.archive_entries_guard();

-- Lineage is append-only too: a rewritten parent would rewrite history.
CREATE FUNCTION epistemic_foundry_evolution.append_only_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME
        USING ERRCODE = '23514';
END
$function$;

CREATE TRIGGER candidate_lineage_append_only_trigger
    BEFORE UPDATE OR DELETE ON epistemic_foundry_evolution.candidate_lineage
    FOR EACH ROW
    EXECUTE FUNCTION epistemic_foundry_evolution.append_only_guard();

CREATE TRIGGER evolution_runs_append_only_trigger
    BEFORE UPDATE OR DELETE ON epistemic_foundry_evolution.evolution_runs
    FOR EACH ROW
    EXECUTE FUNCTION epistemic_foundry_evolution.append_only_guard();

-- ---------------------------------------------------------------------------
-- Atomic checkpoints (EF4-I61).
-- ---------------------------------------------------------------------------

CREATE TABLE epistemic_foundry_evolution.evolution_checkpoints (
    checkpoint_id epistemic_foundry_evolution.identifier PRIMARY KEY,
    run_id epistemic_foundry_evolution.identifier NOT NULL
        REFERENCES epistemic_foundry_evolution.evolution_runs (run_id),
    generation integer NOT NULL,
    -- The seven bindings a safe resume point requires.  Every one is NOT NULL,
    -- so a partially bound checkpoint cannot be written at all.
    population_hash epistemic_foundry_evolution.sha256 NOT NULL,
    archive_hash epistemic_foundry_evolution.sha256 NOT NULL,
    islands_hash epistemic_foundry_evolution.sha256 NOT NULL,
    bandit_state_hash epistemic_foundry_evolution.sha256 NOT NULL,
    budget_state_hash epistemic_foundry_evolution.sha256 NOT NULL,
    testing_ledger_hash epistemic_foundry_evolution.sha256 NOT NULL,
    evaluator_bundle_hash epistemic_foundry_evolution.sha256 NOT NULL,
    checkpoint_hash epistemic_foundry_evolution.sha256 NOT NULL,
    sealed_at timestamp with time zone NOT NULL
        DEFAULT statement_timestamp(),
    CONSTRAINT evolution_checkpoints_generation_range
        CHECK (generation >= 0),
    CONSTRAINT evolution_checkpoints_one_per_generation
        UNIQUE (run_id, generation)
);

CREATE TRIGGER evolution_checkpoints_append_only_trigger
    BEFORE UPDATE OR DELETE
    ON epistemic_foundry_evolution.evolution_checkpoints
    FOR EACH ROW
    EXECUTE FUNCTION epistemic_foundry_evolution.append_only_guard();

-- A checkpoint may bind only the evaluator its own run was opened with
-- (EF4-I43): a resume point cannot silently swap the evaluator.
CREATE FUNCTION epistemic_foundry_evolution.checkpoint_evaluator_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
DECLARE
    run_evaluator text;
BEGIN
    SELECT evaluator_bundle_hash
      INTO run_evaluator
      FROM epistemic_foundry_evolution.evolution_runs
     WHERE run_id = NEW.run_id;

    IF run_evaluator IS DISTINCT FROM NEW.evaluator_bundle_hash THEN
        RAISE EXCEPTION
            'checkpoint evaluator does not match the run evaluator'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END
$function$;

CREATE TRIGGER evolution_checkpoints_evaluator_trigger
    BEFORE INSERT ON epistemic_foundry_evolution.evolution_checkpoints
    FOR EACH ROW
    EXECUTE FUNCTION epistemic_foundry_evolution.checkpoint_evaluator_guard();

-- Sealing a checkpoint is one statement, so a crash cannot leave a partially
-- bound resume point behind.  The function takes all seven bindings or fails.
CREATE FUNCTION epistemic_foundry_evolution.seal_checkpoint(
    requested_checkpoint_id text,
    requested_run_id text,
    requested_generation integer,
    requested_population_hash text,
    requested_archive_hash text,
    requested_islands_hash text,
    requested_bandit_state_hash text,
    requested_budget_state_hash text,
    requested_testing_ledger_hash text,
    requested_evaluator_bundle_hash text,
    requested_checkpoint_hash text
) RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
    INSERT INTO epistemic_foundry_evolution.evolution_checkpoints (
        checkpoint_id,
        run_id,
        generation,
        population_hash,
        archive_hash,
        islands_hash,
        bandit_state_hash,
        budget_state_hash,
        testing_ledger_hash,
        evaluator_bundle_hash,
        checkpoint_hash
    ) VALUES (
        requested_checkpoint_id,
        requested_run_id,
        requested_generation,
        requested_population_hash,
        requested_archive_hash,
        requested_islands_hash,
        requested_bandit_state_hash,
        requested_budget_state_hash,
        requested_testing_ledger_hash,
        requested_evaluator_bundle_hash,
        requested_checkpoint_hash
    );
    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION epistemic_foundry_evolution.seal_checkpoint(
    text, text, integer, text, text, text, text, text, text, text, text
) FROM PUBLIC;

COMMIT;
