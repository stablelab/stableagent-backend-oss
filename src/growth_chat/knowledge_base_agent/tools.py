"""
LangChain tools for Knowledge Hub Agent.

Provides search functionality for the organization's Knowledge Hub,
enabling RAG-based document retrieval with vector similarity search.
"""
import asyncio
import json
import os
from typing import Any, List, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.services.gemini_embeddings import EmbeddingsService
from src.utils.db_utils import (get_database_connection,
                                return_database_connection)
from src.utils.logger import logger

from .database import KnowledgeDatabase

# ==================
# Tool Input Schemas
# ==================

class SearchKnowledgeHubInput(BaseModel):
    """Input for searching the Knowledge Hub."""
    query: str = Field(
        ..., 
        description="The keyword search query to find relevant documents. Use specific keywords rather than full questions."
    )


# ==================
# Knowledge Hub Tool
# ==================

class SearchKnowledgeHubTool(BaseTool):
    """
    Tool for searching the Knowledge Hub using vector similarity.
    
    Searches the organization's knowledge base for documents matching
    the query using semantic similarity. Use this tool multiple times
    with different keyword queries to find comprehensive information.
    """
    
    name: str = "search_knowledge_hub"
    description: str = """Search the Knowledge Hub for relevant documents using keyword-based semantic search.

Use this tool to find information from your organization's Knowledge Hub. You can call this tool MULTIPLE TIMES with different keyword queries to find comprehensive information.

SEARCH STRATEGY:
- Break down complex questions into focused keyword searches
- Use specific terms rather than full questions
- Try different phrasings if initial searches don't return good results

EXAMPLES:
- For "how do I write a good grant proposal?", try searches like:
  - "grant proposal guidelines"
  - "proposal writing tips"  
  - "application requirements"
- For "what is our voting process?", try:
  - "voting process"
  - "governance voting"
  - "proposal voting"

The tool returns documents with titles, content snippets, and similarity scores.
"""
    
    args_schema: Type[BaseModel] = SearchKnowledgeHubInput
    
    # Configuration injected at creation time
    org_schema: str = ""
    org_id: int = 0
    visibility: Optional[str] = None  # "public" for limited access, None for full access
    
    def _run(self, query: str) -> str:
        """
        Search the Knowledge Hub synchronously.
        
        Args:
            query: Keyword search query
            
        Returns:
            Formatted string with search results
        """
        logger.info(f"[TOOL] SearchKnowledgeHub called with query='{query}'")
        
        # Run the async search in a sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a new task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._async_search(query))
                    return future.result()
            else:
                return loop.run_until_complete(self._async_search(query))
        except RuntimeError:
            # No event loop exists, create one
            return asyncio.run(self._async_search(query))
    
    async def _arun(self, query: str) -> str:
        """
        Search the Knowledge Hub asynchronously.
        
        Args:
            query: Keyword search query
            
        Returns:
            Formatted string with search results
        """
        logger.info(f"[TOOL] SearchKnowledgeHub async called with query='{query}'")
        return await self._async_search(query)
    
    async def _async_search(self, query: str) -> str:
        """
        Perform the actual Knowledge Hub search.
        
        Args:
            query: Keyword search query
            
        Returns:
            Formatted string with search results
        """
        conn = None
        try:
            # Get database connection
            conn = get_database_connection()
            database = KnowledgeDatabase(conn)
            
            # Generate query embedding using Gemini embeddings service
            embeddings_service = EmbeddingsService(
                model=os.environ.get("EMBEDDING_MODEL_NAME", "gemini-embedding-001"),
                dimensionality=768
            )
            
            query_embedding = embeddings_service.embed_query(query)
            
            # Search knowledge items using vector similarity
            # visibility is set based on user's role in the organization:
            # - "public" for Guest/Builder roles (limited access)
            # - None for Staff/Admin roles (full access to all items)
            documents = await database.search_knowledge_items(
                org_schema=self.org_schema,
                query_embedding=query_embedding,
                limit=os.environ.get("KNOWLEDGE_AGENT_RETRIEVAL_LIMIT", 3),
                visibility_filter=self.visibility
            )
            
            # Format results for the agent
            return self._format_results(query, documents)
            
        except Exception as e:
            logger.error(f"[TOOL] SearchKnowledgeHub error: {e}", exc_info=True)
            return f"Error searching Knowledge Hub: {str(e)}"
        finally:
            if conn is not None:
                return_database_connection(conn)
    
    def _format_results(self, query: str, documents: List[dict]) -> str:
        """
        Format search results as JSON for the agent and frontend.
        
        Args:
            query: Original search query
            documents: List of document dictionaries
            
        Returns:
            JSON string with search results
        """
        if not documents:
            return json.dumps({
                "query": query,
                "count": 0,
                "documents": [],
                "message": "No documents found. The Knowledge Hub doesn't contain information matching this search. Consider trying different keywords or inform the user that they may need to add more content to the Knowledge Hub."
            })
        
        result = {
            "query": query,
            "count": len(documents),
            "documents": []
        }
        
        for doc in documents:
            # Calculate similarity percentage (distance 0 = 100%, distance 2 = 0%) and round to units
            distance = doc.get("distance", 2)
            similarity_pct = round(max(0, (1 - distance / 2) * 100))
            
            content = doc.get("content", "")
            # Truncate content for readability
            content_preview = content[:1000] + "..." if len(content) > 1000 else content
            
            result["documents"].append({
                "title": doc.get("title", "Untitled"),
                "source_type": doc.get("source_type", "unknown"),
                "content": content_preview,
                "distance": distance,
                "similarity_pct": similarity_pct,
                "metadata": doc.get("metadata", {}),
                "id": doc.get("id"),
                "source_item_id": doc.get("source_item_id", ""),
                "created_at": doc.get("created_at"),
                "last_synced_at": doc.get("last_synced_at"),
                "visibility": doc.get("visibility", "public"),
            })
        
        return json.dumps(result)


# ==================
# Tool Factory
# ==================

def create_knowledge_hub_tools(
    org_schema: str,
    org_id: int,
    visibility: Optional[str] = None,
) -> List[BaseTool]:
    """
    Create Knowledge Hub tools with the given organization context.
    
    Args:
        org_schema: Organization database schema name
        org_id: Organization ID
        visibility: Visibility filter for knowledge items ("public" or None for all)
        
    Returns:
        List of tool instances for the Knowledge Hub agent
    """
    tools = [
        SearchKnowledgeHubTool(
            org_schema=org_schema,
            org_id=org_id,
            visibility=visibility,
        ),
    ]
    
    return tools

