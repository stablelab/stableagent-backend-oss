from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
try:
    # Pydantic v2
    from pydantic import ConfigDict  # type: ignore
except Exception:  # pragma: no cover
    ConfigDict = None  # type: ignore

from src.utils.logger import logger


class VertexSearchArgs(BaseModel):
    query: str = Field(..., description="Search query")
    page_size: int = Field(8, description="Number of results to return (max 32)")


class VertexSearchTool(BaseTool):
    # Allow dynamic attributes on the Pydantic model used by BaseTool (LangChain)
    # to avoid errors like: "VertexSearchTool object has no field 'enabled'".
    if ConfigDict is not None:
        model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)  # type: ignore

    name: str = "vertex_search_tool"
    description: str = (
        "Searches a configured Vertex AI Search / Discovery Engine data store. "
        "Requires env: ENABLE_VERTEX_SEARCH=1, VERTEX_PROJECT, VERTEX_LOCATION, VERTEX_DATASTORE_ID. "
        "Optional: VERTEX_COLLECTION=default_collection, VERTEX_SERVING_CONFIG=default_config."
    )
    args_schema: Type[BaseModel] = VertexSearchArgs

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.enabled = os.getenv("ENABLE_VERTEX_SEARCH", "0").strip() == "1"
        self.project = os.getenv("VERTEX_PROJECT")
        self.location = os.getenv("VERTEX_LOCATION")
        self.collection = os.getenv("VERTEX_COLLECTION", "default_collection")
        self.datastore = os.getenv("VERTEX_DATASTORE_ID")
        self.serving_config = os.getenv("VERTEX_SERVING_CONFIG", "default_config")
        try:
            logger.info(
                "VertexSearchTool: enabled=%s project=%s location=%s collection=%s datastore=%s serving=%s",
                self.enabled,
                self.project,
                self.location,
                self.collection,
                self.datastore,
                self.serving_config,
            )
        except Exception:
            pass

    def _run(self, query: str, page_size: int = 8) -> Dict[str, Any]:  # type: ignore[override]
        if not self.enabled:
            return {
                "results": [],
                "error": "Vertex AI Search is disabled. Set ENABLE_VERTEX_SEARCH=1.",
            }

        required = [self.project, self.location, self.datastore]
        if any(not v for v in required):
            return {
                "results": [],
                "error": (
                    "Vertex AI Search is not configured. Set VERTEX_PROJECT, VERTEX_LOCATION, VERTEX_DATASTORE_ID."
                ),
            }

        try:
            # Lazy import to avoid hard dependency if user doesn't enable the feature
            from google.cloud import discoveryengine_v1 as discoveryengine  # type: ignore

            client = discoveryengine.SearchServiceClient()
            serving_config = client.serving_config_path(
                project=self.project,
                location=self.location,
                data_store=self.datastore,
                serving_config=self.serving_config,
            )

            request = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query=query,
                page_size=min(max(1, int(page_size or 8)), 32),
            )
            response = client.search(request=request)

            results: List[Dict[str, Any]] = []
            for r in response:
                doc = r.document
                meta = dict(doc.derived_struct_data) if getattr(doc, "derived_struct_data", None) else {}
                results.append(
                    {
                        "id": doc.id,
                        "uri": doc.struct_data.get("link") if doc.struct_data else doc.uri,
                        "title": doc.struct_data.get("title") if doc.struct_data else meta.get("title"),
                        "snippet": meta.get("snippet") or meta.get("extract") or "",
                        "source": "vertex_ai_search",
                    }
                )

            return {"query": query, "results": results}
        except Exception as e:
            logger.error("VertexSearchTool: error: %s", e, exc_info=True)
            return {
                "results": [],
                "error": f"Vertex AI Search error: {str(e)}",
            }

    async def _arun(self, query: str, page_size: int = 8) -> Dict[str, Any]:  # type: ignore[override]
        # Synchronous client only; reuse sync path
        return self._run(query=query, page_size=page_size)


