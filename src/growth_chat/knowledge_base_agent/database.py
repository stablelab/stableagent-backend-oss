"""
Database operations for Knowledge Hub queries.

Handles vector similarity search using pgvector for RAG-based knowledge retrieval.
"""
import json
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class KnowledgeDatabase:
    """Database interface for Knowledge Hub queries."""
    
    def __init__(self, db_connection):
        """
        Initialize knowledge database interface.
        
        Args:
            db_connection: Database connection object (psycopg2 connection)
        """
        self.conn = db_connection
    
    async def resolve_org_schema(self, org_identifier: str) -> str:
        """
        Resolve organisation identifier to actual database schema name.
        
        Looks up the organisation by ID and returns the schema name
        from the organisations.schema column.
        
        Args:
            org_identifier: Organisation ID (as string)
            
        Returns:
            str: Actual schema name from organisations.schema column
            
        Raises:
            ValueError: If organisation not found or has no schema
        """
        cursor = self.conn.cursor()
        
        try:
            # Parse as numeric ID
            try:
                org_id = int(org_identifier)
            except ValueError:
                raise ValueError(f"Organisation identifier must be numeric, got: '{org_identifier}'")
            
            # Get schema column from organisations table
            query = """
                SELECT schema 
                FROM public.organisations 
                WHERE id = %s
            """
            cursor.execute(query, [org_id])
            
            row = cursor.fetchone()
            if not row or not row[0]:
                raise ValueError(f"Organisation ID '{org_identifier}' not found or has no schema")
            
            schema_name = row[0]
            logger.info(f"Resolved org ID '{org_identifier}' to schema '{schema_name}'")
            return schema_name
            
        except Exception as e:
            logger.error(f"Failed to resolve org schema for '{org_identifier}': {e}")
            raise
        finally:
            cursor.close()
    
    def resolve_org_slug(self, org_id: int) -> str:
        """
        Resolve organisation ID to its slug.
        
        Looks up the organisation by ID and returns the slug
        from the organisations.slug column. Used by Teams API tools.
        
        Args:
            org_id: Organisation ID
            
        Returns:
            str: Organisation slug from organisations.slug column
            
        Raises:
            ValueError: If organisation not found or has no slug
        """
        cursor = self.conn.cursor()
        
        try:
            query = """
                SELECT slug 
                FROM public.organisations 
                WHERE id = %s
            """
            cursor.execute(query, [org_id])
            
            row = cursor.fetchone()
            if not row or not row[0]:
                raise ValueError(f"Organisation ID {org_id} not found or has no slug")
            
            slug = row[0]
            logger.info(f"Resolved org ID {org_id} to slug '{slug}'")
            return slug
            
        except Exception as e:
            logger.error(f"Failed to resolve org slug for ID {org_id}: {e}")
            raise
        finally:
            cursor.close()
    
    async def search_knowledge_items(
        self,
        org_schema: str,
        query_embedding: List[float],
        limit: int = 5,
        visibility_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge items using vector similarity.
        
        Uses pgvector's cosine similarity operator (<->) to find the most relevant
        knowledge items based on the query embedding.
        
        Args:
            org_schema: Organization schema name
            query_embedding: Query embedding vector (768 dimensions)
            limit: Maximum number of results to return (default: 5)
            visibility_filter: Optional visibility filter ('public', 'org_only', or None for all)
            
        Returns:
            List of knowledge items with similarity scores, ordered by relevance
        """
        cursor = self.conn.cursor()
        
        try:
            # Convert embedding to PostgreSQL vector format
            embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
            
            # Build query with optional visibility filter
            visibility_clause = ""
            params = [embedding_str, embedding_str, limit]
            
            if visibility_filter:
                visibility_clause = "AND visibility = %s"
                # Insert visibility filter between the two embedding params
                params = [embedding_str, visibility_filter, embedding_str, limit]
            
            # pgvector cosine similarity using <=> operator
            # Lower score = more similar
            query = f"""
                SELECT 
                    id,
                    title,
                    content,
                    source_type,
                    source_item_id,
                    embedding <=> %s::vector AS distance,
                    metadata,
                    created_at,
                    last_synced_at,
                    visibility
                FROM {org_schema}.knowledge_items
                WHERE is_deprecated = false
                  AND embedding IS NOT NULL
                {visibility_clause}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            
            cursor.execute(query, params)
            
            # Fetch and format results
            columns = [desc[0] for desc in cursor.description]
            results = []
            
            for row in cursor.fetchall():
                result = dict(zip(columns, row))
                
                # Convert Decimal to float for cosine distance
                if isinstance(result.get('distance'), Decimal):
                    result['distance'] = float(result['distance'])
                
                # Format datetime to ISO string
                if result.get('created_at'):
                    result['created_at'] = result['created_at'].isoformat()
                if result.get('last_synced_at'):
                    result['last_synced_at'] = result['last_synced_at'].isoformat()
                
                results.append(result)
            
            logger.info(
                f"Found {len(results)} knowledge items in {org_schema} "
                f"(limit: {limit}, visibility: {visibility_filter or 'all'})"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching knowledge items: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
    
    async def get_org_id_from_schema(self, org_schema: str) -> Optional[int]:
        """
        Get organisation ID from schema name.
        
        Args:
            org_schema: Organisation schema name (from organisations.schema column)
            
        Returns:
            Organisation ID or None if not found
        """
        cursor = self.conn.cursor()
        
        try:
            query = """
                SELECT id 
                FROM public.organisations 
                WHERE schema = %s
            """
            cursor.execute(query, [org_schema])
            
            row = cursor.fetchone()
            if row:
                return int(row[0])
            return None
            
        except Exception as e:
            logger.error(f"Error getting org ID from schema '{org_schema}': {e}")
            return None
        finally:
            cursor.close()


