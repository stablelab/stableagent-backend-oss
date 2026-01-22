"""Database client for Research Agent tools.

Provides a shared database connection with semantic search capabilities.

PRIMARY TABLES - Unified materialized views with embeddings:
PRIMARY TABLES - Unified materialized views with embeddings:
┌────────────────────────────────────────────────┬──────────────┬─────────────────────────────────────────────────────┐
│ Table                                         │ Embedding    │ Key Columns / Notes                                  │
├───────────────────────────────────────────────┼──────────────┼──────────────────────────────────────────────────────┤
│ internal.unified_proposal_embeddings          │ vector(3072) │ 20,249 rows - Arbitrum, Gnosis, Aave, etc.           │
│ discourse.discourse_embeddings_3072           │ vector(3072) │ 14,828 rows - semantic discourse search              │
│ discourse.posts                               │ -            │ Full forum posts (keyword fallback) - all DAOs       │
│ telegram.telegram_conceptual_embeddings_3072  │ vector(768)  │ 31,968 rows - near, curve, metis, etc.               │
│ github.github_metadata_3072                   │ vector(3072) │ 835 rows - 1inch, aave, ampleforth etc.              │
| github.github_commits_daos                    │ -            │ Full commit messages for 1inch, aave, ampleforth etc.│
└───────────────────────────────────────────────┴──────────────┴──────────────────────────────────────────────────────┘


EMBEDDING PROFILES:
- TEXT_768: text-embedding-004 (768-dim) for proposals, telegram, discord
- GEMINI_3072: gemini-embedding-001 (3072-dim) for discourse

OTHER TABLES (no embeddings):
- snapshot.votelist: vote_id, voter, proposal, choice, space, vp, reason
- internal.daos: id, name, snapshot_id, tally_id, discourse_url
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.services.connection_pool import get_connection_pool
from src.services.gemini_embeddings import EmbeddingsService
from src.utils.logger import logger


class EmbeddingProfile(Enum):
    """Embedding model profiles with their configurations."""
    # 3072-dimensional embeddings (future/new tables)
    GEMINI_3072 = "gemini_3072"
    # 768-dimensional embeddings (default - unified_* tables use this)
    TEXT_768 = "text_768"


@dataclass
class EmbeddingConfig:
    """Configuration for an embedding model."""
    model: str
    dimensionality: int


# Embedding configurations for each profile
EMBEDDING_CONFIGS: Dict[EmbeddingProfile, EmbeddingConfig] = {
    EmbeddingProfile.GEMINI_3072: EmbeddingConfig(
        model="gemini-embedding-001",
        dimensionality=3072,
    ),
    EmbeddingProfile.TEXT_768: EmbeddingConfig(
        model="text-embedding-004",
        dimensionality=768,
    ),
}

# Default profile - unified_* tables use 3072-dim embeddings
DEFAULT_PROFILE = EmbeddingProfile.GEMINI_3072


def parse_date_to_timestamp(date_str: Optional[str]) -> Optional[int]:
    """Parse a date string (YYYY-MM-DD) to Unix timestamp."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp())
    except ValueError:
        logger.warning(f"[ResearchDB] Invalid date format: {date_str}. Expected YYYY-MM-DD")
        return None


