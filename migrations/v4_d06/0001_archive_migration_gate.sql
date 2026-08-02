-- D06 archive migration, crash recovery and atomic checkpoint integration gate.
--
-- This migration applies ON TOP of migrations/v4_d05/0001_evolution_store.sql
-- and adds only what the integration gate needs that D05 does not already
-- enforce.  D05 is not edited, relaxed or re-declared here: its domains, its
-- append-only guard, its seven NOT NULL checkpoint bindings, its evaluator
-- guard and its eviction function are reused as they stand.
--
-- Three gaps remain after D05, and each one gets exactly one mechanism.
--
-- 1. Nothing records which migrations this database has seen.  A resume path
--    that cannot name the schema it is resuming into is guessing, so this
--    migration writes a journal.  The journalled content hash is a digest of
--    the *catalog inventory* of a schema: its columns, defaults, NOT
--    NULLs, constraints, triggers and function bodies, rather than of the
--    migration file, because the file is not what the database will
--    execute after someone alters it.  A weakened D05 guard, a dropped
--    NOT NULL or a rewritten eviction function all move the digest, so
--    tampering is detected by re-derivation rather than by trust.  The
--    digest reads no table data, so it is stable across every row the
--    store writes.
--
-- 2. D05 makes a *sealed* checkpoint atomic: all seven bindings are NOT NULL
--    and the row is immutable, so a half-bound resume point cannot exist.
--    What D05 cannot see is the work that happened before the seal.  A crash
--    between "the run persisted candidates" and "the run sealed a
--    checkpoint" leaves committed work that no checkpoint covers, and nothing
--    in D05 remembers that the work was ever started.  So the gate opens a
--    checkpoint attempt in its own committed transaction *before* the work
--    begins.  The open attempt is the crash marker: it survives precisely
--    because it was committed separately from the work it guards, and an
--    aborted transaction can therefore never erase the evidence that the
--    attempt existed.  Recovery reads epistemic_foundry_recovery.
--    pending_recovery and finds every attempt that was never closed.
--
-- 3. A checkpoint sealed outside that bookkeeping would make the marker
--    advisory, so the gate is enforced by the database: a BEFORE INSERT
--    trigger on D05's checkpoint table refuses any seal that has no open
--    attempt for its run and generation.  This is a tightening of D05, never
--    a relaxation: every D05 constraint still fires first and its messages
--    are unchanged.
--
-- Counts must reconcile before a resume point is declared safe (E05).  The
-- store can only reconcile what the store holds, so the attempt declares the
-- candidate count the generation is expected to have persisted, and closing
-- the attempt refuses unless the lineage rows actually present for that run
-- and generation match it exactly.  The wider proposed/evaluated/cancelled/
-- rejected reconciliation belongs to E05's engine and is not restated here.
--
-- Re-application is REFUSED, not made idempotent.  A migration that silently
-- no-ops on a second run cannot distinguish "already applied" from "applied
-- to the wrong database", and the journal it would leave behind would be a
-- claim rather than a record.  The refusal happens in a preflight block
-- before any DDL, inside the same single transaction, so a refused re-apply
-- changes nothing at all.

BEGIN;

-- Fail closed before touching anything: the gate has one prerequisite and one
-- forbidden state, and both are checked against the catalog rather than
-- assumed from the caller's intent.
DO $preflight$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace
         WHERE nspname = 'epistemic_foundry_evolution'
    ) THEN
        RAISE EXCEPTION
            'the D05 evolution store is absent: apply '
            'migrations/v4_d05/0001_evolution_store.sql before this gate'
            USING ERRCODE = '3F000';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace
         WHERE nspname = 'epistemic_foundry_recovery'
    ) THEN
        RAISE EXCEPTION
            'migration v4_d06/0001_archive_migration_gate is already applied '
            'to this database'
            USING ERRCODE = '42P06';
    END IF;
END
$preflight$;

-- The gate keeps its own schema.  D05's schema declares an exact object set
-- that its sealed acceptance gate asserts; adding bookkeeping tables inside it
-- would rewrite that surface.  Cross-schema foreign keys bind the two without
-- either one redefining the other.
CREATE SCHEMA epistemic_foundry_recovery;
REVOKE ALL ON SCHEMA epistemic_foundry_recovery FROM PUBLIC;

