"""Web search tool for Research Agent.

Self-contained implementation using Tavily, Exa, and Google CSE.
Designed to work in async contexts (LangGraph) without event loop issues.
"""
import asyncio
import concurrent.futures
import os
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from .base import ResearchBaseTool
from src.utils.logger import logger


# Content caps
MAX_CONTENT_CHARS = 2000
MAX_SNIPPET_CHARS = 400


@dataclass
class SearchHit:
    """A single search result."""
    url: str
    title: str
    snippet: Optional[str]
    content: Optional[str]
    score: float
    source: str


def _clean_url(u: str) -> str:
    """Normalize URL for deduplication."""
    try:
        p = urllib.parse.urlparse(u)
        return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return u


def _dedup(hits: List[SearchHit]) -> List[SearchHit]:
    """Remove duplicate URLs."""
    seen = set()
    deduped: List[SearchHit] = []
    for h in hits:
        key = _clean_url(h.url).lower()
        if key not in seen:
            seen.add(key)
            deduped.append(h)
    return deduped


# ============ Search Providers ============

async def _search_tavily(query: str, max_results: int = 10) -> List[SearchHit]:
    """Search using Tavily API."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []
    
    try:
        from langchain_tavily import TavilySearch
        
        tavily = TavilySearch(
            include_answer=False,
            include_raw_content=True,
            max_results=min(max_results, 10),
            search_depth="advanced",
        )
        
        result = await tavily.ainvoke({"query": query})
        
        hits: List[SearchHit] = []
        for r in result.get("results", []):
            content = r.get("content", "")
            if isinstance(content, str) and len(content) > MAX_CONTENT_CHARS:
                content = content[:MAX_CONTENT_CHARS]
            
            hits.append(SearchHit(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=None,
                content=content,
                score=float(r.get("score", 0)),
                source="tavily",
            ))
        
        logger.info(f"[WebSearch] Tavily returned {len(hits)} results")
        return hits
        
    except ImportError:
        logger.debug("[WebSearch] Tavily not installed")
        return []
    except Exception as e:
        logger.warning(f"[WebSearch] Tavily error: {e}")
        return []


async def _search_exa(query: str, max_results: int = 8) -> List[SearchHit]:
    """Search using Exa API."""
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        return []
    
    try:
        from langchain_exa.tools import ExaSearchResults
        
        exa = ExaSearchResults()
        result = await exa.ainvoke({"query": query, "num_results": min(max_results, 8)})
        
        # Normalize result format
        if isinstance(result, dict):
            results = result.get("results", [])
        elif isinstance(result, list):
            results = result
        else:
            results = getattr(result, "results", []) or []
        
        hits: List[SearchHit] = []
        for r in results:
            # Handle both dict and object formats
            if hasattr(r, "url"):
                url = r.url
                title = r.title
                text = getattr(r, "text", "")
                summary = getattr(r, "summary", "")
                score = getattr(r, "score", 0)
            else:
                url = r.get("url", "")
                title = r.get("title", "")
                text = r.get("text", "")
                summary = r.get("summary", "")
                score = r.get("score", 0)
            
            content = text[:MAX_CONTENT_CHARS] if text else None
            snippet = summary or (text[:MAX_SNIPPET_CHARS] if text else None)
            
            hits.append(SearchHit(
                url=url,
                title=title,
                snippet=snippet,
                content=content,
                score=float(score) if score else 0.0,
                source="exa",
            ))
        
        logger.info(f"[WebSearch] Exa returned {len(hits)} results")
        return hits
        
    except ImportError:
        logger.debug("[WebSearch] Exa not installed")
        return []
    except Exception as e:
        logger.warning(f"[WebSearch] Exa error: {e}")
        return []


async def _search_google(query: str, max_results: int = 10) -> List[SearchHit]:
    """Search using Google Custom Search API."""
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        return []
    
    try:
        from langchain_google_community import GoogleSearchAPIWrapper
        
        def _sync_search():
            google = GoogleSearchAPIWrapper(k=min(max_results, 10))
            return google.results(query, num_results=min(max_results, 10))
        
        # Run sync API in thread
        items = await asyncio.to_thread(_sync_search)
        
        hits: List[SearchHit] = []
        for item in items or []:
            snippet = item.get("snippet", "")
            if len(snippet) > MAX_SNIPPET_CHARS:
                snippet = snippet[:MAX_SNIPPET_CHARS]
            
            hits.append(SearchHit(
                url=item.get("link") or item.get("url", ""),
                title=item.get("title", ""),
                snippet=snippet,
                content=None,
                score=0.0,
                source="google",
            ))
        
        logger.info(f"[WebSearch] Google returned {len(hits)} results")
        return hits
        
    except ImportError:
        logger.debug("[WebSearch] Google search not installed")
        return []
    except Exception as e:
        logger.warning(f"[WebSearch] Google error: {e}")
        return []


async def _fanout_search(query: str, max_results: int = 10) -> List[SearchHit]:
    """Run all search providers in parallel and combine results."""
    tasks = [
        _search_tavily(query, max_results),
        _search_exa(query, max_results // 2),
        _search_google(query, max_results),
    ]
    
    results_nested = await asyncio.gather(*tasks, return_exceptions=True)
    
    all_hits: List[SearchHit] = []
    for r in results_nested:
        if isinstance(r, Exception):
            logger.warning(f"[WebSearch] Provider error: {r}")
            continue
        all_hits.extend(r)
    
    # Deduplicate by URL
    deduped = _dedup(all_hits)
    
    # Sort by score (Tavily/Exa have scores, Google doesn't)
    # Prefer sources with content
    def sort_key(h: SearchHit) -> tuple:
        has_content = 1 if h.content else 0
        source_priority = {"tavily": 3, "exa": 2, "google": 1}.get(h.source, 0)
        return (-has_content, -source_priority, -h.score)
    
    deduped.sort(key=sort_key)
    
    return deduped[:max_results]


# ============ Tool Implementation ============

class WebSearchInput(BaseModel):
    """Input for web search."""
    query: str = Field(..., description="Search query")
    num_results: int = Field(5, ge=1, le=10, description="Number of results to return")


class WebSearchTool(ResearchBaseTool):
    """Search the web for recent DAO news and events.
    
    Use as a last resort when data is not available in the database.
    Best for very recent events (last 30 days) or external news.
    
    Providers:
    - Tavily: AI-native search, best for crypto/DAO topics (requires TAVILY_API_KEY)
    - Exa: Semantic search with full content (requires EXA_API_KEY)  
    - Google CSE: Broad coverage (requires GOOGLE_API_KEY + GOOGLE_CSE_ID)
    """
    
    name: str = "web_search"
    description: str = """Search the web for recent DAO/governance news and information.