def parse_date_to_iso(date_str: Optional[str]) -> Optional[str]:
    """Parse a date string (YYYY-MM-DD) to ISO format for SQL."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        logger.warning(f"[ResearchDB] Invalid date format: {date_str}. Expected YYYY-MM-DD")
        return None


import re

# Pattern to detect proposal ID queries like BIP-821, AIP-123, SIP-456, etc.
# Common prefixes: BIP (Balancer), AIP (Aave), SIP (Synthetix), PIP (Polygon), 
# GIP (Gnosis), UIP (Uniswap), TIP (Threshold), MIP (Maker), etc.
PROPOSAL_ID_PATTERN = re.compile(
    r'^[A-Z]{2,5}[-–—]?\d+$',  # AIP-123, BIP821, GIP-99
    re.IGNORECASE
)


def is_proposal_id_query(query: str) -> bool:
    """Check if query looks like a proposal identifier (e.g., BIP-821, AIP-123).
    
    Returns True for patterns like:
    - BIP-821, BIP821
    - AIP-123, AIP123  
    - SIP-456, GIP-99
    - MIP-42, PIP-100
    """
    if not query:
        return False
    # Clean and check the query
    cleaned = query.strip()
    return bool(PROPOSAL_ID_PATTERN.match(cleaned))


class ResearchDatabaseClient:
    """Database client optimized for research queries with semantic search.
    
    Uses:
    - PostgreSQL connection pool for efficient connections
    - Configurable embedding models per table (768 or 3072 dimensions)
    - Cosine distance (<=>) for vector similarity searches
    """
    
    def __init__(self):
        self._pool = None
        self._embedding_services: Dict[EmbeddingProfile, EmbeddingsService] = {}
    
    def _get_pool(self):
        """Get or create connection pool."""
        if self._pool is None:
            self._pool = get_connection_pool()
        return self._pool
    
    def _get_embedding_service(
        self, 
        profile: EmbeddingProfile = DEFAULT_PROFILE
    ) -> EmbeddingsService:
        """Get or create embedding service for the given profile."""
        if profile not in self._embedding_services:
            config = EMBEDDING_CONFIGS[profile]
            self._embedding_services[profile] = EmbeddingsService(
                model=config.model,
                dimensionality=config.dimensionality
            )
            logger.info(
                f"[ResearchDB] Created embedding service: {config.model} "
                f"({config.dimensionality} dims)"
            )
        return self._embedding_services[profile]
    
    def generate_embedding(
        self, 
        text: str, 
        profile: EmbeddingProfile = DEFAULT_PROFILE
    ) -> List[float]:
        """Generate an embedding for the given text using the specified profile."""
        try:
            service = self._get_embedding_service(profile)
            embeddings = service.embed_documents([text])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            return []
        except Exception as e:
            logger.error(f"[ResearchDB] Failed to generate embedding: {e}")
            return []
    
    def format_vector(
        self, 
        embedding: List[float], 
        profile: EmbeddingProfile = DEFAULT_PROFILE
    ) -> str:
        """Format embedding as PostgreSQL vector literal."""
        if not embedding:
            # Return a zero vector of correct dimension
            dim = EMBEDDING_CONFIGS[profile].dimensionality
            return f"'[{','.join(['0'] * dim)}]'::vector"
        return f"'[{','.join(str(v) for v in embedding)}]'::vector"
    
    def execute_query(
        self,
        sql: str,
        params: Optional[Tuple] = None,
        timeout_ms: int = 60000
    ) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results as list of dicts.
        
        Args:
            sql: SQL query to execute
            params: Optional tuple of parameters for parameterized queries
            timeout_ms: Query timeout in milliseconds
        
        Returns:
            List of result rows as dictionaries
        """
        conn = None
        try:
            pool = self._get_pool()
            conn = pool.get_connection()
            
            with conn.cursor() as cur:
                # Set timeout
                cur.execute("SET statement_timeout = %s", (timeout_ms,))
                
                # Execute query
                if params:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                
                # Fetch results
                rows = cur.fetchall()
                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    return [dict(zip(columns, row)) for row in rows]
                return []
                
        except Exception as e:
            logger.error(f"[ResearchDB] Query failed: {e}")
            raise
        finally:
            if conn:
                try:
                    pool.return_connection(conn)
                except Exception:
                    pass
    
    def semantic_search(
        self,
        table: str,
        query: str,
        embedding_column: str = "embedding",
        select_columns: str = "*",
        where_clause: str = "",
        limit: int = 10,
        join_clause: str = "",
        embedding_profile: EmbeddingProfile = DEFAULT_PROFILE,
    ) -> List[Dict[str, Any]]:
        """Execute a semantic search query using vector similarity.
        
        Args:
            table: Table or view to query (e.g., "internal.unified_proposal_embeddings")
            query: User's search query (will be embedded)
            embedding_column: Column containing embeddings
            select_columns: Columns to select (default "*")
            where_clause: Optional WHERE conditions (without "WHERE")
            limit: Maximum results to return
            join_clause: Optional JOIN clause
            embedding_profile: Which embedding model to use for query embedding
        
        Returns:
            Results ordered by cosine similarity (closest first)
        """
        # Generate embedding for query using the specified profile
        embedding = self.generate_embedding(query, profile=embedding_profile)
        if not embedding:
            logger.warning(f"[ResearchDB] No embedding generated for query: {query}")
            # Fall back to keyword search if embedding fails
            return self._keyword_fallback_search(
                table, query, select_columns, where_clause, limit, join_clause
            )
        
        vector_literal = self.format_vector(embedding, profile=embedding_profile)
        
        # Build SQL with vector similarity
        sql = f"""
        SELECT {select_columns}, 
               {embedding_column} <=> {vector_literal} AS distance
        FROM {table}
        {join_clause}
        """
        
        if where_clause:
            sql += f" WHERE {where_clause}"
        
        sql += f"""
        ORDER BY distance ASC
        LIMIT {limit}
        """
        
        config = EMBEDDING_CONFIGS[embedding_profile]
        logger.info(
            f"[ResearchDB] Semantic search on {table} using {config.model} "
            f"({config.dimensionality} dims) for: {query[:100]}..."
        )
        return self.execute_query(sql)
    
    def _keyword_fallback_search(
        self,
        table: str,
        query: str,
        select_columns: str = "*",
        where_clause: str = "",
        limit: int = 10,
        join_clause: str = "",
    ) -> List[Dict[str, Any]]:
        """Fallback to keyword search when embeddings fail."""
        # Simple ILIKE search on common text columns
        keywords = query.replace("'", "''").split()[:5]  # Limit keywords
        
        sql = f"""
        SELECT {select_columns}
        FROM {table}
        {join_clause}
        """
        
        conditions = []
        if where_clause:
            conditions.append(f"({where_clause})")
        
        # Add keyword conditions for common columns
        keyword_conditions = []
        for kw in keywords:
            keyword_conditions.append(f"title ILIKE '%{kw}%' OR body ILIKE '%{kw}%'")
        
        if keyword_conditions:
            conditions.append(f"({' OR '.join(keyword_conditions)})")
        
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        
        sql += f" LIMIT {limit}"
        
        logger.info(f"[ResearchDB] Keyword fallback search on {table}")
        return self.execute_query(sql)
    
    # ==================
    # Data Source Search Methods
    # ==================
    
    def search_proposals(
        self,
        query: Optional[str] = None,
        source: Optional[str] = None,
        dao_id: Optional[str] = None,
        state: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
        embedding_profile: EmbeddingProfile = EmbeddingProfile.GEMINI_3072,  # Use 3072-dim
    ) -> List[Dict[str, Any]]:
        """Search DAO governance proposals using internal.unified_proposal_embeddings.
        
        PURPOSE: Find governance proposals from DAOs. Proposals are formal votes on
        treasury spending, protocol changes, grants, parameter updates, etc.
        
        TABLES:
        - internal.unified_proposal_embeddings: Full proposal metadata joined via proposal_id
        
        SOURCES:
        - Snapshot: Off-chain voting (most common)
        - Tally: On-chain governance via Tally
        - Onchain DAOs: Other on-chain governance
        
        Args:
            query: Semantic search query (e.g., "treasury diversification"). 
                   If None or empty, returns latest proposals ordered by date.
            source: Filter by source (snapshot, tally, onchain_daos)
            dao_id: Filter by DAO identifier (e.g., 'gnosis.eth', 'arbitrumfoundation.eth')
            state: Filter by proposal state (e.g., "active", "closed", "pending")
            start_date: Filter proposals created after this date (YYYY-MM-DD)
            end_date: Filter proposals created before this date (YYYY-MM-DD)
            limit: Maximum results
            embedding_profile: Embedding model - default GEMINI_3072 for unified_embeddings
        """
        # If no query provided, return latest proposals by date (no semantic search)
        if not query or not query.strip():
            logger.info("[ResearchDB] No query provided, returning latest proposals by date")
            return self._search_proposals_by_date(
                source=source, dao_id=dao_id, state=state,
                start_date=start_date, end_date=end_date, limit=limit
            )
        
        # For proposal ID queries (BIP-821, AIP-123, etc.), try title search first
        if is_proposal_id_query(query):
            logger.info(f"[ResearchDB] Detected proposal ID query '{query}', trying title search first")
            title_results = self._search_proposals_by_title(
                query=query, source=source, dao_id=dao_id, state=state, limit=limit
            )
            if title_results:
                logger.info(f"[ResearchDB] Found {len(title_results)} proposals by title match")
                return title_results
            logger.info("[ResearchDB] No title matches, falling back to semantic search")
        
        # Generate embedding with 768-dim model for semantic search
        embedding = self.generate_embedding(query, profile=embedding_profile)
        if not embedding:
            logger.warning("[ResearchDB] No embedding generated, falling back to keyword search")
            return self._search_proposals_keyword(
                query=query, source=source, dao_id=dao_id, state=state,
                start_date=start_date, end_date=end_date, limit=limit
            )
        
        vector_literal = self.format_vector(embedding, profile=embedding_profile)
        
        # Build WHERE clause for unified_proposals
        where_parts = []
        if source:
            where_parts.append(f"e.source = '{source}'")
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            # For Tally, dao_id in unified_proposals is the slug, but users may provide org_id
            where_parts.append(f"""(
                e.dao_id = '{safe_dao}' 
                OR e.dao_id ILIKE '%{safe_dao}%'
                OR (e.source = 'tally' AND e.dao_id IN (
                    SELECT DISTINCT slug FROM tally.tally_data WHERE org_id::text = '{safe_dao}'
                ))
            )""")
        if state:
            where_parts.append(f"LOWER(p.state) = LOWER('{state}')")
        
        # Date filtering
        start_iso = parse_date_to_iso(start_date)
        end_iso = parse_date_to_iso(end_date)
        if start_iso:
            where_parts.append(f"p.created_at >= '{start_iso}'")
        if end_iso:
            where_parts.append(f"p.created_at <= '{end_iso}'")
        
        where_clause = " AND ".join(where_parts) if where_parts else "TRUE"
        
        # Semantic search on unified_embeddings joined with unified_proposals 
        # TODO : same as in the proposal_results_tool.py
        sql = f"""
        SELECT DISTINCT ON (e.proposal_id)
            e.proposal_id,
            e.dao_id,
            e.title,
            LEFT(e.body, 500) as body,
            e.source,
            e.state,
            e.created_at,
            e.ends_at,
            e.choices,
            e.scores,
            e.topic_id as discourse_topic_id,
            e.link,
            e.embedding <=> {vector_literal} AS distance
        FROM internal.unified_proposal_embeddings e
        WHERE {where_clause}
        ORDER BY e.proposal_id, distance ASC
        LIMIT {limit * 2}
        """
        
        # Execute and sort by distance
        logger.info(f"[ResearchDB] Semantic proposal search on unified_embeddings for: {query[:100] if query else 'governance'}...")
        results = self.execute_query(sql)
        
        # Sort by distance and limit
        if results:
            results.sort(key=lambda x: x.get('distance', 1.0))
            results = results[:limit]
        
        # If no results, fall back to keyword search
        if not results:
            logger.info("[ResearchDB] No semantic results, falling back to keyword search")
            results = self._search_proposals_keyword(
                query=query, source=source, dao_id=dao_id, state=state,
                start_date=start_date, end_date=end_date, limit=limit
            )
        
        return results
    
    def _search_proposals_by_title(
        self,
        query: str,
        source: Optional[str],
        dao_id: Optional[str],
        state: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Search proposals by title using keyword/ILIKE matching.
        
        Used for proposal ID queries like BIP-821, AIP-123, etc.
        Fast and exact - no embedding generation needed.
        """
        safe_query = query.replace("'", "''").strip()
        
        # Build WHERE clause - exact title match first, then pattern match
        where_parts = [f"(p.title ILIKE '%{safe_query}%' OR p.title ~* '\\[?{safe_query}\\]?')"]
        
        if source:
            where_parts.append(f"p.source = '{source}'")
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            # For Tally, dao_id in unified_proposals is the slug, but users may provide org_id
            where_parts.append(f"""(
                p.dao_id = '{safe_dao}' 
                OR p.dao_id ILIKE '%{safe_dao}%'
                OR (p.source = 'tally' AND p.dao_id IN (
                    SELECT DISTINCT slug FROM tally.tally_data WHERE org_id::text = '{safe_dao}'
                ))
            )""")
        if state:
            where_parts.append(f"LOWER(p.state) = LOWER('{state}')")
        
        where_clause = " AND ".join(where_parts)
        
        sql = f"""
        SELECT 
            p.proposal_id,
            p.dao_id,
            p.title,
            LEFT(p.body, 500) as body,
            p.source,
            p.state,
            p.created_at,
            p.ends_at,
            p.choices,
            p.scores,
            p.topic_id as discourse_topic_id,
            p.link,
            0.1 as distance
        FROM internal.unified_proposal_embeddings p
        WHERE {where_clause}
        ORDER BY 
            CASE WHEN p.title ILIKE '{safe_query}%' THEN 0 ELSE 1 END,
            p.created_at DESC
        LIMIT {limit}
        """
        
        logger.info(f"[ResearchDB] Title search for '{query}' (source={source}, dao={dao_id})...")
        return self.execute_query(sql)
    
    def _search_proposals_by_date(
        self,
        source: Optional[str],
        dao_id: Optional[str],
        state: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Get latest proposals ordered by date (no semantic search).
        
        Used when user asks for "latest", "recent", or "most recent" proposals
        without a specific topic query.
        """
        where_parts = []
        if source:
            where_parts.append(f"p.source = '{source}'")
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            # For Tally, the dao_id in unified_proposals is the slug, but users may provide org_id
            # Match directly on dao_id (slug) OR via tally.tally_data.org_id for Tally proposals
            where_parts.append(f"""(
                p.dao_id = '{safe_dao}' 
                OR p.dao_id ILIKE '%{safe_dao}%'
                OR (p.source = 'tally' AND p.dao_id IN (
                    SELECT DISTINCT slug FROM tally.tally_data WHERE org_id::text = '{safe_dao}'
                ))
            )""")
        if state:
            where_parts.append(f"LOWER(p.state) = LOWER('{state}')")
        
        start_iso = parse_date_to_iso(start_date)
        end_iso = parse_date_to_iso(end_date)
        if start_iso:
            where_parts.append(f"p.created_at >= '{start_iso}'")
        if end_iso:
            where_parts.append(f"p.created_at <= '{end_iso}'")
        
        where_clause = " AND ".join(where_parts) if where_parts else "TRUE"
        
        sql = f"""
        SELECT 
            p.proposal_id,
            p.dao_id,
            p.title,
            LEFT(p.body, 500) as body,
            p.source,
            p.state,
            p.created_at,
            p.ends_at,
            p.choices,
            p.scores,
            p.topic_id as discourse_topic_id,
            p.link,
            0 as distance
        FROM internal.unified_proposal_embeddings p
        WHERE {where_clause}
        ORDER BY p.created_at DESC
        LIMIT {limit}
        """
        
        logger.info(f"[ResearchDB] Latest proposals by date for source={source}, dao={dao_id}...")
        return self.execute_query(sql)
    
    def _search_proposals_keyword(
        self,
        query: str,
        source: Optional[str],
        dao_id: Optional[str],
        state: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Keyword fallback search on snapshot.proposallist and internal.unified_proposal_embeddings.
        
        Used when semantic search returns no results.
        """
        safe_query = query.replace("'", "''") if query else ""
        keywords = safe_query.split()[:5]
        
        keyword_conditions = []
        for kw in keywords:
            keyword_conditions.append(f"(p.title ILIKE '%{kw}%' OR p.body ILIKE '%{kw}%')")
        keyword_where = " AND ".join(keyword_conditions) if keyword_conditions else "TRUE"
        
        # Search on unified_proposals (has all sources)
        where_parts = [keyword_where]
        if source:
            where_parts.append(f"p.source = '{source}'")
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            # For Tally, dao_id in unified_proposals is the slug, but users may provide org_id
            where_parts.append(f"""(
                p.dao_id = '{safe_dao}' 
                OR p.dao_id ILIKE '%{safe_dao}%'
                OR (p.source = 'tally' AND p.dao_id IN (
                    SELECT DISTINCT slug FROM tally.tally_data WHERE org_id::text = '{safe_dao}'
                ))
            )""")
        if state:
            where_parts.append(f"LOWER(p.state) = LOWER('{state}')")
        
        start_iso = parse_date_to_iso(start_date)
        end_iso = parse_date_to_iso(end_date)
        if start_iso:
            where_parts.append(f"p.created_at >= '{start_iso}'")
        if end_iso:
            where_parts.append(f"p.created_at <= '{end_iso}'")
        
        where_clause = " AND ".join(where_parts)
        
        sql = f"""
        SELECT 
            p.proposal_id,
            p.dao_id,
            p.title,
            LEFT(p.body, 500) as body,
            p.source,
            p.state,
            p.created_at,
            p.ends_at,
            p.choices,
            p.scores,
            p.topic_id as discourse_topic_id,
            p.link,
            0.5 as distance
        FROM internal.unified_proposal_embeddings p
        WHERE {where_clause}
        ORDER BY p.created_at DESC
        LIMIT {limit}
        """
        
        logger.info(f"[ResearchDB] Keyword proposal search for: {query[:100] if query else 'governance'}...")
        return self.execute_query(sql)
    
    def search_discourse(
        self,
        query: Optional[str] = None,
        dao_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
        embedding_profile: EmbeddingProfile = EmbeddingProfile.GEMINI_3072,  # 3072-dim for discourse
    ) -> List[Dict[str, Any]]:
        """Search DAO forum discussions from Discourse platforms using semantic search.
        
        PURPOSE: Find forum discussions where DAOs debate proposals, share ideas,
        and coordinate. Discourse forums are the primary place for governance
        discussions BEFORE formal proposals are created. Use this to:
        - Research community sentiment on topics
        - Find pre-proposal discussions and temperature checks
        - Understand the reasoning behind governance decisions
        - Track delegate and community member contributions
        
        TABLES:
        - discourse.discourse_embeddings_3072: 14,828 rows with 3072-dim semantic embeddings
        - discourse.posts: Full forum posts (keyword fallback)
        
        Args:
            query: Search query (e.g., "delegate incentives", "security concerns").
                   If None or empty, returns latest posts ordered by date.
            dao_id: Filter by DAO identifier (e.g., 'uniswap', 'arbitrum', etc.)
            topic_id: Filter by specific topic thread
            start_date: Filter posts created after this date (YYYY-MM-DD)
            end_date: Filter posts created before this date (YYYY-MM-DD)
            limit: Maximum results
            embedding_profile: Embedding profile (default: GEMINI_3072 for discourse)
        """
        # If no query provided, return latest posts by date (no semantic search)
        if not query or not query.strip():
            logger.info("[ResearchDB] No query provided, returning latest discourse posts by date")
            return self._search_discourse_by_date(
                dao_id=dao_id, topic_id=topic_id,
                start_date=start_date, end_date=end_date, limit=limit
            )
        
        # For proposal ID queries (BIP-821, AIP-123), try title search first
        if is_proposal_id_query(query):
            logger.info(f"[ResearchDB] Detected proposal ID query '{query}', trying discourse title search first")
            title_results = self._search_discourse_by_title(
                query=query, dao_id=dao_id, limit=limit
            )
            if title_results:
                logger.info(f"[ResearchDB] Found {len(title_results)} discourse topics by title match")
                return title_results
            logger.info("[ResearchDB] No title matches, falling back to semantic search")
        
        # Try semantic search first on discourse.discourse_embeddings_3072
        results = self._search_discourse_semantic(
            query=query,
            dao_id=dao_id,
            topic_id=topic_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            embedding_profile=embedding_profile,
        )
        
        # Fall back to keyword search if no results
        if not results:
            logger.info("[ResearchDB] No semantic results, falling back to keyword search")
            results = self._search_discourse_keyword(
                query=query,
                dao_id=dao_id,
                topic_id=topic_id,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
        
        return results
    
    def _search_discourse_semantic(
        self,
        query: str,
        dao_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
        embedding_profile: EmbeddingProfile = EmbeddingProfile.GEMINI_3072,
    ) -> List[Dict[str, Any]]:
        """Semantic search on discourse.discourse_embeddings_3072 using 3072-dim vectors.
        
        Primary search method for discourse with embedding coverage.
        """
        # Generate query embedding with 3072-dim model
        query_embedding = self.generate_embedding(query, profile=embedding_profile)
        if not query_embedding:
            logger.warning("[ResearchDB] Failed to generate discourse embedding")
            return []
        
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"
        
        where_parts = ["e.embedding IS NOT NULL"]
        
        # DAO filter - dao_id in discourse_embeddings_3072 is text like 'uniswap', 'arbitrum'
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            # Strip common suffixes like .eth for matching
            clean_dao = safe_dao.lower().replace('.eth', '').replace('governance', '').strip()
            where_parts.append(f"(LOWER(e.dao_id) = LOWER('{safe_dao}') OR LOWER(e.dao_id) LIKE '%{clean_dao}%')")
        
        if topic_id:
            where_parts.append(f"e.topic_id = '{topic_id}'")
        
        # Date filtering
        start_iso = parse_date_to_iso(start_date)
        end_iso = parse_date_to_iso(end_date)
        if start_iso:
            where_parts.append(f"e.created_at >= '{start_iso}'")
        if end_iso:
            where_parts.append(f"e.created_at <= '{end_iso}'")
        
        where_clause = " AND ".join(where_parts)
        
        sql = f"""
        SELECT DISTINCT ON (e.topic_id)
            e.topic_id,
            e.topic_title,
            e.dao_id,
            e.index,
            e.created_at,
            LEFT(e.content, 500) as content,
            e.embedding <=> '{embedding_str}'::vector(3072) as distance
        FROM discourse.discourse_embeddings_3072 e
        WHERE {where_clause}
        ORDER BY e.topic_id, e.embedding <=> '{embedding_str}'::vector(3072)
        LIMIT {limit * 2}
        """
        
        logger.info(f"[ResearchDB] Discourse semantic search for: {query[:50] if query else 'all'}...")
        
        # Execute and re-sort by distance
        results = self.execute_query(sql)
        
        # Sort by distance (semantic relevance) and limit
        results.sort(key=lambda x: x.get("distance", 999))
        return results[:limit]
    
    def _search_discourse_by_title(
        self,
        query: str,
        dao_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search discourse topics by title using ILIKE matching.
        
        Used for proposal ID queries like BIP-821, AIP-123, etc.
        """
        safe_query = query.replace("'", "''").strip()
        
        dao_join = "LEFT JOIN internal.daos d ON p.dao_id = d.id"
        
        where_parts = [f"(p.topic_title ILIKE '%{safe_query}%')"]
        
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            if safe_dao.isdigit():
                where_parts.append(f"d.id = {safe_dao}")
            else:
                where_parts.append(f"""(
                    LOWER(d.name) = LOWER('{safe_dao}')
                    OR LOWER(d.snapshot_id) = LOWER('{safe_dao}')
                    OR LOWER(d.tally_id) = LOWER('{safe_dao}')
                )""")
        
        where_clause = " AND ".join(where_parts)
        
        sql = f"""
        SELECT DISTINCT ON (p.topic_id)
            p.id::text as id,
            p.topic_title as title,
            LEFT(p.raw, 500) as content,
            'discourse' as source,
            COALESCE(d.snapshot_id, d.name, 'unknown') as dao_id,
            p.topic_id::text,
            p.created_at,
            0.1 as distance
        FROM discourse.posts p
        {dao_join}
        WHERE {where_clause}
        ORDER BY p.topic_id, p.created_at ASC
        LIMIT {limit}
        """
        
        logger.info(f"[ResearchDB] Discourse title search for '{query}'...")
        return self.execute_query(sql)
    
    def _search_discourse_keyword(
        self,
        query: str,
        dao_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Keyword search on discourse.posts.
        
        Joins with internal.daos to resolve DAO names like 'Arbitrum', 'gnosis.eth', etc.
        Primary search method since discourse embeddings are limited.
        """
        safe_query = query.replace("'", "''") if query else ""
        keywords = safe_query.split()[:5]
        
        # Build keyword conditions
        keyword_conditions = []
        for kw in keywords:
            keyword_conditions.append(f"(p.topic_title ILIKE '%{kw}%' OR p.raw ILIKE '%{kw}%')")
        keyword_where = " AND ".join(keyword_conditions) if keyword_conditions else "TRUE"
        
        where_parts = [keyword_where]
        
        # DAO filter - join with internal.daos to resolve names
        dao_join = "LEFT JOIN internal.daos d ON p.dao_id = d.id"
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            # Check if dao_id is a numeric ID
            if safe_dao.isdigit():
                # Direct match on internal.daos.id
                where_parts.append(f"d.id = {safe_dao}")
            else:
                # Match on name, snapshot_id, or tally_id (case-insensitive)
                where_parts.append(f"""(
                    LOWER(d.name) = LOWER('{safe_dao}')
                    OR LOWER(d.snapshot_id) = LOWER('{safe_dao}')
                    OR LOWER(d.tally_id) = LOWER('{safe_dao}')
                    OR d.name ILIKE '%{safe_dao}%'
                )""")
        
        if topic_id:
            where_parts.append(f"p.topic_id = {topic_id}")
        
        # Date filtering
        start_iso = parse_date_to_iso(start_date)
        end_iso = parse_date_to_iso(end_date)
        if start_iso:
            where_parts.append(f"p.created_at >= '{start_iso}'")
        if end_iso:
            where_parts.append(f"p.created_at <= '{end_iso}'")
        
        where_clause = " AND ".join(where_parts)
        
        # Select distinct topics to avoid duplicate posts from same thread
        sql = f"""
        SELECT DISTINCT ON (p.topic_id)
            p.topic_id::text as topic_id,
            p.topic_title,
            COALESCE(d.name, d.snapshot_id, 'unknown') as dao_id,
            0 as index,
            p.created_at,
            LEFT(p.raw, 500) as content
        FROM discourse.posts p
        {dao_join}
        WHERE {where_clause}
        ORDER BY p.topic_id, p.created_at DESC
        LIMIT {limit}
        """
        
        logger.info(f"[ResearchDB] Discourse keyword search for: {query[:50] if query else 'all'}...")
        return self.execute_query(sql)
    
    def _search_discourse_by_date(
        self,
        dao_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get latest discourse posts ordered by date (no semantic search).
        
        Used when user asks for "latest" or "recent" posts without a specific query.
        """
        where_parts = []
        
        # DAO filter - join with internal.daos to resolve names
        dao_join = "LEFT JOIN internal.daos d ON p.dao_id = d.id"
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            # Check if dao_id is a numeric ID
            if safe_dao.isdigit():
                where_parts.append(f"d.id = {safe_dao}")
            else:
                # Match on name, snapshot_id, or tally_id (case-insensitive)
                where_parts.append(f"""(
                    LOWER(d.name) = LOWER('{safe_dao}')
                    OR LOWER(d.snapshot_id) = LOWER('{safe_dao}')
                    OR LOWER(d.tally_id) = LOWER('{safe_dao}')
                    OR d.name ILIKE '%{safe_dao}%'
                )""")
        
        if topic_id:
            where_parts.append(f"p.topic_id = {topic_id}")
        
        # Date filtering
        start_iso = parse_date_to_iso(start_date)
        end_iso = parse_date_to_iso(end_date)
        if start_iso:
            where_parts.append(f"p.created_at >= '{start_iso}'")
        if end_iso:
            where_parts.append(f"p.created_at <= '{end_iso}'")
        
        where_clause = " AND ".join(where_parts) if where_parts else "TRUE"
        
        sql = f"""
        SELECT DISTINCT ON (p.topic_id)
            p.topic_id::text as topic_id,
            p.topic_title,
            COALESCE(d.name, d.snapshot_id, 'unknown') as dao_id,
            0 as index,
            p.created_at,
            LEFT(p.raw, 500) as content
        FROM discourse.posts p
        {dao_join}
        WHERE {where_clause}
        ORDER BY p.topic_id, p.created_at DESC
        LIMIT {limit}
        """
        
        logger.info(f"[ResearchDB] Latest discourse posts by date for dao={dao_id}...")
        return self.execute_query(sql)
    
    def search_telegram(
        self,
        query: str,
        dao_id: Optional[str] = None,  # String - matches telegram.telegram_conceptual_embeddings_3072 schema
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
        embedding_profile: EmbeddingProfile = EmbeddingProfile.GEMINI_3072,  # 3072-dim
    ) -> List[Dict[str, Any]]:
        """Search DAO Telegram group discussions using telegram.telegram_conceptual_embeddings_3072.
        
        PURPOSE: Find real-time community discussions from Telegram groups.
        Telegram is often used for more informal, rapid communication compared
        to forums. Use this to:
        - Gauge community sentiment and reactions
        - Find discussions about recent events or announcements
        - Track informal coordination and planning
        - Identify emerging topics before they reach forums
        
        TABLES:
        - telegram.telegram_conceptual_embeddings_3072: 31,968 rows with 3072-dim embeddings
        
        CONTENT: Aggregated and summarized Telegram messages organized by topic
        and time window (conceptual embeddings group related messages together).
        
        Args:
            query: Semantic search query (e.g., "token launch", "airdrop concerns")
            dao_id: Filter by DAO identifier (string like 'near', 'curve.eth', etc.)
            start_date: Filter messages after this date (YYYY-MM-DD)
            end_date: Filter messages before this date (YYYY-MM-DD)
            limit: Maximum results
            embedding_profile: Embedding model - default GEMINI_3072 for unified_telegram
        """
        where_parts = []
        
        if dao_id:
            safe_dao = str(dao_id).replace("'", "''")
            where_parts.append(f"(dao_id = '{safe_dao}' OR dao_id ILIKE '%{safe_dao}%')")
        
        # Date filtering using unix timestamps
        start_ts = parse_date_to_timestamp(start_date)
        end_ts = parse_date_to_timestamp(end_date)
        if start_ts:
            where_parts.append(f"start_unix >= {start_ts}")
        if end_ts:
            where_parts.append(f"end_unix <= {end_ts}")
        
        where_clause = " AND ".join(where_parts) if where_parts else ""
        
        return self.semantic_search(
            table="telegram.telegram_conceptual_embeddings_3072",
            query=query,
            select_columns="dao_id, window_number, topic_id, topic_title, content, aggregated_messages, start_unix, end_unix",
            where_clause=where_clause,
            limit=limit,
            embedding_profile=embedding_profile,
        )
    
    def search_discord(
        self,
        query: str,
        dao_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10,
        embedding_profile: EmbeddingProfile = EmbeddingProfile.TEXT_768,
    ) -> List[Dict[str, Any]]:
        """Search DAO Discord server discussions using internal.unified_discord.
        
        PURPOSE: Find community discussions from Discord servers. Discord is the
        primary community hub for most DAOs, with channels for governance,
        development, support, and general chat. Use this to:
        - Research community discussions and sentiment
        - Find technical discussions and support threads
        - Track announcements and community reactions
        - Identify active contributors and their perspectives
        
        TABLES:
        - internal.unified_discord: 2,163 rows with 768-dim embeddings
        
        CONTENT: Aggregated Discord messages organized by date + time windows.
        Content is stored as JSON/JSONB with message summaries.
        
        Args:
            query: Semantic search query (e.g., "bug report", "feature request")
            dao_id: Filter by DAO identifier (string like 'near', 'curve.eth', etc.)
            start_date: Filter messages after this date (YYYY-MM-DD)
            end_date: Filter messages before this date (YYYY-MM-DD)
            limit: Maximum results
            embedding_profile: Embedding model - default TEXT_768 for unified_discord
        """
        where_parts = []
        
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            where_parts.append(f"(dao_id = '{safe_dao}' OR dao_id ILIKE '%{safe_dao}%')")
        
        # Date filtering - unified_discord uses date column + unix timestamps
        start_ts = parse_date_to_timestamp(start_date)
        end_ts = parse_date_to_timestamp(end_date)
        if start_ts:
            where_parts.append(f"start_unix >= {start_ts}")
        if end_ts:
            where_parts.append(f"end_unix <= {end_ts}")
        
        where_clause = " AND ".join(where_parts) if where_parts else ""
        
        return self.semantic_search(
            table="internal.unified_discord",
            query=query,
            select_columns="dao_id, date, content_summary, start_unix, end_unix",
            where_clause=where_clause,
            limit=limit,
            embedding_profile=embedding_profile,
        )
    
    def search_votes(
        self,
        proposal_id: Optional[str] = None,
        voter: Optional[str] = None,
        dao_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Search individual votes cast on Snapshot proposals.
        
        PURPOSE: Find how specific addresses voted on proposals. Use this to:
        - Analyze delegate voting patterns and consistency
        - Research voting power distribution
        - Find voting reasons/rationales (when provided)
        - Track participation of specific wallets
        - Calculate delegate rewards based on participation
        
        CONTENT: Individual vote records from Snapshot including voter address,
        choice (can be multiple for ranked choice), voting power (VP), and
        optional reason text explaining the vote.
        
        NOTE: No semantic search - uses direct filtering only.
        
        Args:
            proposal_id: Filter by specific proposal ID
            voter: Filter by voter wallet address (case-insensitive)
            dao_id: Filter by DAO identifier (Snapshot space name)
            start_date: Filter votes cast after this date (YYYY-MM-DD)
            end_date: Filter votes cast before this date (YYYY-MM-DD)
            limit: Maximum results (default 50 for vote queries)
        """
        where_parts = []
        
        if proposal_id:
            where_parts.append(f"proposal = '{proposal_id}'")
        if voter:
            where_parts.append(f"LOWER(voter) = LOWER('{voter}')")
        if dao_id:
            where_parts.append(f"space = '{dao_id}'")
        
        # Date filtering using unix timestamps (created is numeric)
        start_ts = parse_date_to_timestamp(start_date)
        end_ts = parse_date_to_timestamp(end_date)
        if start_ts:
            where_parts.append(f"created >= {start_ts}")
        if end_ts:
            where_parts.append(f"created <= {end_ts}")
        
        where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        sql = f"""
        SELECT vote_id, voter, proposal, choice, vp, created, space as dao_id, reason
        FROM snapshot.votelist
        {where_clause}
        ORDER BY created DESC
        LIMIT {limit}
        """
        
        return self.execute_query(sql)
    
    def get_voter_stats(
        self,
        voter: str,
        dao_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get aggregated voting statistics for a specific voter/delegate.
        
        PURPOSE: Analyze delegate activity and voting patterns. Use this to:
        - Measure participation rates
        - Track total voting power used
        - Identify DAOs participated in
        - Analyze voting choice patterns
        
        Args:
            voter: Voter wallet address (required)
            dao_id: Filter to specific DAO
            start_date: Filter votes after this date (YYYY-MM-DD)
            end_date: Filter votes before this date (YYYY-MM-DD)
        """
        where_parts = [f"LOWER(voter) = LOWER('{voter}')"]
        
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            where_parts.append(f"space = '{safe_dao}'")
        
        start_ts = parse_date_to_timestamp(start_date)
        end_ts = parse_date_to_timestamp(end_date)
        if start_ts:
            where_parts.append(f"created >= {start_ts}")
        if end_ts:
            where_parts.append(f"created <= {end_ts}")
        
        where_clause = " WHERE " + " AND ".join(where_parts)
        
        # Summary stats
        summary_sql = f"""
        SELECT 
            COUNT(*) as total_votes,
            COALESCE(SUM(vp), 0) as total_vp,
            COUNT(DISTINCT space) as daos_count,
            MIN(created) as first_vote,
            MAX(created) as last_vote
        FROM snapshot.votelist
        {where_clause}
        """
        summary = self.execute_query(summary_sql)
        
        # DAOs participated in
        daos_sql = f"""
        SELECT space as dao_id, COUNT(*) as vote_count, SUM(vp) as total_vp
        FROM snapshot.votelist
        {where_clause}
        GROUP BY space
        ORDER BY vote_count DESC
        LIMIT 10
        """
        daos = self.execute_query(daos_sql)
        
        # Choice patterns (simplified - assumes numeric choices 1=For, 2=Against, 3=Abstain)
        choices_sql = f"""
        SELECT 
            choice::text as choice_raw,
            COUNT(*) as count
        FROM snapshot.votelist
        {where_clause}
        GROUP BY choice::text
        ORDER BY count DESC
        LIMIT 5
        """
        choices = self.execute_query(choices_sql)
        
        # Recent votes
        recent_sql = f"""
        SELECT proposal, space as dao_id, choice, vp, created, reason
        FROM snapshot.votelist
        {where_clause}
        ORDER BY created DESC
        LIMIT 5
        """
        recent = self.execute_query(recent_sql)
        
        return {
            "total_votes": summary[0]["total_votes"] if summary else 0,
            "total_vp": float(summary[0]["total_vp"]) if summary else 0,
            "daos_count": summary[0]["daos_count"] if summary else 0,
            "first_vote": summary[0]["first_vote"] if summary else None,
            "last_vote": summary[0]["last_vote"] if summary else None,
            "daos": daos,
            "choice_patterns": choices,
            "recent_votes": recent,
        }
    
    def get_proposal_vote_stats(
        self,
        proposal_id: str,
        dao_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get detailed voting statistics for a specific proposal.
        
        PURPOSE: Analyze voting breakdown and participation for a proposal. Use to:
        - Get vote counts and VP breakdown by choice
        - Find top voters
        - Calculate participation vs quorum
        - Understand VP distribution
        
        Args:
            proposal_id: Proposal ID (required)
            dao_id: DAO identifier (optional, helps narrow search)
        """
        where_parts = [f"proposal = '{proposal_id}'"]
        
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            where_parts.append(f"space = '{safe_dao}'")
        
        where_clause = " WHERE " + " AND ".join(where_parts)
        
        # Summary stats
        summary_sql = f"""
        SELECT 
            COUNT(*) as total_voters,
            COALESCE(SUM(vp), 0) as total_vp,
            AVG(vp) as avg_vp,
            MAX(vp) as max_vp,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY vp) as median_vp
        FROM snapshot.votelist
        {where_clause}
        """
        summary = self.execute_query(summary_sql)
        
        # Vote breakdown by choice
        breakdown_sql = f"""
        SELECT 
            choice::text as choice_raw,
            COUNT(*) as voter_count,
            SUM(vp) as total_vp
        FROM snapshot.votelist
        {where_clause}
        GROUP BY choice::text
        ORDER BY total_vp DESC
        """
        breakdown = self.execute_query(breakdown_sql)
        
        # Top voters
        top_voters_sql = f"""
        SELECT voter, choice, vp, reason
        FROM snapshot.votelist
        {where_clause}
        ORDER BY vp DESC
        LIMIT 10
        """
        top_voters = self.execute_query(top_voters_sql)
        
        return {
            "total_voters": summary[0]["total_voters"] if summary else 0,
            "total_vp": float(summary[0]["total_vp"]) if summary else 0,
            "avg_vp": float(summary[0]["avg_vp"]) if summary and summary[0]["avg_vp"] else 0,
            "max_vp": float(summary[0]["max_vp"]) if summary and summary[0]["max_vp"] else 0,
            "median_vp": float(summary[0]["median_vp"]) if summary and summary[0]["median_vp"] else 0,
            "vote_breakdown": breakdown,
            "top_voters": top_voters,
        }
    
    def get_voting_power_trends(
        self,
        voter: str,
        dao_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Track voting power changes over time for a voter.
        
        PURPOSE: Analyze how a voter's VP has changed. Use this to:
        - Track delegation changes
        - Identify VP growth/decline trends
        - Compare current vs historical VP
        
        Args:
            voter: Voter wallet address (required)
            dao_id: Filter to specific DAO
            start_date: Start of period (default: 6 months ago)
            end_date: End of period
        """
        where_parts = [f"LOWER(voter) = LOWER('{voter}')"]
        
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            where_parts.append(f"space = '{safe_dao}'")
        
        start_ts = parse_date_to_timestamp(start_date)
        end_ts = parse_date_to_timestamp(end_date)
        if start_ts:
            where_parts.append(f"created >= {start_ts}")
        if end_ts:
            where_parts.append(f"created <= {end_ts}")
        
        where_clause = " WHERE " + " AND ".join(where_parts)
        
        # VP over time (each vote)
        votes_sql = f"""
        SELECT 
            proposal,
            space as dao_id,
            vp,
            created,
            TO_TIMESTAMP(created) as vote_date
        FROM snapshot.votelist
        {where_clause}
        ORDER BY created ASC
        """
        votes = self.execute_query(votes_sql)
        
        # Monthly aggregates
        monthly_sql = f"""
        SELECT 
            DATE_TRUNC('month', TO_TIMESTAMP(created)) as month,
            COUNT(*) as vote_count,
            AVG(vp) as avg_vp,
            MAX(vp) as max_vp
        FROM snapshot.votelist
        {where_clause}
        GROUP BY DATE_TRUNC('month', TO_TIMESTAMP(created))
        ORDER BY month DESC
        LIMIT 12
        """
        monthly = self.execute_query(monthly_sql)
        
        # First and last VP
        first_vp = votes[0]["vp"] if votes else None
        last_vp = votes[-1]["vp"] if votes else None
        
        # Calculate change
        vp_change_pct = None
        if first_vp and last_vp and first_vp > 0:
            vp_change_pct = ((last_vp - first_vp) / first_vp) * 100
        
        return {
            "votes": votes,
            "monthly_trends": monthly,
            "first_vp": float(first_vp) if first_vp else None,
            "last_vp": float(last_vp) if last_vp else None,
            "vp_change_pct": vp_change_pct,
            "total_votes": len(votes),
        }
    
    def get_voting_power_trends_multi(
        self,
        voters: List[str],
        dao_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Track voting power changes over time for multiple voters.
        
        PURPOSE: Compare VP trends across multiple delegates. Use this to:
        - Compare delegation changes across voters
        - Analyze VP distribution trends
        - Track multiple delegates simultaneously
        
        Args:
            voters: List of voter wallet addresses (required)
            dao_id: Filter to specific DAO
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Dict mapping each voter address to their voting power trends
        """
        if not voters:
            return {}
        
        # Sanitize addresses and build IN clause (case-insensitive)
        safe_voters = [v.replace("'", "''").strip().lower() for v in voters if v.strip()]
        if not safe_voters:
            return {}
        
        voters_in = ", ".join(f"LOWER('{v}')" for v in safe_voters)
        
        where_parts = [f"LOWER(voter) IN ({voters_in})"]
        
        if dao_id:
            safe_dao = dao_id.replace("'", "''")
            where_parts.append(f"space = '{safe_dao}'")
        
        start_ts = parse_date_to_timestamp(start_date)
        end_ts = parse_date_to_timestamp(end_date)
        if start_ts:
            where_parts.append(f"created >= {start_ts}")
        if end_ts:
            where_parts.append(f"created <= {end_ts}")
        
        where_clause = " WHERE " + " AND ".join(where_parts)
        
        # Get all votes for all voters, including voter address
        votes_sql = f"""
        SELECT 
            voter,
            proposal,
            space as dao_id,
            vp,
            created,
            TO_TIMESTAMP(created) as vote_date
        FROM snapshot.votelist
        {where_clause}
        ORDER BY voter, created ASC
        """
        all_votes = self.execute_query(votes_sql)
        
        # Get monthly aggregates per voter
        monthly_sql = f"""
        SELECT 
            voter,
            DATE_TRUNC('month', TO_TIMESTAMP(created)) as month,
            COUNT(*) as vote_count,
            AVG(vp) as avg_vp,
            MAX(vp) as max_vp
        FROM snapshot.votelist
        {where_clause}
        GROUP BY voter, DATE_TRUNC('month', TO_TIMESTAMP(created))
        ORDER BY voter, month DESC
        """
        all_monthly = self.execute_query(monthly_sql)
        
        # Group results by voter (case-insensitive key)
        results: Dict[str, Dict[str, Any]] = {}
        
        # Initialize all requested voters
        for v in voters:
            v_lower = v.strip().lower()
            results[v_lower] = {
                "voter": v.strip(),
                "votes": [],
                "monthly_trends": [],
                "first_vp": None,
                "last_vp": None,
                "vp_change_pct": None,
                "total_votes": 0,
            }
        
        # Distribute votes to each voter
        for vote in all_votes:
            voter_key = vote.get("voter", "").lower()
            if voter_key in results:
                results[voter_key]["votes"].append(vote)
        
        # Distribute monthly data to each voter
        for month_data in all_monthly:
            voter_key = month_data.get("voter", "").lower()
            if voter_key in results:
                results[voter_key]["monthly_trends"].append(month_data)
        
        # Calculate stats for each voter
        for voter_key, data in results.items():
            votes = data["votes"]
            data["total_votes"] = len(votes)
            
            if votes:
                data["first_vp"] = float(votes[0]["vp"]) if votes[0].get("vp") else None
                data["last_vp"] = float(votes[-1]["vp"]) if votes[-1].get("vp") else None
                
                if data["first_vp"] and data["last_vp"] and data["first_vp"] > 0:
                    data["vp_change_pct"] = ((data["last_vp"] - data["first_vp"]) / data["first_vp"]) * 100
            
            # Limit monthly trends to 12
            data["monthly_trends"] = data["monthly_trends"][:12]
        
        return results
    
    def get_top_voters(
        self,
        dao_id: str,
        metric: str = "votes",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Get top voters/delegates for a DAO.
        
        PURPOSE: Find the most active or powerful voters. Use this to:
        - Identify key delegates
        - Analyze governance concentration
        - Track delegate leaderboards
        
        Args:
            dao_id: DAO identifier (required)
            metric: Ranking metric - "votes" (count), "voting_power" (total VP)
            start_date: Filter votes after this date
            end_date: Filter votes before this date
            limit: Number of top voters to return
        """
        safe_dao = dao_id.replace("'", "''")
        where_parts = [f"space = '{safe_dao}'"]
        
        start_ts = parse_date_to_timestamp(start_date)
        end_ts = parse_date_to_timestamp(end_date)
        if start_ts:
            where_parts.append(f"created >= {start_ts}")
        if end_ts:
            where_parts.append(f"created <= {end_ts}")
        
        where_clause = " WHERE " + " AND ".join(where_parts)
        
        # Get total for percentage calculation
        total_sql = f"""
        SELECT COUNT(*) as total_votes, SUM(vp) as total_vp
        FROM snapshot.votelist
        {where_clause}
        """
        totals = self.execute_query(total_sql)
        total_votes = totals[0]["total_votes"] if totals else 0
        total_vp = float(totals[0]["total_vp"]) if totals and totals[0]["total_vp"] else 0
        
        # Order by selected metric
        # Supported metrics: votes, voting_power, avg_vp, tenure
        metric_order_map = {
            "votes": "vote_count DESC",
            "voting_power": "latest_vp DESC",
            "avg_vp": "avg_vp DESC",
            "tenure": "first_vote ASC",  # Oldest first = longest tenure
        }
        order_by = metric_order_map.get(metric, "latest_vp DESC")
        
        # Use CTEs to get latest VP and first VP for each voter
        top_sql = f"""
        WITH voter_stats AS (
            SELECT 
                voter,
                COUNT(*) as vote_count,
                SUM(vp) as cumulative_vp,
                AVG(vp) as avg_vp,
                MIN(created) as first_vote,
                MAX(created) as last_vote
            FROM snapshot.votelist
            {where_clause}
            GROUP BY voter
        ),
        latest_vp_cte AS (
            SELECT DISTINCT ON (voter)
                voter,
                vp as latest_vp
            FROM snapshot.votelist
            {where_clause}
            ORDER BY voter, created DESC
        ),
        first_vp_cte AS (
            SELECT DISTINCT ON (voter)
                voter,
                vp as first_vp
            FROM snapshot.votelist
            {where_clause}
            ORDER BY voter, created ASC
        )
        SELECT 
            vs.voter,
            vs.vote_count,
            vs.cumulative_vp,
            vs.avg_vp,
            lv.latest_vp,
            fv.first_vp,
            vs.first_vote,
            vs.last_vote
        FROM voter_stats vs
        JOIN latest_vp_cte lv ON vs.voter = lv.voter
        JOIN first_vp_cte fv ON vs.voter = fv.voter
        ORDER BY {order_by}
        LIMIT {limit}
        """
        top_voters = self.execute_query(top_sql)
        
        # Calculate total latest VP for percentage (sum of all voters' current VP)
        total_latest_vp = sum(float(v.get("latest_vp", 0) or 0) for v in top_voters)
        
        # Add percentages and VP change calculation
        for v in top_voters:
            v["vote_pct"] = (int(v["vote_count"]) / int(total_votes) * 100) if total_votes > 0 else 0
            # Use latest_vp for percentage (represents current delegation)
            latest_vp = float(v.get("latest_vp", 0) or 0)
            v["vp_pct"] = (latest_vp / total_latest_vp * 100) if total_latest_vp > 0 else 0
            
            # Calculate VP change percentage (from first vote to latest vote)
            first_vp = float(v.get("first_vp", 0) or 0)
            if first_vp > 0:
                v["vp_change_pct"] = ((latest_vp - first_vp) / first_vp) * 100
            else:
                v["vp_change_pct"] = None
        
        return {
            "dao_id": dao_id,
            "total_votes": total_votes,
            "cumulative_vp": total_vp,  # Renamed from total_vp for clarity
            "total_latest_vp": total_latest_vp,  # Sum of current VPs
            "top_voters": top_voters,
            "metric": metric,
        }
    
    def batch_resolve_ens(
        self,
        addresses: List[str],
    ) -> Dict[str, Optional[str]]:
        """Batch resolve Ethereum addresses to ENS names.
        
        PURPOSE: Efficiently resolve multiple addresses to their ENS names in a single query.
        
        Args:
            addresses: List of Ethereum addresses (0x...)
            
        Returns:
            Dict mapping address (lowercase) -> ENS name (or None if no ENS)
        """
        if not addresses:
            return {}
        
        # Normalize and dedupe addresses
        normalized = list(set(addr.lower() for addr in addresses if addr and addr.startswith('0x')))
        if not normalized:
            return {}
        
        # Build SQL with IN clause for batch lookup
        placeholders = ", ".join(f"'{addr}'" for addr in normalized)
        sql = f"""
        SELECT LOWER(address) as address, name
        FROM dune.ens_labels
        WHERE LOWER(address) IN ({placeholders})
        AND name IS NOT NULL
        AND name != ''
        ORDER BY name
        """
        
        try:
            rows = self.execute_query(sql)
            result = {addr: None for addr in normalized}
            for row in rows:
                addr = row.get("address", "").lower()
                name = row.get("name")
                if addr and name:
                    result[addr] = name
            return result
        except Exception as e:
            logger.error(f"[ResearchDB] batch_resolve_ens error: {e}")
            return {addr: None for addr in normalized}
    
    def search_github(
        self,
        query: str,
        dao_id: Optional[int] = None,
        repo: Optional[str] = None,
        limit: int = 10,
        embedding_profile: EmbeddingProfile = EmbeddingProfile.GEMINI_3072,
    ) -> List[Dict[str, Any]]:
        """Search DAO GitHub repositories and their metadata.
        
        PURPOSE: Find GitHub repositories associated with DAOs. Use this to:
        - Discover DAO codebases and technical infrastructure
        - Find documentation and technical specs
        - Research development activity and contributors
        - Identify related projects and dependencies
        
        CONTENT: Repository metadata including description, README content,
        star/fork counts, and organization information. Useful for understanding
        what DAOs are building technically.
        
        Args:
            query: Semantic search query (e.g., "smart contracts", "SDK", "documentation")
            dao_id: Filter by DAO identifier (integer ID)
            repo: Filter by repository name (partial match)
            limit: Maximum results
            embedding_profile: Embedding model to use (3072-dim for GitHub)
        """
        where_parts = []
        
        if dao_id:
            where_parts.append(f"dao_id = {dao_id}")
        if repo:
            where_parts.append(f"repo_name ILIKE '%{repo}%'")
        
        where_clause = " AND ".join(where_parts) if where_parts else ""
        
        return self.semantic_search(
            table="github.github_metadata_3072",
            query=query,
            select_columns="dao_id, github_org, repo_name, full_name, description, html_url, stargazers_count, forks_count",
            where_clause=where_clause,
            limit=limit,
            embedding_profile=embedding_profile,
        )
    
    def search_github_commits(
        self,
        query: str,
        base_url: Optional[str] = None,
        limit: int = 10,
        embedding_profile: EmbeddingProfile = EmbeddingProfile.GEMINI_3072,
    ) -> List[Dict[str, Any]]:
        """Search GitHub commit messages and diffs.
        
        PURPOSE: Find specific code changes and commit history. Use this to:
        - Track development progress on specific features
        - Find when bugs were introduced or fixed
        - Research code changes related to governance or security
        - Identify contributors working on specific areas
        
        CONTENT: Commit messages and diff summaries, searchable semantically.
        
        Args:
            query: Semantic search query (e.g., "fix vulnerability", "add voting")
            base_url: Filter by repository base URL
            limit: Maximum results
            embedding_profile: Embedding model to use (768-dim)
        """
        where_parts = []
        
        if base_url:
            where_parts.append(f"base_url = '{base_url}'")
        
        where_clause = " AND ".join(where_parts) if where_parts else ""
        
        return self.semantic_search(
            table="github.github_commit_embeddings_3072",
            query=query,
            select_columns="base_url, sha, index, content",
            where_clause=where_clause,
            limit=limit,
            embedding_profile=embedding_profile,
        )
    
    def search_github_commits_daos(
        self,
        query: Optional[str] = None,
        dao_id: Optional[int] = None,
        author: Optional[str] = None,
        repo: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search GitHub commits for DAO repositories.
        
        PURPOSE: Find commits in DAO codebases. Use this to:
        - Track what DAOs have been working on
        - Find commits by specific authors
        - Search commit messages for topics
        - Analyze development activity over time
        
        Args:
            query: Keyword search in commit messages (optional)
            dao_id: Filter by DAO identifier (integer ID)
            author: Filter by author name or GitHub username
            repo: Filter by repository name (partial match)
            start_date: Filter commits after this date (YYYY-MM-DD)
            end_date: Filter commits before this date (YYYY-MM-DD)
            limit: Maximum results
        """
        where_parts = []
        
        if dao_id:
            where_parts.append(f"dao_id = {dao_id}")
        if author:
            safe_author = author.replace("'", "''")
            where_parts.append(f"(author_name ILIKE '%{safe_author}%' OR github_username ILIKE '%{safe_author}%')")
        if repo:
            safe_repo = repo.replace("'", "''")
            where_parts.append(f"repo_name ILIKE '%{safe_repo}%'")
        if start_date:
            where_parts.append(f"date >= '{start_date}'::timestamp")
        if end_date:
            where_parts.append(f"date <= '{end_date}'::timestamp")
        if query:
            safe_query = query.replace("'", "''")
            where_parts.append(f"message ILIKE '%{safe_query}%'")
        
        where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        sql = f"""
        SELECT 
            dao_id, github_org, repo_name, sha, message,
            author_name, github_username, date, html_url
        FROM github.github_commits_daos
        {where_clause}
        ORDER BY date DESC
        LIMIT {limit}
        """
        
        return self.execute_query(sql)
    
    def get_github_stats(
        self,
        dao_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get GitHub development statistics for a DAO.
        
        PURPOSE: Aggregate development metrics. Use this to:
        - Measure development activity (commit counts)
        - Identify top contributors
        - Find most active repositories
        - Track activity trends over time
        
        Args:
            dao_id: Filter by DAO identifier (integer ID)
            start_date: Filter commits after this date (YYYY-MM-DD)
            end_date: Filter commits before this date (YYYY-MM-DD)
            
        Returns:
            Dictionary with total_commits, unique_contributors, top_contributors, 
            active_repos, and weekly_commits
        """
        where_parts = []
        
        if dao_id:
            where_parts.append(f"dao_id = {dao_id}")
        if start_date:
            where_parts.append(f"date >= '{start_date}'::timestamp")
        if end_date:
            where_parts.append(f"date <= '{end_date}'::timestamp")
        
        where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        # Total commits and unique contributors
        summary_sql = f"""
        SELECT 
            COUNT(*) as total_commits,
            COUNT(DISTINCT COALESCE(github_username, author_name)) as unique_contributors
        FROM github.github_commits_daos
        {where_clause}
        """
        summary = self.execute_query(summary_sql)
        
        # Top contributors
        contributors_sql = f"""
        SELECT 
            COALESCE(github_username, author_name) as contributor,
            COUNT(*) as commit_count
        FROM github.github_commits_daos
        {where_clause}
        GROUP BY COALESCE(github_username, author_name)
        ORDER BY commit_count DESC
        LIMIT 10
        """
        top_contributors = self.execute_query(contributors_sql)
        
        # Most active repos
        repos_sql = f"""
        SELECT 
            repo_name,
            github_org,
            COUNT(*) as commit_count
        FROM github.github_commits_daos
        {where_clause}
        GROUP BY repo_name, github_org
        ORDER BY commit_count DESC
        LIMIT 5
        """
        active_repos = self.execute_query(repos_sql)
        
        # Weekly commit trend
        weekly_sql = f"""
        SELECT 
            DATE_TRUNC('week', date) as week,
            COUNT(*) as commits
        FROM github.github_commits_daos
        {where_clause}
        GROUP BY DATE_TRUNC('week', date)
        ORDER BY week DESC
        LIMIT 12
        """
        weekly_commits = self.execute_query(weekly_sql)
        
        return {
            "total_commits": summary[0]["total_commits"] if summary else 0,
            "unique_contributors": summary[0]["unique_contributors"] if summary else 0,
            "top_contributors": top_contributors,
            "active_repos": active_repos,
            "weekly_commits": weekly_commits,
        }
    
    def search_github_board(
        self,
        query: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search GitHub project board items.
        
        PURPOSE: Find roadmap and priority items. Use this to:
        - See what's planned (Backlog)
        - Track current work (In Progress)
        - Find completed items (Done)
        - Filter by priority (P0, P1)
        
        Args:
            query: Keyword search in item titles (optional)
            status: Filter by status (Backlog, In Progress, This Sprint, Done)
            priority: Filter by priority (P0, P1, etc.)
            limit: Maximum results
        """
        where_parts = []
        
        if query:
            safe_query = query.replace("'", "''")
            where_parts.append(f"title ILIKE '%{safe_query}%'")
        if status:
            safe_status = status.replace("'", "''")
            where_parts.append(f"status ILIKE '%{safe_status}%'")
        if priority:
            safe_priority = priority.replace("'", "''")
            where_parts.append(f"priority ILIKE '%{safe_priority}%'")
        
        where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        sql = f"""
        SELECT title, url, status, priority
        FROM github.github_board
        {where_clause}
        ORDER BY 
            CASE 
                WHEN priority = 'P0' THEN 1
                WHEN priority = 'P1' THEN 2
                ELSE 3
            END,
            title
        LIMIT {limit}
        """
        
        return self.execute_query(sql)
    
    def list_daos(
        self,
        name_filter: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List available DAOs and their identifiers.
        
        PURPOSE: Get the master list of DAOs tracked in the system. Use this to:
        - Find the correct DAO identifier for filtering other searches
        - Discover which DAOs are available in the database
        - Get cross-references between platforms (Snapshot ID, Tally ID, etc.)
        
        CONTENT: DAO registry with identifiers for different platforms:
        - id: Internal numeric identifier (used for telegram, github)
        - name: Human-readable DAO name
        - snapshot_id: Snapshot space identifier (used for proposals, votes)
        - tally_id: Tally organization identifier
        - discourse_url: URL to DAO's Discourse forum
        - coingecko_token_id: Token identifier for price data
        
        Args:
            name_filter: Filter DAOs by name (partial match, case-insensitive)
            limit: Maximum results
        """
        sql = """
        SELECT id, name, snapshot_id, tally_id, discourse_url, coingecko_token_id
        FROM internal.daos
        """
        
        if name_filter:
            sql += f" WHERE name ILIKE '%{name_filter}%'"
        
        sql += f" ORDER BY name LIMIT {limit}"
        
        return self.execute_query(sql)