CREATE TABLE epistemic_foundry_recovery.gate_metadata (
    key text COLLATE pg_catalog."C" PRIMARY KEY,
    value text COLLATE pg_catalog."C" NOT NULL
);

INSERT INTO epistemic_foundry_recovery.gate_metadata (key, value) VALUES
    ('schema_version', '1'),
    ('contract_id', 'epistemic-foundry-postgres-recovery-gate/v1'),
    ('applies_on_top_of', 'epistemic-foundry-postgres-evolution-store/v1'),
    ('reapply_policy', 'refuse-before-any-ddl'),
    ('journal_digest_form', 'catalog-inventory-sha256'),
    ('checkpoint_seal_path', 'open-attempt-then-seal-and-close'),
    ('crash_marker', 'checkpoint_attempts-with-null-closed_at'),
    ('count_reconciliation', 'expected-equals-persisted-lineage-at-generation');

-- ---------------------------------------------------------------------------
-- The migration journal.
-- ---------------------------------------------------------------------------

-- Content addresses and identifiers are D05's domains, reused rather than
-- re-declared: a second definition of the same shape is a second thing to
-- weaken.
CREATE TABLE epistemic_foundry_recovery.migration_journal (
    migration_id epistemic_foundry_evolution.identifier PRIMARY KEY,
    digest_scope epistemic_foundry_evolution.identifier NOT NULL,
    content_hash epistemic_foundry_evolution.sha256 NOT NULL,
    applied_at timestamp with time zone NOT NULL
        DEFAULT statement_timestamp()
);

-- A journal that can be edited records nothing.  D05's append-only guard is
-- the same refusal this table needs, so it is reused, not rewritten.
CREATE TRIGGER migration_journal_append_only_trigger
    BEFORE UPDATE OR DELETE ON epistemic_foundry_recovery.migration_journal
    FOR EACH ROW
    EXECUTE FUNCTION epistemic_foundry_evolution.append_only_guard();

-- The digest reads catalog structure only, never table contents, so it does
-- not move when the store writes rows, and it does move when someone changes
-- what the store is allowed to write.  Function bodies are included, because a
-- guard that has been redefined to return early is exactly the tampering this
-- is here to catch.
CREATE FUNCTION epistemic_foundry_recovery.schema_digest(target_schema text)
RETURNS epistemic_foundry_evolution.sha256
LANGUAGE sql
STABLE
SET search_path = pg_catalog
AS $function$
    WITH relation_columns AS (
        SELECT coalesce(string_agg(
                   c.relname || '.' || a.attname
                   || ' type=' || pg_catalog.format_type(a.atttypid,
                                                         a.atttypmod)
                   || ' notnull=' || a.attnotnull::text
                   || ' default=' || coalesce(
                          pg_catalog.pg_get_expr(d.adbin, d.adrelid), ''),
                   E'\n'
                   ORDER BY c.relname COLLATE "C", a.attname COLLATE "C"
               ), '') AS body
          FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
          LEFT JOIN pg_catalog.pg_attrdef d
                 ON d.adrelid = c.oid AND d.adnum = a.attnum
         WHERE n.nspname = target_schema
           AND c.relkind IN ('r', 'v')
           AND a.attnum > 0
           AND NOT a.attisdropped
    ),
    declared_constraints AS (
        SELECT coalesce(string_agg(
                   con.conname || ' '
                   || pg_catalog.pg_get_constraintdef(con.oid),
                   E'\n' ORDER BY con.conname COLLATE "C"
               ), '') AS body
          FROM pg_catalog.pg_constraint con
          JOIN pg_catalog.pg_namespace n ON n.oid = con.connamespace
         WHERE n.nspname = target_schema
    ),
    declared_triggers AS (
        SELECT coalesce(string_agg(
                   tg.tgname || ' ' || pg_catalog.pg_get_triggerdef(tg.oid),
                   E'\n' ORDER BY tg.tgname COLLATE "C"
               ), '') AS body
          FROM pg_catalog.pg_trigger tg
          JOIN pg_catalog.pg_class c ON c.oid = tg.tgrelid
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = target_schema AND NOT tg.tgisinternal
    ),
    declared_routines AS (
        SELECT coalesce(string_agg(
                   pg_catalog.pg_get_functiondef(p.oid),
                   E'\n'
                   ORDER BY p.oid::regprocedure::text COLLATE "C"
               ), '') AS body
          FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = target_schema AND p.prokind = 'f'
    )
    SELECT ('sha256:' || pg_catalog.encode(
                pg_catalog.sha256(pg_catalog.convert_to(
                    relation_columns.body || E'\n-- constraints --\n'
                    || declared_constraints.body || E'\n-- triggers --\n'
                    || declared_triggers.body || E'\n-- routines --\n'
                    || declared_routines.body,
                    'UTF8')),
                'hex'))::epistemic_foundry_evolution.sha256
      FROM relation_columns,
           declared_constraints,
           declared_triggers,
           declared_routines;
