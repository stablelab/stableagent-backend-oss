CREATE SCHEMA IF NOT EXISTS internal;
DROP MATERIALIZED VIEW IF EXISTS internal.unified_github_commits CASCADE;

CREATE MATERIALIZED VIEW internal.unified_github_commits AS
SELECT 
    b.*,
    e.content AS content_summary,
    e.embedding
FROM 
    github.github_board b
LEFT JOIN 
    github.github_board_stages_embeddings e
    ON b.url = e.url
WHERE 
    b.status IS NOT NULL
    AND b.status <> ''
ORDER BY 
    b.url;

COMMENT ON MATERIALIZED VIEW internal.unified_github_commits IS
$$
Aggregated daily GitHub commits.
$$;

/* ---------------------------------------------------------------------------  
   Indexes
   --------------------------------------------------------------------------- */

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    unified_github_commits_url_title_idx
    ON internal.unified_github_commits (url, title);

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_github_commits_url_idx           ON internal.unified_github_commits (url);          -- 1
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    unified_github_commits_title_idx          ON internal.unified_github_commits (title);       -- 2

/* ---------------------------------------------------------------------------
   First populate & optional cron job
   --------------------------------------------------------------------------- */
-- REFRESH MATERIALIZED VIEW  internal.unified_github_commits;
SELECT cron.schedule(
    'refresh_unified_github_commits',
    '0 */2 * * *',
    $$REFRESH MATERIALIZED VIEW CONCURRENTLY internal.unified_github_commits;$$);