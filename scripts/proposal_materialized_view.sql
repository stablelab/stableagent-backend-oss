CREATE SCHEMA IF NOT EXISTS internal;
DROP MATERIALIZED VIEW IF EXISTS internal.unified_proposals CASCADE;

/* ---------------------------------------------------------------------------
   Materialised view — identical column list in both SELECTs (15 cols)
   --------------------------------------------------------------------------- */
CREATE MATERIALIZED VIEW internal.unified_proposals
AS
/* ───────────────────────────────  Snapshot  ─────────────────────────────── */
SELECT
    p.proposal_id                                       AS proposal_id,      -- 1
    'snapshot'::text                                    AS source,           -- 2
    p.dao_id                                            AS dao_id,           -- 3
    p.title                                             AS title,            -- 4
    p.body                                              AS body,             -- 5
    to_timestamp(p.created)::timestamptz                AS created_at,       -- 6
    p.start::BIGINT                                     AS vote_start,       -- 7
    p.ends::BIGINT                                      AS vote_end,         -- 8
    p.state                                             AS state,            -- 9
    p.scores_total                                      AS for_votes,        -- 10
    NULL::NUMERIC                                       AS against_votes,    -- 11
    NULL::NUMERIC                                       AS abstain_votes,    -- 12
    NULL::NUMERIC                                       AS votes_object,     -- 13
    p.quorum                                            AS quorum,           -- 14
    p.link                                              AS link              -- 15
FROM snapshot.proposallist p

UNION ALL

/* ────────────────────────────────  Tally  ───────────────────────────────── */
SELECT
    td.id::TEXT                                         AS proposal_id,      -- 1
    'tally'::text                                       AS source,           -- 2
    td.slug                                             AS dao_id,           -- 3
    td.title                                            AS title,            -- 4
    td.description                                      AS body,             -- 5
    td.start_timestamp::timestamptz                     AS created_at,       -- 6
    EXTRACT(EPOCH FROM td.start_timestamp::timestamptz)::BIGINT  AS vote_start, -- 7
    EXTRACT(EPOCH FROM td.end_timestamp::timestamptz)::BIGINT AS vote_end,   -- 8
    td.status                                           AS state,            -- 9
    td.for_votes_count                                  AS for_votes,        -- 10
    td.against_votes_count                              AS against_votes,    -- 11
    td.abstain_votes_count                              AS abstain_votes,    -- 12
    NULL::NUMERIC                                       AS votes_object,     -- 13
    td.quorum                                           AS quorum,           -- 14
    td.snapshot_url                                     AS link              -- 15
FROM tally.tally_data td

UNION ALL

/* ──────────────────────────────── Aragon Multisig  ─────────────────────────────── */
SELECT
    m.proposal_id::TEXT                                 AS proposal_id,      -- 1
    'aragon'::TEXT                                      AS source,           -- 2
    CASE
        WHEN m.ens_name IS NOT NULL AND m.ens_name NOT IN ('', 'NaN') THEN m.ens_name
        WHEN m.dao_address IS NOT NULL AND m.dao_address NOT IN ('', 'NaN') THEN m.dao_address
        ELSE NULL
    END                                                 AS dao_id,           -- 3
    m.title                                             AS title,            -- 4
    m.description                                       AS body,             -- 5
    to_timestamp(m.start_date)                          AS created_at,       -- 6
    m.start_date::BIGINT                                AS vote_start,       -- 7
    m.end_date::BIGINT                                  AS vote_end,         -- 8
    m.status                                            AS state,            -- 9
    m.votes_gained                                      AS for_votes,        -- 10
    NULL::NUMERIC                                       AS against_votes,    -- 11
    NULL::NUMERIC                                       AS abstain_votes,    -- 12
    NULL::NUMERIC                                       AS votes_object,     -- 13
    m.quorum                                            AS quorum,           -- 14
    NULL::TEXT                                          AS link              -- 15
FROM aragon.aragon_multisig m

UNION ALL