$function$;

-- Re-derivation, not trust: every journalled hash is recomputed from the live
-- catalog on every call.
CREATE FUNCTION epistemic_foundry_recovery.verify_migration_journal()
RETURNS TABLE (
    journalled_migration_id text,
    journalled_scope text,
    journalled_hash text,
    observed_hash text,
    matches boolean
)
LANGUAGE sql
STABLE
SET search_path = pg_catalog
AS $function$
    SELECT j.migration_id::text,
           j.digest_scope::text,
           j.content_hash::text,
           epistemic_foundry_recovery.schema_digest(j.digest_scope::text)::text,
           j.content_hash::text
               = epistemic_foundry_recovery.schema_digest(
                     j.digest_scope::text)::text
      FROM epistemic_foundry_recovery.migration_journal j
     ORDER BY j.migration_id COLLATE "C";
$function$;

-- The fail-closed form of the same question, for callers that must stop rather
-- than report.
CREATE FUNCTION epistemic_foundry_recovery.require_intact_migration_journal()
RETURNS boolean
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
AS $function$
DECLARE
    drifted text;
BEGIN
    SELECT string_agg(v.journalled_migration_id, ', ')
      INTO drifted
      FROM epistemic_foundry_recovery.verify_migration_journal() v
     WHERE NOT v.matches;

    IF drifted IS NOT NULL THEN
        RAISE EXCEPTION
            'the migration journal no longer describes this database: %',
            drifted
            USING ERRCODE = '23514';
    END IF;

    RETURN true;
END
$function$;

-- ---------------------------------------------------------------------------
-- Crash-recovery bookkeeping.
-- ---------------------------------------------------------------------------

-- An attempt is open while closed_at IS NULL.  That single nullable column is
-- the in-progress flag: it is committed before the guarded work starts, so a
-- crash leaves it behind, and it is cleared only in the same transaction that
-- seals the checkpoint or records why the attempt was given up.
CREATE TABLE epistemic_foundry_recovery.checkpoint_attempts (
    attempt_id epistemic_foundry_evolution.identifier PRIMARY KEY,
    run_id epistemic_foundry_evolution.identifier NOT NULL
        REFERENCES epistemic_foundry_evolution.evolution_runs (run_id),
    generation integer NOT NULL,
    -- What the caller declares this generation will have persisted.  Closing
    -- the attempt reconciles it against the rows that actually exist.
    expected_candidate_count integer NOT NULL,
    opened_at timestamp with time zone NOT NULL
        DEFAULT statement_timestamp(),
    closed_at timestamp with time zone,
    checkpoint_id epistemic_foundry_evolution.identifier
        REFERENCES
            epistemic_foundry_evolution.evolution_checkpoints (checkpoint_id),
    abandon_reason text COLLATE pg_catalog."C",
    CONSTRAINT checkpoint_attempts_generation_range
        CHECK (generation >= 0),
    CONSTRAINT checkpoint_attempts_expected_count_range
        CHECK (expected_candidate_count >= 0),
    -- An attempt is open, or it sealed a checkpoint, or it was abandoned for a
    -- stated reason.  It can never be two of those, and it can never be closed
    -- without saying which.
    CONSTRAINT checkpoint_attempts_closed_exactly_one_way CHECK (
        (closed_at IS NULL
         AND checkpoint_id IS NULL
         AND abandon_reason IS NULL)
        OR (closed_at IS NOT NULL
            AND (checkpoint_id IS NOT NULL) <> (abandon_reason IS NOT NULL))
    ),
    CONSTRAINT checkpoint_attempts_abandon_reason_nonempty
        CHECK (abandon_reason IS NULL OR abandon_reason <> ''),
    -- One checkpoint has one attempt behind it, so a resume point can never
    -- claim two provenances.
    CONSTRAINT checkpoint_attempts_one_attempt_per_checkpoint
        UNIQUE (checkpoint_id)
);

