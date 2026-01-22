"""Base classes for Research Agent tools.

Provides common functionality for all research tools including:
- Database connection management
- Embedding generation for semantic search
- Error handling and logging
- Result formatting
"""
from abc import abstractmethod
from typing import Any, Dict, List, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from src.utils.logger import logger


class ResearchToolError(Exception):
    """Exception raised when a research tool encounters an error."""
    pass


class ResearchBaseTool(BaseTool):
    """Base class for all Research Agent tools.
    
    Provides common functionality for database queries with semantic search
    via embeddings.
    """
    
    # Subclasses should set these
    name: str = "research_base_tool"
    description: str = "Base research tool"
    args_schema: Type[BaseModel] = BaseModel
    
    def _run(self, *args: Any, **kwargs: Any) -> Any:
        """Run the tool - delegates to _run_tool with error handling."""
        try:
            logger.info(f"[RESEARCH TOOL] Running {self.name} with params: {kwargs}")
            result = self._run_tool(**kwargs)
            logger.info(f"[RESEARCH TOOL] {self.name} completed successfully")
            return result
        except ResearchToolError as e:
            logger.error(f"[RESEARCH TOOL] {self.name} error: {e}")
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"[RESEARCH TOOL] {self.name} unexpected error: {e}", exc_info=True)
            return f"Error executing {self.name}: {str(e)}"
    
    @abstractmethod
    def _run_tool(self, **kwargs: Any) -> str:
        """Execute the tool logic. Subclasses must implement this."""
        raise NotImplementedError("Subclasses must implement _run_tool")
    
    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        """Async run - falls back to sync for now."""
        return self._run(*args, **kwargs)
    
    def _format_preview_block(
        self,
        preview_type: str,
        data: List[Dict[str, Any]] | Dict[str, Any],
    ) -> str:
        """Format data as a preview block for the frontend.
        
        Args:
            preview_type: Type of preview (proposal, discussion, etc.)
            data: Single dict or list of dicts to include in the preview
            
        Returns:
            Markdown code block with preview data as JSON
        """
        import json
        
        # Remove embedding vectors and other large fields
        def clean_item(item: Dict[str, Any]) -> Dict[str, Any]:
            cleaned = {}
            for key, value in item.items():
                # Skip internal/large fields
                if key in ("embedding", "distance", "similarity_score", "vector"):
                    continue
                cleaned[key] = value
            return cleaned
        
        if isinstance(data, list):
            cleaned_data = [clean_item(item) for item in data[:5]]  # Limit to 5 previews
        else:
            cleaned_data = clean_item(data)
        
        json_str = json.dumps(cleaned_data, indent=2, default=str)
        return f"```{preview_type}-preview\n{json_str}\n```"


class SemanticSearchTool(ResearchBaseTool):
    """Base class for tools that use semantic search via embeddings.
    
    Extends ResearchBaseTool with embedding generation capabilities.
    """
    
    _embedding_service: Optional[Any] = None
    _db_client: Optional[Any] = None
    
    def _get_embedding_service(self):
        """Get or create the embedding service (lazy initialization)."""
        if self._embedding_service is None:
            from src.services.gemini_embeddings import EmbeddingsService
            # Use gemini-embedding-001 with 3072 dimensions
            self._embedding_service = EmbeddingsService(
                model="gemini-embedding-001",
                dimensionality=3072
            )
        return self._embedding_service
    
    def _get_db_client(self):
        """Get or create the database client (lazy initialization)."""
        if self._db_client is None:
            from .database_client import ResearchDatabaseClient
            self._db_client = ResearchDatabaseClient()
        return self._db_client
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate an embedding vector for the given text."""
        try:
            service = self._get_embedding_service()
            embeddings = service.embed_documents([text])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            return []
        except Exception as e:
            logger.error(f"[RESEARCH TOOL] Embedding generation failed: {e}")
            return []
    
    def _format_as_vector_literal(self, embedding: List[float]) -> str:
        """Format embedding as PostgreSQL vector literal."""
        if not embedding:
            return "'[]'::vector"
        return f"'[{','.join(str(v) for v in embedding)}]'::vector"
    
    def _format_results(
        self,
        results: List[Dict[str, Any]],
        title_key: str = "title",
        max_results: int = 10
    ) -> str:
        """Format query results into a readable string."""
        if not results:
            return "No results found."
        
        results = results[:max_results]
        formatted = []
        
        for i, row in enumerate(results, 1):
            title = row.get(title_key, "Untitled")
            formatted.append(f"\n**{i}. {title}**")
            
            for key, value in row.items():
                if key == title_key or key == "embedding" or key == "distance":
                    continue
                if value is not None:
                    # Truncate long values
                    str_value = str(value)
                    if len(str_value) > 500:
                        str_value = str_value[:500] + "..."
                    formatted.append(f"  - {key}: {str_value}")
        
        return "\n".join(formatted)
