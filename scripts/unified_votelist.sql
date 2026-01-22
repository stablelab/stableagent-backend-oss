CREATE MATERIALIZED VIEW internal.unified_votelist AS
SELECT
    'snapshot'              AS source,            --  1
    vote_id                 AS vote_id,           --  2
    voter                   AS voter,             --  3
    created                 AS created,           --  4
    proposal                AS proposal,          --  5
    choice                  AS choice,            --  6
    NULL                    AS contract_address,  --  7
    space                   AS space,             --  8
    NULL                    AS dao_name,          --  9
    app                     AS app,               -- 10
    reason                  AS reason,            -- 11
    vp_state                AS vp_state,          -- 12
    typename                AS typename,          -- 13
    vp_by_strategy          AS vp_by_strategy,    -- 14
    vp                      AS vp                 -- 15
FROM snapshot.votelist

UNION ALL

SELECT
    'onchain_daos'          AS source,            --  1
    vote_id                 AS vote_id,           --  2
    voter                   AS voter,             --  3
    created                 AS created,           --  4
    proposal                AS proposal,          --  5
    choice                  AS choice,            --  6
    contract_address        AS contract_address,  --  7
    NULL                    AS space,             --  8
    dao_name                AS dao_name,          --  9
    NULL                    AS app,               -- 10
    reason                  AS reason,            -- 11
    NULL                    AS vp_state,          -- 12
    typename                AS typename,          -- 13
    NULL                    AS vp_by_strategy,    -- 14
    vp                      AS vp                 -- 15
FROM onchain_daos.votelist;

/* ---------------------------------------------------------------------------
   Comment
   --------------------------------------------------------------------------- */
COMMENT ON MATERIALIZED VIEW internal.unified_votelist IS
$$
Unifies Snapshot & On-Chain DAO votes with a consistent column set (15 columns),
including voter metadata, choice, and voting power.
$$;

/* ---------------------------------------------------------------------------
   Indexes
   --------------------------------------------------------------------------- */
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    unified_votelist_pk
    ON internal.unified_votelist (vote_id, source, proposal, voter);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_votelist_voter_idx        ON internal.unified_votelist (voter);           -- 1
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_votelist_vote_id_idx      ON internal.unified_votelist (vote_id);           -- 2
	
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_votelist_proposal_idx     ON internal.unified_votelist (proposal, contract_address, source);        -- 3

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_votelist_created_idx      ON internal.unified_votelist (proposal, space, source);         -- 4

/* ---------------------------------------------------------------------------
   First populate & optional cron job (refresh every 2 hours)
   --------------------------------------------------------------------------- */
-- REFRESH MATERIALIZED VIEW CONCURRENTLY internal.unified_votelist;

SELECT cron.schedule('refresh_unified_votelist',
                     '0 */2 * * *',
                     $$REFRESH MATERIALIZED VIEW CONCURRENTLY internal.unified_votelist;$$);