/* ──────────────────────────────── Aragon VT ─────────────────────────────── */
SELECT
    v.proposal_id::TEXT                                 AS proposal_id,      -- 1
    'aragon'::TEXT                                      AS source,           -- 2
    CASE
        WHEN v.ens_name IS NOT NULL AND v.ens_name NOT IN ('', 'NaN') THEN v.ens_name
        WHEN v.dao_address IS NOT NULL AND v.dao_address NOT IN ('', 'NaN') THEN v.dao_address
        ELSE NULL
    END                                                 AS dao_id,           -- 3
    v.title                                             AS title,            -- 4
    v.description                                       AS body,             -- 5
    to_timestamp(v.start_date)                          AS created_at,       -- 6
    v.start_date::BIGINT                                AS vote_start,       -- 7
    v.end_date::BIGINT                                  AS vote_end,         -- 8
    v.status                                            AS state,            -- 9
    v.for_votes                                         AS for_votes,        -- 10
    v.against_votes                                     AS against_votes,    -- 11
    v.abstain_votes                                     AS abstain_votes,    -- 12
    NULL::NUMERIC                                       AS votes_object,     -- 13
    v.min_voting_power                                  AS quorum,           -- 14
    NULL::TEXT                                          AS link              -- 15
FROM aragon.aragon_vt v

UNION ALL

/* ──────────────────────────────── MakerDAO (onchain) ─────────────────────────────── */
SELECT
    o.poll_id::TEXT                                     AS proposal_id,      -- 1
    'onchain_daos'::TEXT                                AS source,           -- 2
    'MakerDAO'                                          AS dao_id,           -- 3
    o.title                                             AS title,            -- 4
    o.summary                                           AS body,             -- 5
    to_timestamp(o.start_date)                          AS created_at,       -- 6
    o.start_date::BIGINT                                AS vote_start,       -- 7
    o.end_date::BIGINT                                  AS vote_end,         -- 8
    NULL                                                AS state,            -- 9
    NULL::NUMERIC                                       AS for_votes,        -- 10
    NULL::NUMERIC                                       AS against_votes,    -- 11
    NULL::NUMERIC                                       AS abstain_votes,    -- 12
    o.total_mkr_participation                           AS votes_object,     -- 13
    NULL::NUMERIC                                       AS quorum,           -- 14
    o.discussion_url                                    AS link              -- 15
FROM onchain_daos.makerdao_governance_polls o

UNION ALL

/* ──────────────────────────────── On-Chain DAOs ─────────────────────────────── */
SELECT
    oc.proposal_id::TEXT               AS proposal_id,     -- 1
    'onchain_daos'::TEXT               AS source,          -- 2
    oc.address                        AS dao_id,          -- 3
    oc.title                          AS title,           -- 4
    oc.description                    AS body,            -- 5
    to_timestamp(oc.created_at)       AS created_at,      -- 6
    oc.start_date::BIGINT             AS vote_start,      -- 7
    oc.end_date::BIGINT               AS vote_end,        -- 8
    oc.state                         AS state,           -- 9
    oc.for_votes::NUMERIC             AS for_votes,       -- 10
    oc.against_votes::NUMERIC         AS against_votes,   -- 11
    oc.abstain_votes::NUMERIC         AS abstain_votes,   -- 12
    NULL::NUMERIC                    AS votes_object,    -- 13
    NULL::NUMERIC                    AS quorum,          -- 14
    oc.discussion                    AS link             -- 15
FROM onchain_daos.tally_onchain_data oc
Join internal.onchain_daos ocp on ocp.dao_id = oc.dao_id
    and ocp.snapshot_id is null and ocp.tally_id is null
WITH NO DATA;

COMMENT ON MATERIALIZED VIEW internal.unified_proposals IS
$$Unifies Snapshot & Tally proposals with a minimal common column set and
pgvector embeddings. Column order/type identical in both branches (15 cols).$$;

/* ---------------------------------------------------------------------------
   Indexes
   --------------------------------------------------------------------------- */
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    unified_proposals_pk
    ON internal.unified_proposals (proposal_id, source, dao_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_proposals_dao_id_idx      ON internal.unified_proposals (dao_id);           -- 1
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_proposals_state_idx       ON internal.unified_proposals (state);            -- 2
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_proposals_created_at_idx  ON internal.unified_proposals (created_at);       -- 3
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_proposals_proposal_id_idx ON internal.unified_proposals (proposal_id);      -- 4
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_proposals_title_idx       ON internal.unified_proposals ((md5(title)));      -- 5

/* ---------------------------------------------------------------------------
   First populate & optional cron job
   --------------------------------------------------------------------------- */
-- REFRESH MATERIALIZED VIEW  internal.unified_proposals;
SELECT cron.schedule('refresh_unified_proposals',
                     '0 */2 * * *',
                     $$REFRESH MATERIALIZED VIEW CONCURRENTLY internal.unified_proposals;$$);