-- Two concurrent attempts on one generation would make the crash marker
-- ambiguous: recovery could not tell which work each one covered.
CREATE UNIQUE INDEX checkpoint_attempts_one_open_per_generation
    ON epistemic_foundry_recovery.checkpoint_attempts (run_id, generation)
    WHERE closed_at IS NULL;

CREATE INDEX checkpoint_attempts_open_idx
    ON epistemic_foundry_recovery.checkpoint_attempts (opened_at)
    WHERE closed_at IS NULL;

-- The crash record is evidence, so it cannot be deleted, rewritten or
-- reopened.  Only the closing columns may ever change, and only once.
CREATE FUNCTION epistemic_foundry_recovery.checkpoint_attempts_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'checkpoint attempts are append-only: a crashed attempt is the '
            'only evidence that the work was started'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.attempt_id IS DISTINCT FROM OLD.attempt_id
       OR NEW.run_id IS DISTINCT FROM OLD.run_id
       OR NEW.generation IS DISTINCT FROM OLD.generation
       OR NEW.expected_candidate_count IS DISTINCT FROM
          OLD.expected_candidate_count
       OR NEW.opened_at IS DISTINCT FROM OLD.opened_at THEN
        RAISE EXCEPTION
            'a checkpoint attempt is immutable once opened'
            USING ERRCODE = '23514';
    END IF;

    IF OLD.closed_at IS NOT NULL THEN
        RAISE EXCEPTION
            'a closed checkpoint attempt cannot be reopened or reclosed'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END
$function$;

CREATE TRIGGER checkpoint_attempts_guard_trigger
    BEFORE UPDATE OR DELETE
    ON epistemic_foundry_recovery.checkpoint_attempts
    FOR EACH ROW
    EXECUTE FUNCTION epistemic_foundry_recovery.checkpoint_attempts_guard();

-- ---------------------------------------------------------------------------
-- The gate over D05's checkpoint table.
-- ---------------------------------------------------------------------------

-- Without this trigger the crash marker would be a convention: a caller could
-- seal a resume point having recorded no attempt, and recovery would never
-- learn that the generation had been worked on at all.  D05's own guards run
-- first (the trigger name sorts after the evaluator guard), so this refusal
-- never masks a D05 refusal.
CREATE FUNCTION epistemic_foundry_recovery.checkpoint_requires_open_attempt()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM epistemic_foundry_recovery.checkpoint_attempts a
         WHERE a.run_id = NEW.run_id
           AND a.generation = NEW.generation
           AND a.closed_at IS NULL
    ) THEN
        RAISE EXCEPTION
            'a checkpoint may only be sealed inside an open recovery '
            'attempt (run %, generation %)', NEW.run_id, NEW.generation
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END
$function$;

CREATE TRIGGER evolution_checkpoints_recovery_gate_trigger
    BEFORE INSERT ON epistemic_foundry_evolution.evolution_checkpoints
    FOR EACH ROW
    EXECUTE FUNCTION
        epistemic_foundry_recovery.checkpoint_requires_open_attempt();

-- ---------------------------------------------------------------------------
-- The three entry points.
-- ---------------------------------------------------------------------------

