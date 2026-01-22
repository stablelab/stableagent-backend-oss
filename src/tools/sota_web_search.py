import os
import asyncio
import urllib.parse
from typing import List, Optional, Dict, Any, Type
from dataclasses import dataclass, asdict

from pydantic import BaseModel, Field
from langchain_core.documents import Document
from langchain_core.tools import BaseTool
from src.llm.factory import create_tool_chat_model
from src.utils.logger import logger
from src.utils.tool_events import emit_tool_event
import time

# Providers (optional; import guarded)
try:
    from langchain_tavily import TavilySearch  # type: ignore
    _HAS_TAVILY = True
except Exception:  # pragma: no cover - optional dependency
    TavilySearch = None  # type: ignore
    _HAS_TAVILY = False

try:
    from langchain_exa.tools import ExaSearchResults  # type: ignore
    _HAS_EXA = True
except Exception:  # pragma: no cover - optional dependency
    ExaSearchResults = None  # type: ignore
    _HAS_EXA = False

try:
    from langchain_google_community import GoogleSearchAPIWrapper  # type: ignore
    _HAS_GOOGLE = True
except Exception:  # pragma: no cover - optional dependency
    GoogleSearchAPIWrapper = None  # type: ignore
    _HAS_GOOGLE = False

# Loaders / reranker (optional; import guarded)
try:
    from langchain_community.document_loaders import WebBaseLoader  # type: ignore
    _HAS_LOADER = True
except Exception:  # pragma: no cover - optional dependency
    WebBaseLoader = None  # type: ignore
    _HAS_LOADER = False

try:
    from langchain_cohere import CohereRerank  # type: ignore
    _HAS_COHERE = True
except Exception:  # pragma: no cover - optional dependency
    CohereRerank = None  # type: ignore
    _HAS_COHERE = False

# Content caps to avoid flooding downstream prompts
MAX_CONTENT_CHARS = int(os.getenv("WEB_SEARCH_MAX_CHARS", "2000"))
MAX_SNIPPET_CHARS = int(os.getenv("WEB_SEARCH_MAX_SNIPPET", "400"))


@dataclass
class SearchHit:
    url: str
    title: str
    snippet: Optional[str]
    content: Optional[str]
    score: float
    source: str
    published: Optional[str] = None


def _clean_url(u: str) -> str:
    try:
        p = urllib.parse.urlparse(u)
        return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return u


def _dedup(hits: List[SearchHit]) -> List[SearchHit]:
    seen = set()
    deduped: List[SearchHit] = []
    for h in hits:
        key = _clean_url(h.url).lower()
        if key not in seen:
            seen.add(key)
            deduped.append(h)
    return deduped


# ---------- Providers (Tavily, Exa, Google CSE)

async def _search_tavily(query: str, time_range: Optional[str], topic: Optional[str], max_results: int) -> List[SearchHit]:
    if not _HAS_TAVILY or not os.getenv("TAVILY_API_KEY"):
        return []
    t = TavilySearch(
        include_answer=False,
        include_raw_content=True,
        max_results=min(max_results, 10),
        time_range=time_range,
        topic=topic or "general",
        search_depth="advanced",
        auto_parameters=True,
    )
    out = await t.ainvoke({"query": query})
    hits: List[SearchHit] = []
    for r in out.get("results", []):
        content = r.get("content")
        if isinstance(content, str) and len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS]
        hits.append(
            SearchHit(
                url=r.get("url", ""),
                title=r.get("title"),
                snippet=None,
                content=content,
                score=float(r.get("score") or 0.0),
                source="tavily",
            )
        )
    return hits


