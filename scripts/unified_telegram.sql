/* ---------------------------------------------------------------------------
   Create Materialized View
   --------------------------------------------------------------------------- */
DROP MATERIALIZED VIEW IF EXISTS internal.unified_telegram;

CREATE MATERIALIZED VIEW internal.unified_telegram AS
WITH aggregated_messages AS (
    SELECT
        ct.dao_id,
        ct.window_number,
        ct.topic_id,
        MIN(ct.window_start) AS window_start,
        MAX(ct.window_end) AS window_end,
        MIN(ct.unix_ts) AS start_unix,
        MAX(ct.unix_ts) AS end_unix,
        STRING_AGG(
            CONCAT('[', ct.unix_ts, ']: ', ct.message),
            E'\n\n' ORDER BY ct.unix_ts
        ) AS aggregated_messages
    FROM telegram.conceptual_telegram AS ct
    GROUP BY ct.dao_id, ct.window_number, ct.topic_id
)
SELECT
    COALESCE(d.snapshot_id::text, d.name) AS dao_id,
    tce.window_number,
    tce.topic_id,
    tce.topic_title,
    tce.topic_representation,
    tce.window_start,
    tce.window_end,
    tce.start_unix,
    tce.end_unix,
    tce.content,
    tce.embedding,
    am.aggregated_messages
FROM telegram.telegram_conceptual_embeddings AS tce
LEFT JOIN aggregated_messages AS am
    ON tce.dao_id = am.dao_id
   AND tce.window_number = am.window_number
   AND tce.topic_id = am.topic_id
LEFT JOIN internal.daos AS d
    ON tce.dao_id = d.id
WITH DATA;


/* ---------------------------------------------------------------------------
   Comment on Materialized View
   --------------------------------------------------------------------------- */
COMMENT ON MATERIALIZED VIEW internal.unified_telegram IS
$$
Aggregated conceptual Telegram messages per DAO, window, and topic.
Includes all message texts (with timestamps), joined embeddings content,
and DAO snapshot_id (or name if null) as dao_id from internal.daos.
Automatically refreshed every 2 hours via pg_cron.
$$;


/* ---------------------------------------------------------------------------
   Indexes for Efficient Querying
   --------------------------------------------------------------------------- */
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    unified_telegram_unique_idx
    ON internal.unified_telegram (dao_id, window_number, topic_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_telegram_start_end_unique_idx
    ON internal.unified_telegram (dao_id, window_start, window_end);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_telegram_dao_idx
    ON internal.unified_telegram (dao_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_telegram_window_idx
    ON internal.unified_telegram (window_number);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_telegram_start_unix_idx
    ON internal.unified_telegram (start_unix);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_telegram_end_unix_idx
    ON internal.unified_telegram (end_unix);


/* ---------------------------------------------------------------------------
   Cron Job for Periodic Refresh (every 2 hours)
   --------------------------------------------------------------------------- */
SELECT cron.schedule(
    'refresh_unified_telegram',
    '0 */2 * * *',
    $$REFRESH MATERIALIZED VIEW CONCURRENTLY internal.unified_telegram;$$
);
