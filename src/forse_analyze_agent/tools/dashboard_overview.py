# src/forse_analyze_agent/tools/dashboard_overview.py

from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
import httpx
import asyncio

from src.forse_analyze_agent.utils.validators import get_required_env
from src.utils.logger import logger


class DashboardOverviewInput(BaseModel):
    dashboard_id: str = Field(..., description="The dashboard ID to analyze")
    max_graphs: int = Field(default=10, description="Maximum number of graphs to fetch data for")


class GraphSummary(BaseModel):
    graph_id: str
    title: str
    graph_type: str
    categories: List[dict]
    data_sample: Optional[dict] = None  # First category's data summary


class DashboardOverview(BaseModel):
    dashboard_id: str
    total_graphs: int
    graphs: List[GraphSummary]
    data_fetched: int  # How many graphs have data


@tool(
    name_or_callable="fetch_dashboard_overview",
    description="Fetch complete dashboard overview including all graphs and their data for holistic analysis. Use when user asks about an entire dashboard.",
    args_schema=DashboardOverviewInput,
)
async def fetch_dashboard_overview(
    dashboard_id: str, 
    max_graphs: int = 10,
    timeout: int = 60
) -> DashboardOverview:
    """Fetch dashboard overview with all graphs and sample data."""
    
    def _empty_overview() -> DashboardOverview:
        """Return empty overview for error cases."""
        return DashboardOverview(
            dashboard_id=dashboard_id,
            total_graphs=0,
            graphs=[],
            data_fetched=0
        )
    
    try:
        base_url = get_required_env("FORSE_BACKEND_URL")
        cookies = {"jwt": get_required_env("FORSE_BACKEND_JWT")}
    except Exception as e:
        logger.error(f"Failed to get required environment variables: {e}")
        return _empty_overview()
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # 1. Fetch all graphs for dashboard
            graphs_url = f"{base_url}/api/graphs/newdashboard/{dashboard_id}/graphs"
            try:
                graphs_resp = await client.get(graphs_url, cookies=cookies)
                graphs_resp.raise_for_status()
                graphs_response = graphs_resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching dashboard graphs: {e.response.status_code}")
                return _empty_overview()
            except Exception as e:
                logger.error(f"Error fetching dashboard graphs: {e}")
                return _empty_overview()
            
            # Normalize response: handle both list and dict with 'graphs' key
            if isinstance(graphs_response, list):
                graphs_data = graphs_response
            elif isinstance(graphs_response, dict):
                graphs_data = graphs_response.get("graphs", [])
            else:
                logger.warning(f"Unexpected graphs response type: {type(graphs_response)}")
                graphs_data = []
            
            # 2. Fetch data for top N graphs in parallel
            graphs_to_fetch = graphs_data[:max_graphs] if graphs_data else []
            
            async def fetch_graph_data(graph: dict) -> Optional[GraphSummary]:
                try:
                    categories = graph.get("categories", [])
                    data_sample = None
                    
                    if categories:
                        first_cat = categories[0]
                        category_id = first_cat.get("category_id")
                        graph_id = graph.get("graph_id")
                        
                        if category_id and graph_id:
                            data_url = f"{base_url}/api/graphs/newdashboard-graphdata/{graph_id}/{category_id}"
                            try:
                                data_resp = await client.get(data_url, cookies=cookies)
                                if data_resp.status_code == 200:
                                    data = data_resp.json()
                                    # Create summary instead of full data
                                    data_list = data.get("data", []) if isinstance(data, dict) else []
                                    data_sample = {
                                        "record_count": len(data_list),
                                        "latest_value": data_list[-1] if data_list else None,
                                        "category": first_cat.get("category_name", "unknown")
                                    }
                            except Exception as e:
                                logger.warning(f"Failed to fetch data for graph {graph_id}: {e}")
                    
                    return GraphSummary(
                        graph_id=graph.get("graph_id", "unknown"),
                        title=graph.get("title", "Untitled"),
                        graph_type=graph.get("type", "unknown"),
                        categories=[
                            {"id": c.get("category_id", ""), "name": c.get("category_name", "")} 
                            for c in categories
                        ],
                        data_sample=data_sample
                    )
                except Exception as e:
                    logger.warning(f"Failed to process graph data: {e}")
                    return None
            
            # Parallel fetch with error handling
            results = await asyncio.gather(*[
                fetch_graph_data(g) for g in graphs_to_fetch
            ], return_exceptions=True)
            
            # Filter out None results and exceptions
            graph_summaries = [
                r for r in results 
                if isinstance(r, GraphSummary)
            ]
            
            return DashboardOverview(
                dashboard_id=dashboard_id,
                total_graphs=len(graphs_data),
                graphs=graph_summaries,
                data_fetched=sum(1 for g in graph_summaries if g.data_sample)
            )
            
    except httpx.TimeoutException as e:
        logger.error(f"Timeout fetching dashboard overview: {e}")
        return _empty_overview()
    except Exception as e:
        logger.error(f"Unexpected error fetching dashboard overview: {e}")
        return _empty_overview()