async def _search_exa(query: str, max_results: int) -> List[SearchHit]:
    if not _HAS_EXA or not os.getenv("EXA_API_KEY"):
        return []
    exa = ExaSearchResults()
    res = await exa.ainvoke({"query": query, "num_results": min(max_results, 8)})
    # Normalize result list
    if isinstance(res, dict):
        results = res.get("results", []) or []
    elif isinstance(res, list):
        results = res
    else:
        results = getattr(res, "results", []) or []

    def _get_val(obj, attr: str, key: Optional[str] = None):
        if hasattr(obj, attr):
            return getattr(obj, attr)
        if isinstance(obj, dict):
            return obj.get(key or attr)
        return None

    hits: List[SearchHit] = []
    for r in results:
        text_full = _get_val(r, "text")
        if isinstance(text_full, str) and len(text_full) > MAX_CONTENT_CHARS:
            text_trimmed = text_full[:MAX_CONTENT_CHARS]
        else:
            text_trimmed = text_full
        summary = _get_val(r, "summary")
        if not summary:
            base = text_trimmed or ""
            summary = base[:MAX_SNIPPET_CHARS]
        score_val = _get_val(r, "score")
        published = _get_val(r, "published_date")
        url_val = _get_val(r, "url") or ""
        title_val = _get_val(r, "title")
        try:
            score_num = float(score_val or 0.0)
        except Exception:
            score_num = 0.0
        hits.append(
            SearchHit(
                url=url_val,
                title=title_val,
                snippet=summary,
                content=text_trimmed,
                score=score_num,
                source="exa",
                published=published,
            )
        )
    return hits


def _search_google_sync(query: str, k: int) -> List[SearchHit]:
    if not _HAS_GOOGLE:
        return []
    try:
        g = GoogleSearchAPIWrapper(k=min(k, 10))
        items = g.results(query, num_results=min(k, 10))
        hits: List[SearchHit] = []
        for it in items or []:
            snippet = it.get("snippet")
            if isinstance(snippet, str) and len(snippet) > MAX_SNIPPET_CHARS:
                snippet = snippet[:MAX_SNIPPET_CHARS]
            hits.append(
                SearchHit(
                    url=it.get("link") or it.get("url", ""),
                    title=it.get("title"),
                    snippet=snippet,
                    content=None,
                    score=0.0,
                    source="google_cse",
                )
            )
        return hits
    except Exception:
        return []


async def _search_google(query: str, k: int) -> List[SearchHit]:
    return await asyncio.to_thread(_search_google_sync, query, k)


# ---------- Content fetching (for SERP results without full text)

