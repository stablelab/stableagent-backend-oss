CREATE SCHEMA IF NOT EXISTS internal;
DROP MATERIALIZED VIEW IF EXISTS internal.unified_github_board CASCADE;

CREATE MATERIALIZED VIEW internal.unified_github_board AS
SELECT 
    c.*,
    e.content AS content_summary,
    e.embedding
FROM 
    github.github_commits c
LEFT JOIN 
    github.github_commit_embeddings e
    ON c.base_url = e.base_url AND c.sha = e.sha
ORDER BY 
    c.unix_ts, c.base_url;
    

COMMENT ON MATERIALIZED VIEW internal.unified_github_board IS
$$
Aggregated daily GitHub board stage progress.
$$;

/* ---------------------------------------------------------------------------  
   Indexes
   --------------------------------------------------------------------------- */
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    unified_github_board_date_dao_sha_parent_sha_idx
    ON internal.unified_github_board (base_url, sha, parent_sha);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_github_board_base_url_idx           ON internal.unified_github_board (base_url);          -- 1
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_github_board_sha_idx          ON internal.unified_github_board (sha);               -- 2
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_github_board_parent_sha_idx    ON internal.unified_github_board (parent_sha);      -- 3

/* ---------------------------------------------------------------------------
   First populate & optional cron job
   --------------------------------------------------------------------------- */
-- REFRESH MATERIALIZED VIEW  internal.unified_github_board;
SELECT cron.schedule(
    'refresh_unified_github_board',
    '0 */2 * * *',
    $$REFRESH MATERIALIZED VIEW CONCURRENTLY internal.unified_github_board;$$);