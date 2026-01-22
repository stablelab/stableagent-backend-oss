CREATE SCHEMA IF NOT EXISTS internal;
DROP MATERIALIZED VIEW IF EXISTS internal.unified_embeddings CASCADE;

/* ---------------------------------------------------------------------------
   Materialized View: internal.unified_embeddings
   Unifies embedding vectors from multiple sources with consistent structure.
   --------------------------------------------------------------------------- */
CREATE MATERIALIZED VIEW internal.unified_embeddings AS

/* ─────────────────────────────── Snapshot embeddings ─────────────────────────────── */
SELECT
    pe.proposal_id::TEXT                                AS proposal_id,      -- 1
    'snapshot'::TEXT                                     AS source,           -- 2
    p.dao_id::TEXT                                       AS dao_id,           -- 3
    pe.index                                             AS index,            -- 4
    pe.embedding                                         AS embedding         -- 5
FROM snapshot.proposal_embeddings pe
JOIN snapshot.proposallist p ON p.proposal_id = pe.proposal_id

UNION ALL

/* ─────────────────────────────── Tally embeddings ─────────────────────────────── */
SELECT
    te.proposal_id::TEXT                                AS proposal_id,      -- 1
    'tally'::TEXT                                        AS source,           -- 2
    td.slug::TEXT                                        AS dao_id,           -- 3
    te.index                                             AS index,            -- 4
    te.embedding                                         AS embedding         -- 5
FROM tally.proposal_embeddings te
JOIN tally.tally_data td ON td.id::TEXT = te.proposal_id

UNION ALL

/* ─────────────────────────────── Aragon embeddings ─────────────────────────────── */
SELECT
    ar.proposal_id::TEXT                                AS proposal_id,      -- 1
    'aragon'::TEXT                                       AS source,           -- 2
    ar.dao_                                              AS dao_id,           -- 3
    ar.index                                             AS index,            -- 4
    ar.embedding                                         AS embedding         -- 5
FROM aragon.proposal_embeddings ar

UNION ALL

/* ─────────────────────────────── MakerDAO embeddings ─────────────────────────────── */
SELECT
    me.proposal_id::TEXT                                AS proposal_id,      -- 1
    'onchain_daos'::TEXT                                     AS source,           -- 2
    'MakerDAO'::TEXT                                     AS dao_id,           -- 3
    me.index                                             AS index,            -- 4
    me.embedding                                         AS embedding         -- 5
FROM onchain_daos.proposal_embeddings_maker me

UNION ALL

/* ─────────────────────────────── On-Chain DAOs embeddings ─────────────────────────────── */
SELECT
    oc.proposal_id::TEXT                                AS proposal_id,      -- 1
    'onchain_daos'::TEXT                               AS source,           -- 2
    ocp.contract_address::TEXT                                    AS dao_id,           -- 3
    oc.index                                             AS index,            -- 4
    oc.embedding                                         AS embedding         -- 5
FROM onchain_daos.proposal_embeddings oc
Join internal.onchain_daos ocp on ocp.dao_id = oc.dao_id
WITH NO DATA;

COMMENT ON MATERIALIZED VIEW internal.unified_embeddings IS
$$
Unified embeddings view across Snapshot, Tally, Aragon, and MakerDAO.
Includes consistent proposal_id, source, dao_id, index, and pgvector embedding.
$$;

-- Unique index on proposal_id, source, and index

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    unified_embeddings_pk
    ON internal.unified_embeddings (proposal_id, dao_id, index);

-- Vector index for fast ANN search
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_embeddings_ivfflat
    ON internal.unified_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);


/* ---------------------------------------------------------------------------
   First populate & optional cron job
   --------------------------------------------------------------------------- */
-- REFRESH MATERIALIZED VIEW  internal.unified_proposals;
SELECT cron.schedule(
    'refresh_unified_embeddings',
    '0 */2 * * *',
    $$REFRESH MATERIALIZED VIEW CONCURRENTLY internal.unified_embeddings;$$
);