async def _fetch_contents(urls: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not _HAS_LOADER:
        return out

    async def _load_one(u: str):
        try:
            loader = WebBaseLoader(web_paths=[u])
            docs = await asyncio.to_thread(loader.load)
            if docs:
                content = docs[0].page_content
                if isinstance(content, str) and len(content) > MAX_CONTENT_CHARS:
                    content = content[:MAX_CONTENT_CHARS]
                out[u] = content
        except Exception:
            pass

    await asyncio.gather(*[_load_one(u) for u in urls])
    return out


# ---------- Reranking

def _rerank(query: str, hits: List[SearchHit], top_n: int) -> List[SearchHit]:
    try:
        compressor = CohereRerank(
            model=os.getenv("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0"),
            top_n=top_n,
        )
        docs = [
            Document(
                page_content=" \n".join(
                    filter(None, [h.title, h.snippet, (h.content or "")])
                ),
                metadata={"url": h.url, "source": h.source},
            )
            for h in hits
        ]
        ranked = compressor.compress_documents(docs, query)
        url2hit = {_clean_url(h.url): h for h in hits}
        out: List[SearchHit] = []
        for d in ranked:
            u = _clean_url(d.metadata.get("url", ""))
            h = url2hit.get(u)
            if h:
                out.append(h)
        return out
    except Exception:
        pref = {"tavily": 2, "exa": 2, "google_cse": 1}
        return sorted(hits, key=lambda h: (-(pref.get(h.source, 0)), -h.score))[:top_n]


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Search query to look up")
    k: int = Field(12, description="Total number of results to return after reranking")
    time_range: Optional[str] = Field(None, description="One of {'day','week','month','year'} for recency filtering")
    news: bool = Field(False, description="If true, bias providers towards news")
    fetch_full_content: bool = Field(True, description="If true, fetch page bodies for non AI-native SERP hits")


async def _fanout_search(args: WebSearchArgs) -> List[SearchHit]:
    topic = "news" if args.news else "general"
    tasks = [
        _search_tavily(args.query, args.time_range, topic, max_results=args.k),
        _search_exa(args.query, max_results=args.k // 2),
        _search_google(args.query, k=args.k),
    ]
    results_nested = await asyncio.gather(*tasks, return_exceptions=True)
    all_hits: List[SearchHit] = []
    for r in results_nested:
        if isinstance(r, Exception):
            continue
        all_hits.extend(r)

    all_hits = _dedup(all_hits)

    if args.fetch_full_content:
        missing = [h.url for h in all_hits if not h.content]
        bodies = await _fetch_contents(missing[: args.k]) if missing else {}
        for h in all_hits:
            if not h.content and h.url in bodies:
                h.content = bodies[h.url]

    reranked = _rerank(args.query, all_hits, top_n=args.k)
    return reranked


class SotaWebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = (
        "High-recall, high-precision internet search across Tavily, Exa, and Google CSE with reranking and optional content fetching. "
        "Use ONLY as a last resort when DAO database-backed tools (sql_query_tool, database_query_tool) "
        "cannot answer the question or when the question is clearly outside DAO/governance scope (e.g., general news or definitions)."
    )
    args_schema: Type[BaseModel] = WebSearchArgs

    def __init__(self, **data):
        super().__init__(**data)
        try:
            rerank_model = os.getenv("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0")
            logger.info("SotaWebSearchTool: initialized (no chat LLM); rerank_model=%s", rerank_model)
        except Exception:
            pass

    def _run(
        self,
        query: str,
        k: int = 12,
        time_range: Optional[str] = None,
        news: bool = False,
        fetch_full_content: bool = True,
    ) -> Dict[str, Any]:
        args = WebSearchArgs(
            query=query,
            k=k,
            time_range=time_range,
            news=news,
            fetch_full_content=fetch_full_content,
        )
        start_ts = time.time()
        try:
            emit_tool_event("web_search.input", {"query": query, "k": k, "time_range": time_range, "news": news})
            emit_tool_event("tool.start", {"tool": self.name, "input": {"k": k, "time_range": time_range, "news": news}})
        except Exception:
            pass
        # Prefer async path in agent; for pure sync contexts, run minimal sync fallback to avoid event loop issues
        try:
            loop = asyncio.get_running_loop()
            # Running loop detected: avoid nested loop; degrade to Google-only sync search
            hits = _search_google_sync(query=args.query, k=args.k)
            out = {"query": query, "results": [asdict(h) for h in hits]}
            try:
                emit_tool_event("web_search.output", {"count": len(out.get("results") or [])})
                emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000), "result": {"count": len(out.get("results") or [])}})
            except Exception:
                pass
            return out
        except RuntimeError:
            # No running loop; safe to run the full async fanout
            try:
                hits = asyncio.run(_fanout_search(args))
            except Exception as e:
                try:
                    emit_tool_event("web_search.error", {"message": str(e)})
                except Exception:
                    pass
                hits = []
            out = {"query": query, "results": [asdict(h) for h in hits]}
            try:
                emit_tool_event("web_search.output", {"count": len(out.get("results") or [])})
                emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000), "result": {"count": len(out.get("results") or [])}})
            except Exception:
                pass
            return out

    async def _arun(
        self,
        query: str,
        k: int = 12,
        time_range: Optional[str] = None,
        news: bool = False,
        fetch_full_content: bool = True,
    ) -> Dict[str, Any]:
        args = WebSearchArgs(
            query=query,
            k=k,
            time_range=time_range,
            news=news,
            fetch_full_content=fetch_full_content,
        )
        try:
            start_ts = time.time()
            hits = await _fanout_search(args)
        except Exception as e:
            try:
                emit_tool_event("web_search.error", {"message": str(e)})
            except Exception:
                pass
            hits = []
        out = {"query": query, "results": [asdict(h) for h in hits]}
        try:
            emit_tool_event("web_search.output", {"count": len(out.get("results") or [])})
            emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "result": {"count": len(out.get("results") or [])}})
        except Exception:
            pass
        return out


async def summarize_with_citations(
    question: str, hits: List[SearchHit], model: Optional[str] = None
) -> str:
    model_name = model or os.getenv("OPENAI_MODEL_NAME", "gpt-5-mini")
    llm = create_tool_chat_model("web_search_summarizer", default_provider="openai", default_model=model_name)
    bullets: List[str] = []
    for i, h in enumerate(hits[:8], 1):
        text = (h.content or h.snippet or "")[:1200]
        bullets.append(f"[{i}] {h.title}\nURL: {h.url}\n---\n{text}")
    prompt = (
        "You are a careful researcher. Answer the question using ONLY the sources below.\n"
        "Include inline citations like [1], [2] that map to the numbered sources.\n\n"
        f"Question: {question}\n\nSources:\n" + "\n".join(bullets)
    )
    resp = await llm.ainvoke(prompt)
    return resp.content