-- Opening an attempt is a transaction of its own by contract: the caller must
-- commit it before starting the work it guards, or the marker will disappear
-- with the work and recovery will find nothing.
CREATE FUNCTION epistemic_foundry_recovery.open_checkpoint_attempt(
    requested_attempt_id text,
    requested_run_id text,
    requested_generation integer,
    requested_expected_candidate_count integer
) RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM epistemic_foundry_evolution.evolution_checkpoints c
         WHERE c.run_id = requested_run_id
           AND c.generation = requested_generation
    ) THEN
        RAISE EXCEPTION
            'generation % of run % is already sealed and cannot be reopened',
            requested_generation, requested_run_id
            USING ERRCODE = '23505';
    END IF;

    INSERT INTO epistemic_foundry_recovery.checkpoint_attempts (
        attempt_id,
        run_id,
        generation,
        expected_candidate_count
    ) VALUES (
        requested_attempt_id,
        requested_run_id,
        requested_generation,
        requested_expected_candidate_count
    );

    RETURN true;
END
$function$;

-- Sealing and closing are one statement, so the resume point and the record
-- that it closed the attempt cannot come apart.  The run and generation are
-- read from the attempt rather than accepted from the caller: an attempt
-- cannot be used to seal a generation it never covered.
CREATE FUNCTION epistemic_foundry_recovery.seal_and_close_attempt(
    requested_attempt_id text,
    requested_checkpoint_id text,
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
DECLARE
    attempt epistemic_foundry_recovery.checkpoint_attempts%ROWTYPE;
    observed_candidate_count integer;
BEGIN
    SELECT * INTO attempt
      FROM epistemic_foundry_recovery.checkpoint_attempts
     WHERE attempt_id = requested_attempt_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'checkpoint attempt does not exist'
            USING ERRCODE = '23503';
    END IF;

    IF attempt.closed_at IS NOT NULL THEN
        RAISE EXCEPTION 'checkpoint attempt is already closed'
            USING ERRCODE = '23505';
    END IF;

    SELECT count(*)
      INTO observed_candidate_count
      FROM epistemic_foundry_evolution.candidate_lineage l
     WHERE l.run_id = attempt.run_id
       AND l.generation = attempt.generation;

    -- A resume point whose population count disagrees with the lineage the
    -- store actually holds is a silent partial fan-in wearing a checkpoint.
    IF observed_candidate_count <> attempt.expected_candidate_count THEN
        RAISE EXCEPTION
            'checkpoint counts do not reconcile: generation % expected % '
            'persisted candidates, the store holds %',
            attempt.generation,
            attempt.expected_candidate_count,
            observed_candidate_count
            USING ERRCODE = '23514';
    END IF;

    PERFORM epistemic_foundry_evolution.seal_checkpoint(
        requested_checkpoint_id,
        attempt.run_id,
        attempt.generation,
        requested_population_hash,
        requested_archive_hash,
        requested_islands_hash,
        requested_bandit_state_hash,
        requested_budget_state_hash,
        requested_testing_ledger_hash,
        requested_evaluator_bundle_hash,
        requested_checkpoint_hash
    );

    UPDATE epistemic_foundry_recovery.checkpoint_attempts
       SET closed_at = statement_timestamp(),
           checkpoint_id = requested_checkpoint_id
     WHERE attempt_id = requested_attempt_id;

    RETURN true;
END
$function$;

-- Recovery's other legal move: give up on a crashed attempt and say why.  The
-- row stays, so the crash remains in the record.
CREATE FUNCTION epistemic_foundry_recovery.abandon_checkpoint_attempt(
    requested_attempt_id text,
    requested_reason text
) RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
    stored_closed timestamp with time zone;
BEGIN
    IF requested_reason IS NULL OR requested_reason = '' THEN
        RAISE EXCEPTION 'abandoning a checkpoint attempt requires a reason'
            USING ERRCODE = '23514';
    END IF;

    SELECT closed_at
      INTO stored_closed
      FROM epistemic_foundry_recovery.checkpoint_attempts
     WHERE attempt_id = requested_attempt_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'checkpoint attempt does not exist'
            USING ERRCODE = '23503';
    END IF;

    IF stored_closed IS NOT NULL THEN
        RAISE EXCEPTION 'checkpoint attempt is already closed'
            USING ERRCODE = '23505';
    END IF;

    UPDATE epistemic_foundry_recovery.checkpoint_attempts
       SET closed_at = statement_timestamp(),
           abandon_reason = requested_reason
     WHERE attempt_id = requested_attempt_id;

    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION
    epistemic_foundry_recovery.schema_digest(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION
    epistemic_foundry_recovery.verify_migration_journal() FROM PUBLIC;
REVOKE ALL ON FUNCTION
    epistemic_foundry_recovery.require_intact_migration_journal()
    FROM PUBLIC;
REVOKE ALL ON FUNCTION
    epistemic_foundry_recovery.open_checkpoint_attempt(
        text, text, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION
    epistemic_foundry_recovery.seal_and_close_attempt(
        text, text, text, text, text, text, text, text, text, text)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION
    epistemic_foundry_recovery.abandon_checkpoint_attempt(text, text)
    FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- What recovery reads.
-- ---------------------------------------------------------------------------

-- Every attempt that was opened and never closed, with the count it expected
-- and the count the store actually holds, so recovery can see how far the
-- crashed work got before deciding whether to finish or abandon it.
CREATE VIEW epistemic_foundry_recovery.pending_recovery AS
    SELECT a.attempt_id,
           a.run_id,
           a.generation,
           a.opened_at,
           a.expected_candidate_count,
           (SELECT count(*)
              FROM epistemic_foundry_evolution.candidate_lineage l
             WHERE l.run_id = a.run_id
               AND l.generation = a.generation)::integer
               AS observed_candidate_count,
           EXISTS (
               SELECT 1
                 FROM epistemic_foundry_evolution.evolution_checkpoints c
                WHERE c.run_id = a.run_id
                  AND c.generation = a.generation
           ) AS checkpoint_present
      FROM epistemic_foundry_recovery.checkpoint_attempts a
     WHERE a.closed_at IS NULL;

-- A safe resume point and the attempt that produced it, joined.  A checkpoint
-- absent from this view has no provenance in the gate.
CREATE VIEW epistemic_foundry_recovery.checkpoint_recovery_points AS
    SELECT c.checkpoint_id,
           c.run_id,
           c.generation,
           c.sealed_at,
           c.checkpoint_hash,
           c.evaluator_bundle_hash,
           a.attempt_id,
           a.opened_at,
           a.closed_at,
           a.expected_candidate_count
      FROM epistemic_foundry_evolution.evolution_checkpoints c
      JOIN epistemic_foundry_recovery.checkpoint_attempts a
        ON a.checkpoint_id = c.checkpoint_id;

-- The completeness audit: a checkpoint that no closed attempt claims.  The
-- gate trigger makes this empty on the happy path; a row here means a seal
-- committed and its attempt did not close, which is precisely the state a
-- crash between the two would leave.
CREATE VIEW epistemic_foundry_recovery.unreconciled_checkpoints AS
    SELECT c.checkpoint_id,
           c.run_id,
           c.generation,
           c.sealed_at
      FROM epistemic_foundry_evolution.evolution_checkpoints c
      LEFT JOIN epistemic_foundry_recovery.checkpoint_attempts a
             ON a.checkpoint_id = c.checkpoint_id
     WHERE a.attempt_id IS NULL;

-- ---------------------------------------------------------------------------
-- The journal rows this migration leaves behind.
-- ---------------------------------------------------------------------------

-- Both schemas are journalled, and both are journalled here: D05's digest is
-- recorded as the gate found and left it (including the trigger this file
-- adds to D05's checkpoint table), so any later change to the evolution store
-- (a dropped NOT NULL, a relaxed CHECK, a rewritten guard) fails
-- re-derivation.  This is the last statement in the transaction, so the
-- digests describe the finished schema.
INSERT INTO epistemic_foundry_recovery.migration_journal
    (migration_id, digest_scope, content_hash)
VALUES
    ('v4_d05/0001_evolution_store',
     'epistemic_foundry_evolution',
     epistemic_foundry_recovery.schema_digest('epistemic_foundry_evolution')),
    ('v4_d06/0001_archive_migration_gate',
     'epistemic_foundry_recovery',
     epistemic_foundry_recovery.schema_digest('epistemic_foundry_recovery'));

COMMIT;
