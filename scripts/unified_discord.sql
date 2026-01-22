CREATE SCHEMA IF NOT EXISTS internal;
DROP MATERIALIZED VIEW IF EXISTS internal.unified_discord CASCADE;

CREATE MATERIALIZED VIEW internal.unified_discord AS
WITH message_data AS (
    SELECT
        dm.timestamp::date AS date,
        COALESCE(d.snapshot_id, d.name) AS dao_id,
        MIN(dm.unix_ts) AS start_unix,
        MAX(dm.unix_ts) AS end_unix,
        JSON_AGG(
            JSON_STRIP_NULLS(
                JSON_BUILD_OBJECT(
                    'unix_ts', dm.unix_ts,
                    'Channel', dm.channel_name,
                    'Author', dm.author_username || ' (' || COALESCE(dm.author_global_name, '') || ')',
                    'Message', dm.content,
                    'referenced_message_content',
                        CASE
                            WHEN dm.referenced_message IS NOT NULL THEN dm.referenced_message ->> 'content'
                            ELSE NULL
                        END,
                    'referenced_author',
                        CASE
                            WHEN dm.referenced_message IS NOT NULL THEN dm.referenced_message -> 'author' ->> 'username'
                            ELSE NULL
                        END
                )
            ) ORDER BY dm.unix_ts
        ) AS content
    FROM discord.discord_msg dm
    LEFT JOIN internal.daos d ON dm.dao_id = d.id
    WHERE dm.timestamp::date < CURRENT_DATE - INTERVAL '3 days'
    GROUP BY dm.timestamp::date, COALESCE(d.snapshot_id, d.name)
)
SELECT 
    md.date,                                        -- 1
    md.dao_id,                                      -- 2
    md.start_unix,                                  -- 3
    md.end_unix,                                    -- 4
    md.content,                                     -- 5
    de.content AS content_summary,                  -- 6
    de.embedding AS embedding                       -- 7
FROM message_data md
LEFT JOIN discord.discord_embeddings de
    ON md.start_unix = de.start_unix
    AND md.end_unix = de.end_unix
    AND md.dao_id = de.dao_id
ORDER BY md.date, md.dao_id;

COMMENT ON MATERIALIZED VIEW internal.unified_discord IS
$$
Aggregated daily Discord messages per DAO (by snapshot_id or name), including all messages older than 3 days.
Includes message details as JSON array and joined embeddings content as content_summary.
$$;

/* ---------------------------------------------------------------------------
   Indexes
   --------------------------------------------------------------------------- */
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    unified_discord_date_dao_idx
    ON internal.unified_discord (date, dao_id, start_unix, end_unix);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_discord_dao_idx           ON internal.unified_discord (dao_id);          -- 1
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_discord_date_idx          ON internal.unified_discord (date);            -- 2
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_discord_start_unix_idx    ON internal.unified_discord (start_unix);      -- 3
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_discord_end_unix_idx      ON internal.unified_discord (end_unix);        -- 4

/* ---------------------------------------------------------------------------
   First populate & optional cron job
   --------------------------------------------------------------------------- */
-- REFRESH MATERIALIZED VIEW  internal.unified_discord;
SELECT cron.schedule(
    'refresh_unified_discord',
    '0 */2 * * *',
    $$REFRESH MATERIALIZED VIEW CONCURRENTLY internal.unified_discord;$$
);
