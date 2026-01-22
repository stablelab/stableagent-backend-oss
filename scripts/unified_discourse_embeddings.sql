CREATE SCHEMA IF NOT EXISTS internal;
DROP MATERIALIZED VIEW IF EXISTS internal.unified_discourse_embeddings CASCADE;

CREATE MATERIALIZED VIEW internal.unified_discourse_embeddings AS
SELECT
    dp.topic_id,                                    -- 1
    de.index,                                       -- 2
    dp.topic_title,                                 -- 3
    COALESCE(d.snapshot_id, d.name) AS dao_id,      -- 4
    de.content AS content_summary,                  -- 5
    de.embedding                                    -- 6
FROM
    discourse.posts dp
LEFT JOIN internal.daos d ON dp.dao_id = d.id
JOIN discourse.discourse_embeddings de
    ON de.topic_id::integer = dp.topic_id::integer
    AND de.dao_id = COALESCE(d.snapshot_id, d.name)
WHERE
    dp.dao_id IN (86)
GROUP BY
    dp.topic_id,
    de.index,
    dp.topic_title,
    COALESCE(d.snapshot_id, d.name),
    de.content,
    de.embedding
ORDER BY
    dp.topic_id,
    de.index;

COMMENT ON MATERIALIZED VIEW internal.unified_discourse_embeddings IS
$$
Unified discourse embeddings view across DAOs.
Includes topic_id, topic_title, dao_id (as snapshot_id or name), content summary, and vector embedding.
$$;

-- ----------------------------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------------------------

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    unified_discourse_embeddings_topic_dao_idx
    ON internal.unified_discourse_embeddings (topic_id, dao_id, index);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_discourse_embeddings_dao_idx
    ON internal.unified_discourse_embeddings (dao_id, index);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_discourse_embeddings_title_idx
    ON internal.unified_discourse_embeddings (topic_title);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_discourse_embeddings_title_index_idx
    ON internal.unified_discourse_embeddings (topic_title, index);

/* ---------------------------------------------------------------------------
   First populate & optional cron job
   --------------------------------------------------------------------------- */
-- REFRESH MATERIALIZED VIEW  internal.unified_discourse_embeddings;
SELECT cron.schedule(
    'refresh_unified_discourse_embeddings',
    '0 */2 * * *',
    $$REFRESH MATERIALIZED VIEW CONCURRENTLY internal.unified_discourse_embeddings;$$
);