Input: query (required), num_results (optional, default 5)
Returns: Web search results with titles, snippets, and URLs.
Use as LAST RESORT when database tools have no results for recent events or external info."""
    args_schema: Type[BaseModel] = WebSearchInput
    
    def _run_tool(
        self,
        query: str,
        num_results: int = 5,
        **kwargs: Any,
    ) -> str:
        """Execute web search using multiple providers."""
        
        # Check if any provider is configured
        has_tavily = bool(os.getenv("TAVILY_API_KEY"))
        has_exa = bool(os.getenv("EXA_API_KEY"))
        has_google = bool(os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CSE_ID"))
        
        if not any([has_tavily, has_exa, has_google]):
            logger.warning("[WebSearch] No search providers configured")
            return (
                f"Web search unavailable - no search API keys configured. "
                f"Query: {query}\n\n"
                f"To enable web search, configure one of:\n"
                f"- TAVILY_API_KEY (recommended)\n"
                f"- EXA_API_KEY\n"
                f"- GOOGLE_API_KEY + GOOGLE_CSE_ID"
            )
        
        providers = []
        if has_tavily:
            providers.append("Tavily")
        if has_exa:
            providers.append("Exa")
        if has_google:
            providers.append("Google")
        
        logger.info(f"[WebSearch] Searching with providers: {', '.join(providers)}")
        
        try:
            # Run async search in a separate thread with its own event loop
            def run_async_search():
                return asyncio.run(_fanout_search(query, num_results))
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_search)
                hits = future.result(timeout=30)
            
            if not hits:
                return (
                    f"No web results found for '{query}'.\n\n"
                    f"Providers checked: {', '.join(providers)}\n"
                    f"Try a different query or check if the topic exists online."
                )
            
            # Format results
            output_lines = [f"**Web search results for '{query}':**\n"]
            
            for i, hit in enumerate(hits[:num_results], 1):
                title = hit.title or "Untitled"
                url = hit.url or ""
                snippet = hit.snippet or hit.content or ""
                
                if len(snippet) > 400:
                    snippet = snippet[:400] + "..."
                
                output_lines.append(f"**{i}. [{title}]({url})**")
                output_lines.append(f"   *via {hit.source}*")
                if snippet:
                    output_lines.append(f"   {snippet}")
                output_lines.append("")
            
            return "\n".join(output_lines)
            
        except concurrent.futures.TimeoutError:
            logger.error(f"[WebSearch] Timeout for query: {query}")
            return f"Web search timed out for '{query}'. Try a simpler query."
        except Exception as e:
            logger.error(f"[WebSearch] Error: {e}", exc_info=True)
            return f"Web search error for '{query}': {str(e)}"
